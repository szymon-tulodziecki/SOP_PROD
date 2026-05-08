"""
app_student/routes/documents.py
"""

import io
import logging

import httpx
from flask import (Blueprint, abort, send_file, jsonify, request,
                   current_app, flash, redirect, url_for, make_response,
                   render_template)
from flask_login import login_required, current_user

from core.extensions import limiter
from core.models import EnrollmentStatus
from core.services.documents import (
    DOC_CONFIG,
    STATIC_TEMPLATES,
    resolve_documents as resolve_documents,
    build_context,
    validate_completeness,
)
from core.repositories import EnrollmentRepository

_enrollment_repository = EnrollmentRepository()

logger = logging.getLogger(__name__)
documents_bp = Blueprint('documents', __name__)

_MIME_PDF = 'application/pdf'


def _get_tex_url() -> str:
    return current_app.config['TEX_SERVICE_URL']


# ── Lista dokumentów studenta ─────────────────────────────────────────────────

@documents_bp.route('/moje', methods=['GET'])
@login_required
def my_documents():
    enrollments = _enrollment_repository.aktywne_dla_studenta(
        current_user.id,
        [EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMPLETED],
    )

    documents_list = [
        {
            'enrollment': enrollment,
            'path_type': enrollment.path_type.value if enrollment.path_type else 'STANDARD',
            'docs': resolve_documents(enrollment),
        }
        for enrollment in enrollments
    ]

    return render_template('dokumenty/moje_dokumenty.html', documents_list=documents_list)


# ── Dokumenty statyczne ───────────────────────────────────────────────────────

@documents_bp.route('/staly/<doc_key>', methods=['GET'])
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
            pdf_response.headers['Content-Type'] = _MIME_PDF
            pdf_response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return pdf_response
        flash('Błąd generowania dokumentu.', 'error')
    except httpx.HTTPError as exc:
        logger.error("tex-service unreachable for static doc %s: %s", doc_key, exc)
        flash('Błąd połączenia z serwisem PDF. Spróbuj ponownie później.', 'error')
    return redirect(url_for('documents.my_documents'))


# ── Dokumenty dynamiczne ──────────────────────────────────────────────────────

@documents_bp.route('/dynamiczny/<uuid:enrollment_id>/<doc_type>', methods=['GET'])
@login_required
def download_dynamic(enrollment_id, doc_type):
    if doc_type not in DOC_CONFIG:
        abort(404)

    enrollment = _enrollment_repository.znajdz_po_id(enrollment_id)
    if not enrollment or enrollment.student_id != current_user.id:
        abort(404)

    template_name, filename = DOC_CONFIG[doc_type]
    context = build_context(enrollment, doc_type)

    try:
        response = httpx.post(
            f"{_get_tex_url()}/generuj",
            json={'template': template_name, 'context': context, 'filename': filename},
            timeout=60,
        )
        if response.status_code == 200:
            import unicodedata
            from urllib.parse import quote
            pdf_name = template_name.replace('.tex.j2', '')
            full_filename = f"{pdf_name}_{enrollment.student.last_name or 'student'}.pdf"
            ascii_fallback = (
                unicodedata.normalize('NFKD', full_filename)
                .encode('ascii', 'ignore')
                .decode('ascii')
                .strip()
                or 'dokument.pdf'
            )
            utf8_filename = quote(full_filename, safe='')
            pdf_response = make_response(response.content)
            pdf_response.headers['Content-Type'] = _MIME_PDF
            pdf_response.headers['Content-Disposition'] = (
                f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_filename}"
            )
            return pdf_response
        logger.warning("tex-service returned %s for doc %s", response.status_code, doc_type)
        flash('Błąd generowania dokumentu. Spróbuj ponownie później.', 'error')
    except httpx.HTTPError as exc:
        logger.error("tex-service unreachable for doc %s: %s", doc_type, exc)
        flash('Błąd połączenia z serwisem PDF. Spróbuj ponownie później.', 'error')
    return redirect(url_for('documents.my_documents'))


@documents_bp.route('/generuj/<doc_type>', methods=['POST'])
@login_required
@limiter.limit("30 per hour")
def generuj(doc_type: str):
    if doc_type not in DOC_CONFIG:
        abort(403)

    payload = request.get_json(silent=True) or {}
    force = payload.get('force') is True

    enrollment = (
        _enrollment_repository.aktywny_dla_studenta(current_user.id, [EnrollmentStatus.IN_PROGRESS])
        or _enrollment_repository.ostatni_dla_studenta(current_user.id)
    )

    if not enrollment:
        return jsonify({'error': 'Nie znaleziono zapisu na praktykę.'}), 404

    warnings = validate_completeness(enrollment, doc_type)

    if warnings and not force:
        return jsonify({
            'requires_confirmation': True,
            'warnings': warnings,
            'message': 'Niektóre dane są puste. Dokument będzie niekompletny.',
        }), 200

    template_name, filename = DOC_CONFIG[doc_type]
    try:
        context = build_context(enrollment, doc_type)
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
            mimetype=_MIME_PDF,
            as_attachment=True,
            download_name=filename,
        )
    except httpx.HTTPError as exc:
        logger.error("tex-service unreachable for %s: %s", doc_type, exc)
        return jsonify({'error': 'Serwis PDF jest niedostępny.'}), 502
    except Exception:
        logger.exception("Nieoczekiwany błąd generowania %s", doc_type)
        return jsonify({'error': 'Wewnętrzny błąd serwera.'}), 500
