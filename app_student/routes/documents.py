"""
app_student/routes/documents.py
"""

import io
import logging

from flask import (Blueprint, abort, send_file, jsonify, request,
                   flash, redirect, url_for, render_template)
from flask_login import login_required, current_user

from core.extensions import limiter
from core.i18n import t
from core.models import EnrollmentStatus
from core.presenters import student_path_label
from core.services.documents import (
    DOC_CONFIG,
    STATIC_TEMPLATES,
    resolve_documents as resolve_documents,
    build_context,
    validate_completeness,
)
from core.services.tex_client import TexServiceError, dyspozycja_pdf, generuj_pdf, odpowiedz_pdf
from core.repositories import EnrollmentRepository

_enrollment_repository = EnrollmentRepository()

logger = logging.getLogger(__name__)
documents_bp = Blueprint('documents', __name__)

_MIME_PDF = 'application/pdf'


# ── Lista dokumentów studenta ─────────────────────────────────────────────────

@documents_bp.route('/moje', methods=['GET'])
@login_required
def my_documents():
    enrollments = _enrollment_repository.aktywne_dla_studenta(
        current_user.id,
        [EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMPLETED],
    )

    documents_list = []
    for enrollment in enrollments:
        path_type = enrollment.path_type.value if enrollment.path_type else 'STANDARD'
        firma_nazwa = enrollment.company.name if enrollment.company else enrollment.company_display_name
        documents_list.append({
            'enrollment': enrollment,
            'path_type': path_type,
            'sciezka_label': student_path_label(path_type),
            'firma_nazwa': firma_nazwa,
            'docs': resolve_documents(enrollment),
        })

    return render_template('dokumenty/moje_dokumenty.html', documents_list=documents_list)


# ── Dokumenty statyczne ───────────────────────────────────────────────────────

@documents_bp.route('/staly/<doc_key>', methods=['GET'])
@login_required
def pobierz_staly(doc_key):
    if doc_key not in STATIC_TEMPLATES:
        abort(404)
    template_name, filename = STATIC_TEMPLATES[doc_key]
    try:
        pdf = generuj_pdf(template_name, {}, filename, timeout=30)
        return odpowiedz_pdf(pdf, dyspozycja_pdf(filename))
    except TexServiceError as exc:
        logger.error("tex-service error for static doc %s: %s", doc_key, exc)
        if exc.status_code:
            flash(t('Błąd generowania dokumentu.'), 'error')
        else:
            flash(t('Błąd połączenia z serwisem PDF. Spróbuj ponownie później.'), 'error')
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
        pdf = generuj_pdf(template_name, context, filename, timeout=60)
        pdf_name = template_name.replace('.tex.j2', '')
        disposition = dyspozycja_pdf(pdf_name, enrollment.student.last_name or 'student')
        return odpowiedz_pdf(pdf, disposition)
    except TexServiceError as exc:
        if exc.status_code:
            logger.warning("tex-service returned %s for doc %s", exc.status_code, doc_type)
            flash(t('Błąd generowania dokumentu. Spróbuj ponownie później.'), 'error')
        else:
            logger.error("tex-service unreachable for doc %s: %s", doc_type, exc)
            flash(t('Błąd połączenia z serwisem PDF. Spróbuj ponownie później.'), 'error')
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
        return jsonify({'error': t('Nie znaleziono zapisu na praktykę.')}), 404

    warnings = validate_completeness(enrollment, doc_type)

    if warnings and not force:
        return jsonify({
            'requires_confirmation': True,
            'warnings': warnings,
            'message': t('Niektóre dane są puste. Dokument będzie niekompletny.'),
        }), 200

    template_name, filename = DOC_CONFIG[doc_type]
    try:
        context = build_context(enrollment, doc_type)
        pdf = generuj_pdf(template_name, context, filename, timeout=30.0)
        return send_file(
            io.BytesIO(pdf),
            mimetype=_MIME_PDF,
            as_attachment=True,
            download_name=filename,
        )
    except TexServiceError as exc:
        if exc.status_code:
            return jsonify({'error': t(exc.error_detail or 'Błąd serwisu PDF')}), 500
        logger.error("tex-service unreachable for %s: %s", doc_type, exc)
        return jsonify({'error': t('Serwis PDF jest niedostępny.')}), 502
    except Exception:
        logger.exception("Nieoczekiwany błąd generowania %s", doc_type)
        return jsonify({'error': t('Wewnętrzny błąd serwera.')}), 500
