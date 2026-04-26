"""
app_admin/routes/zarzadzanie/dokumenty_studentow.py
Lista dokumentów studentów – widok dla ADMIN i UOPZ.
"""

import logging
import unicodedata
from urllib.parse import quote

import httpx
from flask import render_template, request, abort, make_response, current_app
from flask_login import login_required, current_user

from core.modele import EnrollmentStatus, UserRole
from core.uslugi.dokumenty import DOC_CONFIG, STATIC_TEMPLATES, rozwiaz_dokumenty, buduj_kontekst
from core.repozytoria import UserRepository, EnrollmentRepository

from . import zarzadzanie_bp

logger = logging.getLogger(__name__)

_repo_uzytk   = UserRepository()
_repo_zapisow = EnrollmentRepository()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_tex_url() -> str:
    return current_app.config.get('TEX_SERVICE_URL', 'http://tex-service:5002')


def _sciezka(zapis) -> str:
    return zapis.track_type.value if zapis.track_type else 'STANDARD'


def _pdf_content_disposition(base_name: str, last_name: str) -> str:
    """Buduje nagłówek Content-Disposition zgodny z RFC 6266 + RFC 5987.

    Zawiera dwa tokeny filename:
    - ``filename=`` — ASCII fallback (znaki spoza ASCII pominięte, nigdy puste)
    - ``filename*=`` — pełna nazwa zakodowana UTF-8 dla przeglądarek obsługujących RFC 5987
    """
    full = f"{base_name}_{last_name}.pdf"
    ascii_fallback = (
        unicodedata.normalize('NFKD', full)
        .encode('ascii', 'ignore').decode('ascii')
        .strip() or 'dokument.pdf'
    )
    utf8_encoded = quote(full, safe='')
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_encoded}"


# ── Lista studentów ───────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/dokumenty')
@login_required
def dokumenty_studentow():
    strona     = request.args.get('strona', 1, type=int)
    szukaj     = request.args.get('szukaj', '').strip()
    uopz_id    = current_user.id if current_user.role == UserRole.UOPZ else None

    studenci_page = _repo_uzytk.studenci_strona(
        szukaj=szukaj, supervisor_id=uopz_id, strona=strona
    )

    aktywne_statusy = [
        EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.COMMISSION_REVIEW,
        EnrollmentStatus.DIRECTOR_APPROVAL, EnrollmentStatus.IN_PROGRESS,
        EnrollmentStatus.COMPLETED,
    ]
    student_ids = [s.id for s in studenci_page.items]
    aktywne_counts = _repo_zapisow.liczba_aktywnych_dla_studentow(
        student_ids, aktywne_statusy
    )

    uopz_cache: dict = {}
    studenci_info = []
    for s in studenci_page.items:
        uopz = None
        if s.supervisor_id:
            if s.supervisor_id not in uopz_cache:
                uopz_cache[s.supervisor_id] = _repo_uzytk.znajdz_po_id(s.supervisor_id)
            uopz = uopz_cache[s.supervisor_id]
        studenci_info.append({
            'student': s,
            'uopz':    uopz,
            'aktywne': aktywne_counts.get(s.id, 0),
        })

    return render_template(
        'zarzadzanie/dokumenty_studentow.html',
        studenci=studenci_page,
        studenci_info=studenci_info,
        szukaj=szukaj,
    )


# ── Dokumenty jednego studenta ────────────────────────────────────────────────

@zarzadzanie_bp.route('/dokumenty/student/<uuid:student_id>')
@login_required
def dokumenty_studenta(student_id):
    student = _repo_uzytk.znajdz_po_id(student_id) or abort(404)

    aktywne_statusy = [
        EnrollmentStatus.AWAITING_APPROVAL,
        EnrollmentStatus.COMMISSION_REVIEW,
        EnrollmentStatus.DIRECTOR_APPROVAL,
        EnrollmentStatus.IN_PROGRESS,
        EnrollmentStatus.COMPLETED,
    ]
    zapisy = _repo_zapisow.aktywne_dla_studenta(student_id, aktywne_statusy)

    if current_user.role == UserRole.UOPZ:
        is_student_supervisor = student.supervisor_id == current_user.id
        is_enrollment_supervisor = any(z.supervisor_id == current_user.id for z in zapisy)
        if not (is_student_supervisor or is_enrollment_supervisor):
            abort(403)
    uopz   = _repo_uzytk.znajdz_po_id(student.supervisor_id) if student.supervisor_id else None

    dokumenty_list = [
        {'zapis': z, 'docs': rozwiaz_dokumenty(z), 'sciezka': _sciezka(z)}
        for z in zapisy
    ]

    return render_template(
        'zarzadzanie/dokumenty_studenta.html',
        student=student,
        uopz=uopz,
        dokumenty_list=dokumenty_list,
    )


# ── Pobieranie dokumentów ─────────────────────────────────────────────────────

@zarzadzanie_bp.route('/dokumenty/pobierz/<uuid:zapis_id>/<typ>')
@login_required
def dokumenty_pobierz(zapis_id, typ):
    if typ not in DOC_CONFIG:
        abort(404)
    zapis = _repo_zapisow.znajdz_po_id(zapis_id) or abort(404)
    if current_user.role == UserRole.UOPZ and zapis.supervisor_id != current_user.id:
        abort(403)

    template_name, filename = DOC_CONFIG[typ]
    ctx = buduj_kontekst(zapis, typ)
    try:
        response = httpx.post(
            f"{_get_tex_url()}/generuj",
            json={'template': template_name, 'context': ctx, 'filename': filename},
            timeout=60,
        )
        if response.status_code != 200:
            abort(500)
        pdf_name = template_name.replace('.tex.j2', '')
        resp = make_response(response.content)
        resp.headers['Content-Type'] = 'application/pdf'
        resp.headers['Content-Disposition'] = _pdf_content_disposition(
            pdf_name, zapis.student.last_name or 'student'
        )
        return resp
    except Exception:
        logger.exception("Błąd generowania %s dla %s", typ, zapis_id)
        abort(500)


@zarzadzanie_bp.route('/dokumenty/staly/<klucz>')
@login_required
def dokumenty_pobierz_staly(klucz):
    if klucz not in STATIC_TEMPLATES:
        abort(404)
    template_name, filename = STATIC_TEMPLATES[klucz]
    try:
        response = httpx.post(
            f"{_get_tex_url()}/generuj",
            json={'template': template_name, 'context': {}, 'filename': filename},
            timeout=30,
        )
        if response.status_code != 200:
            abort(500)
        resp = make_response(response.content)
        resp.headers['Content-Type'] = 'application/pdf'
        resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp
    except Exception:
        logger.exception("Błąd pobierania stałego dokumentu %s", klucz)
        abort(500)
