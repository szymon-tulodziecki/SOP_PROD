"""
app_admin/routes/zarzadzanie/dokumenty_studentow.py
Lista dokumentów studentów – widok dla ADMIN i UOPZ.
"""

import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable

import httpx
from flask import render_template, request, abort, make_response, current_app
from flask_login import login_required, current_user

from core.modele import (
    Uzytkownik, Student, ZapisPraktyki, StatusZapisu,
    HarmonogramPraktyki, RolaUzytkownika,
)
from core.extensions import db

from . import zarzadzanie_bp

logger = logging.getLogger(__name__)


# ── Konfiguracja szablonów ────────────────────────────────────────────────────

DOC_CONFIG = {
    'ZAL_1':  ('zal1_porozumienie.tex.j2',  'zal1_porozumienie.pdf'),
    'ZAL_2':  ('zal2_program.tex.j2',        'zal2_program.pdf'),
    'ZAL_2A': ('zal2a_program.tex.j2',       'zal2a_program.pdf'),
    'ZAL_3':  ('zal3_karta.tex.j2',          'zal3_karta.pdf'),
    'ZAL_4':  ('zal4_efekty.tex.j2',         'zal4_efekty.pdf'),
    'ZAL_4A': ('zal4a_komisja.tex.j2',       'zal4a_komisja.pdf'),
    'ZAL_4B': ('zal4b_wniosek.tex.j2',       'zal4b_wniosek.pdf'),
    'ZAL_6':  ('zal6_dziennik.tex.j2',       'zal6_dziennik.pdf'),
    'ZAL_7':  ('zal7_sprawozdanie.tex.j2',   'zal7_sprawozdanie.pdf'),
    'ZAL_7A': ('zal7a_sprawozdanie.tex.j2',  'zal7a_sprawozdanie.pdf'),
    'ZAL_8':  ('zal8_protokol.tex.j2',       'zal8_protokol.pdf'),
    'ZAL_9':  ('zal9_oswiadczenie.tex.j2',   'zal9_oswiadczenie.pdf'),
}

STATIC_TEMPLATES = {
    'ankieta': ('zal5_ankieta.tex.j2', 'zal5_ankieta.pdf'),
}


# ── Policy Object — deklaratywna lista dokumentów per ścieżka ────────────────

@dataclass
class DocumentEntry:
    """Deklaracja jednego dokumentu na liście.

    available_when: callable(ctx) → bool
    unavailable_reason: callable(ctx) → str | None
    """
    name: str
    doc_type: str | None = None          # None → dokument statyczny
    description: str | None = None
    static_key: str | None = None
    available_when: Callable = field(default=lambda _ctx: True)
    unavailable_reason: Callable = field(default=lambda _ctx: None)

    def resolve(self, ctx: dict) -> dict:
        available = self.available_when(ctx)
        entry = {
            'nazwa':    self.name,
            'opis':     self.description,
            'dostepny': available,
            'powod':    None if available else self.unavailable_reason(ctx),
        }
        if self.static_key:
            entry.update({'staly': True, 'klucz_staly': self.static_key})
        else:
            entry.update({'dynamiczny': True, 'typ': self.doc_type,
                          'zapis_id': ctx['zapis_id']})
        return entry


_SEPARATOR = lambda name: {'separator': True, 'nazwa': name}  # noqa: E731

# Reguły dostępności (callable przyjmuje ctx-dict z flagami stanu zapisu)
_zawsze         = lambda ctx: True                                     # noqa: E731
_w_trakcie_lub_zakonczona = lambda ctx: ctx['w_trakcie'] or ctx['zakonczona']  # noqa: E731
_zakonczona     = lambda ctx: ctx['zakonczona']                        # noqa: E731
_oceniona       = lambda ctx: ctx['oceniona']                          # noqa: E731
_ma_harmonogram = lambda ctx: ctx['harmonogram_count'] > 0             # noqa: E731
_firma_custom   = lambda ctx: ctx['firma_custom']                      # noqa: E731
_firma_bez_umowy = lambda ctx: ctx['firma_bez_umowy']                  # noqa: E731
_dziekan_lub_zakonczona = lambda ctx: ctx['dziekan_zatwierdził'] or ctx['zakonczona']  # noqa: E731


# Każda ścieżka to lista DocumentEntry lub wynik wywołania (dla warunkowych)
def _docs_standard() -> list:
    return [
        DocumentEntry('Zał. 9 – Oświadczenie instytucji', 'ZAL_9',
                      'Do wypełnienia przez zakład pracy',
                      available_when=_firma_custom),
        DocumentEntry('Zał. 1 – Porozumienie uczelnia ↔ zakład', 'ZAL_1',
                      'Dla firm bez stałej umowy z ANS',
                      available_when=_firma_bez_umowy),
        DocumentEntry('Zał. 2 – Program praktyki', 'ZAL_2',
                      'Z danymi studenta i firmy'),
        DocumentEntry('Zał. 2a – Indywidualny Program Praktyk', 'ZAL_2A',
                      'Harmonogram efektów — student + UOPZ + ZOPZ',
                      available_when=_ma_harmonogram,
                      unavailable_reason=lambda _: 'Wymaga wypełnionego harmonogramu'),
        DocumentEntry('Zał. 3 – Karta praktyki / Skierowanie', 'ZAL_3',
                      'Z danymi studenta, firmy i ZOPZ'),
        DocumentEntry('Zał. 6 – Dziennik praktyki', 'ZAL_6',
                      'Generowany z wpisów dziennika',
                      available_when=_w_trakcie_lub_zakonczona,
                      unavailable_reason=lambda _: 'Dostępny po zatwierdzeniu praktyki'),
        _SEPARATOR('Pakiet końcowy'),
        DocumentEntry('Zał. 7 – Sprawozdanie końcowe', 'ZAL_7',
                      'Podpisuje student',
                      available_when=_zakonczona,
                      unavailable_reason=lambda _: 'Dostępny po zakończeniu praktyki'),
        DocumentEntry('Zał. 4 – Potwierdzenie efektów uczenia się', 'ZAL_4',
                      'Podpisuje ZOPZ + UOPZ',
                      available_when=_zakonczona,
                      unavailable_reason=lambda _: 'Dostępny po zakończeniu praktyki'),
        _SEPARATOR('Po egzaminie komisji'),
        DocumentEntry('Zał. 8 – Protokół egzaminu komisji', 'ZAL_8',
                      available_when=_oceniona,
                      unavailable_reason=lambda _: 'Dostępny po wystawieniu oceny przez UOPZ'),
        DocumentEntry('Zał. 5 – Ankieta oceny praktyki', static_key='ankieta',
                      description='Formularz anonimowej ankiety'),
    ]


def _docs_employment_own_business() -> list:
    return [
        DocumentEntry('Zał. 4b – Wniosek o zaliczenie', 'ZAL_4B',
                      'Praca etatowa / własna działalność'),
        DocumentEntry('Zał. 7a – Sprawozdanie z pracy/działalności', 'ZAL_7A',
                      'Zatwierdza przełożony/UOPZ',
                      available_when=_w_trakcie_lub_zakonczona,
                      unavailable_reason=lambda _: 'Dostępny po decyzji komisji'),
        DocumentEntry('Zał. 4a – Potwierdzenie efektów (komisja)', 'ZAL_4A',
                      '13 efektów: uzyskał / częściowo / nie',
                      available_when=_dziekan_lub_zakonczona,
                      unavailable_reason=lambda _: 'Dostępny po decyzji dziekana'),
        _SEPARATOR('Po egzaminie komisji'),
        DocumentEntry('Zał. 5 – Ankieta', static_key='ankieta'),
        DocumentEntry('Zał. 8 – Protokół egzaminu komisji', 'ZAL_8',
                      available_when=_dziekan_lub_zakonczona,
                      unavailable_reason=lambda _: 'Dostępny po decyzji dziekana'),
    ]


_DOCUMENT_POLICY: dict[str, Callable[[], list]] = {
    'STANDARD':     _docs_standard,
    'EMPLOYMENT':   _docs_employment_own_business,
    'OWN_BUSINESS': _docs_employment_own_business,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_tex_url() -> str:
    return current_app.config.get('TEX_SERVICE_URL', 'http://tex-service:5002')


def _fmt_date(value) -> str:
    if value is None:
        return ''
    if isinstance(value, (date, datetime)):
        return value.strftime('%d.%m.%Y')
    return str(value)


def _iso(value) -> str:
    if value is None:
        return ''
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


# ── Lista studentów ───────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/dokumenty')
@login_required
def dokumenty_studentow():
    strona = request.args.get('strona', 1, type=int)
    szukaj = request.args.get('szukaj', '').strip()

    q = db.session.query(Student)

    if current_user.role == RolaUzytkownika.UOPZ:
        q = q.filter(Student.supervisor_id == current_user.id)

    if szukaj:
        album_sub = db.session.query(Student.id).filter(
            Student.album_number.ilike(f'%{szukaj}%')
        ).subquery()
        q = q.filter(db.or_(
            Student.first_name.ilike(f'%{szukaj}%'),
            Student.last_name.ilike(f'%{szukaj}%'),
            Student.id.in_(album_sub),
        ))

    studenci_page = q.order_by(Student.last_name, Student.first_name)\
                     .paginate(page=strona, per_page=25, error_out=False)

    aktywne_statusy = [
        StatusZapisu.AWAITING_APPROVAL, StatusZapisu.COMMISSION_REVIEW,
        StatusZapisu.DEAN_APPROVAL, StatusZapisu.IN_PROGRESS,
    ]
    uopz_cache: dict = {}
    studenci_info = []
    for s in studenci_page.items:
        uopz = None
        if s.uopz_id:
            if s.uopz_id not in uopz_cache:
                uopz_cache[s.uopz_id] = db.session.get(Uzytkownik, s.uopz_id)
            uopz = uopz_cache[s.uopz_id]
        aktywne = db.session.query(ZapisPraktyki).filter(
            ZapisPraktyki.student_id == s.id,
            ZapisPraktyki.status.in_(aktywne_statusy),
        ).count()
        studenci_info.append({'student': s, 'uopz': uopz, 'aktywne': aktywne})

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
    student = db.session.get(Student, student_id) or abort(404)

    if current_user.role == RolaUzytkownika.UOPZ and student.supervisor_id != current_user.id:
        abort(403)

    zapisy = db.session.query(ZapisPraktyki).filter(
        ZapisPraktyki.student_id == student_id,
        ZapisPraktyki.status.in_([
            StatusZapisu.AWAITING_APPROVAL,
            StatusZapisu.COMMISSION_REVIEW,
            StatusZapisu.DEAN_APPROVAL,
            StatusZapisu.IN_PROGRESS,
            StatusZapisu.COMPLETED,
        ])
    ).order_by(ZapisPraktyki.enrolled_at.desc()).all()

    uopz = db.session.get(Uzytkownik, student.uopz_id) if student.uopz_id else None

    dokumenty_list = [
        {'zapis': z, 'docs': _resolve_docs(z), 'sciezka': _sciezka(z)}
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
    zapis = db.session.get(ZapisPraktyki, zapis_id) or abort(404)
    if current_user.role == RolaUzytkownika.UOPZ and zapis.supervisor_id != current_user.id:
        abort(403)

    template_name, filename = DOC_CONFIG[typ]
    ctx = _build_context(zapis, typ)
    try:
        response = httpx.post(
            f"{_get_tex_url()}/generuj",
            json={'template': template_name, 'context': ctx, 'filename': filename},
            timeout=60,
        )
        if response.status_code != 200:
            abort(500)
        safe_name = (
            unicodedata.normalize('NFKD', zapis.student.last_name or '')
            .encode('ascii', 'ignore').decode('ascii') or 'student'
        )
        pdf_name = template_name.replace('.tex.j2', '')
        resp = make_response(response.content)
        resp.headers['Content-Type'] = 'application/pdf'
        resp.headers['Content-Disposition'] = f'attachment; filename="{pdf_name}_{safe_name}.pdf"'
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


# ── Wewnętrzna logika dokumentów ──────────────────────────────────────────────

def _sciezka(zapis: ZapisPraktyki) -> str:
    return zapis.track_type.value if zapis.track_type else 'STANDARD'


def _build_flags(zapis: ZapisPraktyki) -> dict:
    """Zbiera wszystkie flagi stanu zapisu w jednym miejscu."""
    w_trakcie  = zapis.status == StatusZapisu.IN_PROGRESS
    zakonczona = zapis.status == StatusZapisu.COMPLETED
    return {
        'zapis_id':           str(zapis.id),
        'w_trakcie':          w_trakcie,
        'zakonczona':         zakonczona,
        'oceniona':           zakonczona and zapis.ocena_uopz is not None,
        'dziekan_zatwierdził': w_trakcie or zakonczona,
        'harmonogram_count':  db.session.query(HarmonogramPraktyki)
                                .filter_by(enrollment_id=zapis.id).count(),
        'firma_bez_umowy':    not zapis.firma or not zapis.firma.has_standing_agreement,
        'firma_custom':       not zapis.firma_id,
    }


def _resolve_docs(zapis: ZapisPraktyki) -> list[dict]:
    """Zwraca listę dokumentów dla danego zapisu na podstawie Policy Object."""
    sciezka = _sciezka(zapis)
    policy_factory = _DOCUMENT_POLICY.get(sciezka, _docs_standard)
    ctx = _build_flags(zapis)
    result = []
    for entry in policy_factory():
        if isinstance(entry, dict):          # separator
            result.append(entry)
        elif isinstance(entry, DocumentEntry):
            result.append(entry.resolve(ctx))
    return result


def _build_context(zapis: ZapisPraktyki, typ: str) -> dict:
    """Buduje kontekst dla szablonu TeX."""
    from core.modele.dziennik import WpisDziennika

    s    = zapis.student
    p    = zapis.praktyka
    uopz = zapis.uopz

    ctx = {
        'student': {
            'first_name':   s.first_name   if s else '',
            'last_name':    s.last_name    if s else '',
            'album_number': s.album_number if s else '',
            'plec':         s.gender       if s else '',
            'kierunek':     s.field_of_study or 'Informatyka' if s else '',
            'specjalnosc':  s.specialization or ''            if s else '',
            'tryb_studiow': s.study_mode   or ''              if s else '',
        },
        'praktyka': {
            'rok_uczelniany': p.academic_year    if p else '',
            'semestr':        p.semester         if p else '',
            'wymiar_godzin':  p.required_hours   if p else 160,
        },
        'firma': {
            'nazwa':   zapis.firma_nazwa,
            'adres':   zapis.firma_adres,
            'miasto':  zapis.firma_miasto,
            'nip_krs': zapis.firma_nip_krs,
        },
        'terminy': {
            'od': _fmt_date(zapis.termin_od),
            'do': _fmt_date(zapis.termin_do),
        },
        'zopz': {
            'imie_nazwisko': zapis.zopz_imie_nazwisko or '',
            'stanowisko':    zapis.zopz_stanowisko    or '',
            'telefon':       zapis.zopz_telefon       or '',
            'email':         zapis.zopz_email         or '',
        },
        'uopz': {
            'imie_nazwisko': f"{uopz.first_name} {uopz.last_name}" if uopz else '',
        },
        'uzasadnienie': zapis.uzasadnienie_sciezki or '',
        'specjalnosc':  s.specialization or '' if s else '',
        'zapis': {'sciezka': zapis.track_type},
    }

    if typ == 'ZAL_6':
        wpisy = (
            db.session.query(WpisDziennika)
            .filter_by(enrollment_id=zapis.id)
            .order_by(WpisDziennika.entry_date)
            .all()
        )
        ctx.update({
            'sciezka':          zapis.track_type.value if zapis.track_type else 'STANDARD',
            'lacznie_godzin':   zapis.lacznie_godzin or 0,
            'data_rozpoczecia': _iso(zapis.termin_od),
            'data_zakonczenia': _iso(zapis.termin_do),
            'wpisy': [
                {
                    'data':     _iso(w.data_wpisu),
                    'opis':     w.opis or '',
                    'godziny':  w.liczba_godzin or 0,
                    'efekt_nr': ', '.join(f"{e.id:02d}" for e in w.efekty_uczenia)
                                if w.efekty_uczenia else '--',
                }
                for w in wpisy
            ],
        })

    return ctx
