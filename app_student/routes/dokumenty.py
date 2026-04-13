"""
app_student/routes/dokumenty.py
"""

import io
import logging

import httpx
from flask import (Blueprint, abort, send_file, jsonify, request,
                   current_app, flash, redirect, url_for, make_response,
                   render_template)
from flask_login import login_required, current_user

from core.extensions import db, limiter
from core.modele import InternshipEnrollment, EnrollmentStatus
from core.uslugi.dokumenty import (
    DOC_CONFIG, STATIC_TEMPLATES, rozwiaz_dokumenty, buduj_kontekst,
)
from core.repozytoria import RepozytoriumZapisow

_repo_zapisow = RepozytoriumZapisow()

logger = logging.getLogger(__name__)
documents_bp = Blueprint('documents', __name__)


def _get_tex_url() -> str:
    return current_app.config.get('TEX_SERVICE_URL', 'http://tex-service:5002')


# ── Lista dokumentów studenta ─────────────────────────────────────────────────

@documents_bp.route('/moje')
@login_required
def moje_dokumenty():
    zapisy = _repo_zapisow.aktywne_dla_studenta(
        current_user.id,
        [EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMPLETED],
    )

    dokumenty_list = [
        {
            'zapis':   z,
            'sciezka': z.track_type.value if z.track_type else 'STANDARD',
            'docs':    rozwiaz_dokumenty(z),
        }
        for z in zapisy
    ]

    return render_template('dokumenty/moje_dokumenty.html', dokumenty_list=dokumenty_list)


# ── Dokumenty statyczne ───────────────────────────────────────────────────────

@documents_bp.route('/staly/<doc_key>')
@login_required
def pobierz_staly(doc_key):
    if doc_key not in STATIC_TEMPLATES:
        abort(404)
    template_name, filename = STATIC_TEMPLATES[doc_key]
    try:
        response = httpx.post(
            f"{_get_tex_url()}/generuj",
            json={'template': template_name, 'context': {}, 'filename': filename},
            timeout=30,
        )
        if response.status_code == 200:
            pdf_response = make_response(response.content)
            pdf_response.headers['Content-Type'] = 'application/pdf'
            pdf_response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return pdf_response
        flash('Błąd generowania dokumentu.', 'error')
    except Exception as e:
        flash(f'Błąd połączenia z serwisem PDF: {str(e)}', 'error')
    return redirect(url_for('documents.moje_dokumenty'))


# ── Dokumenty dynamiczne ──────────────────────────────────────────────────────

@documents_bp.route('/dynamiczny/<uuid:zapis_id>/<typ>')
@login_required
def pobierz_dynamiczny(zapis_id, typ):
    if typ not in DOC_CONFIG:
        abort(404)

    zapis = db.session.get(InternshipEnrollment, zapis_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    template_name, filename = DOC_CONFIG[typ]
    ctx = buduj_kontekst(zapis, typ)

    try:
        response = httpx.post(
            f"{_get_tex_url()}/generuj",
            json={'template': template_name, 'context': ctx, 'filename': filename},
            timeout=60,
        )
        if response.status_code == 200:
            import unicodedata
            safe = (
                unicodedata.normalize('NFKD', zapis.student.last_name or '')
                .encode('ascii', 'ignore').decode('ascii') or 'student'
            )
            pdf_name = template_name.replace('.tex.j2', '')
            pdf_response = make_response(response.content)
            pdf_response.headers['Content-Type'] = 'application/pdf'
            pdf_response.headers['Content-Disposition'] = f'attachment; filename="{pdf_name}_{safe}.pdf"'
            return pdf_response
        flash(f'Błąd generowania dokumentu: {response.text[:200]}', 'error')
    except Exception as e:
        flash(f'Błąd połączenia z serwisem PDF: {str(e)}', 'error')
    return redirect(url_for('documents.moje_dokumenty'))


@documents_bp.route('/generuj/<doc_type>', methods=['POST'])
@login_required
@limiter.limit("30 per hour")
def generuj(doc_type: str):
    if doc_type not in DOC_CONFIG:
        abort(403)

    force = request.args.get('force') == 'true'

    zapis = (
        _repo_zapisow.aktywny_dla_studenta(current_user.id, [EnrollmentStatus.IN_PROGRESS])
        or _repo_zapisow.ostatni_dla_studenta(current_user.id)
    )

    if not zapis:
        return jsonify({'error': 'Nie znaleziono zapisu na praktykę.'}), 404

    # Walidacja kompletności danych
    warnings = []
    if not (zapis.firma_nazwa or (zapis.firma and zapis.firma.nazwa)):
        warnings.append('Nazwa firmy')
    if not (zapis.firma_adres or (zapis.firma and zapis.firma.adres)):
        warnings.append('Adres firmy')
    if doc_type == 'ZAL_6' and not getattr(zapis, 'wpisy_dziennika', None):
        warnings.append('Brak wpisów w dzienniku')

    if warnings and not force:
        return jsonify({
            'requires_confirmation': True,
            'warnings': warnings,
            'message': 'Niektóre dane są puste. Dokument będzie niekompletny.',
        }), 200

    template_name, filename = DOC_CONFIG[doc_type]
    try:
        context = buduj_kontekst(zapis, doc_type)
        resp = httpx.post(
            f"{_get_tex_url()}/generuj",
            json={'template': template_name, 'context': context, 'filename': filename},
            timeout=30.0,
        )
        if resp.status_code != 200:
            err = resp.json() if 'application/json' in resp.headers.get('content-type', '') else {}
            return jsonify({'error': err.get('error', 'Błąd serwisu PDF')}), 500

        return send_file(
            io.BytesIO(resp.content),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.error("Błąd krytyczny generowania %s: %s", doc_type, e, exc_info=True)
        return jsonify({'error': str(e)}), 500
