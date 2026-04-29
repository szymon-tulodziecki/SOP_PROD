import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort, send_file, current_app, Response, stream_with_context
from flask_login import login_required, current_user
from pathlib import Path

from core.modele import InternshipEnrollment, DocumentAuditLog, UserRole
from core.extensions import db, limiter
from core.autoryzacja import roles_required
from core.repozytoria import EnrollmentRepository, LogRepository
from core.uslugi.documents import build_context, sse_pdf_status
from celery_app import generate_pdf_from_template, celery

_repo_enrollments = EnrollmentRepository()
_repo_logs        = LogRepository()

import logging
logger = logging.getLogger(__name__)

documents_bp = Blueprint('documents', __name__)

DOCUMENTS = {
    'ZAL_1':  ('zal1_porozumienie.tex.j2',  'Załącznik 1 (Porozumienie)'),
    'ZAL_2a': ('zal2a_harmonogram.tex.j2',  'Załącznik 2a (Harmonogram Uczelniany)'),
    'ZAL_3':  ('zal3_skierowanie.tex.j2',   'Załącznik 3 (Skierowanie i ocena ZOPZ)'),
    'ZAL_4':  ('zal4_efekty.tex.j2',        'Załącznik 4 (Efekty Uczenia Się)'),
    'ZAL_4a': ('zal4a_komisja.tex.j2',      'Załącznik 4a (Opinia Komisji do weryfikacji)'),
    'ZAL_4b': ('zal4b_wniosek.tex.j2',      'Załącznik 4b (Wniosek o działalność gospodarczą)'),
    'ZAL_6':  ('zal6_dziennik.tex.j2',      'Załącznik 6 (Dziennik Praktyki)'),
    'ZAL_7':  ('zal7_sprawozdanie.tex.j2',  'Załącznik 7 (InternshipReport Instytucji)'),
    'ZAL_7a': ('zal7a_wniosek.tex.j2',      'Załącznik 7a (Wniosek o pracę zawodową)'),
    'ZAL_8':  ('zal8_protokol.tex.j2',      'Załącznik 8 (Protokół Egzaminacyjny)'),
    'ZAL_9':  ('zal9_zobowiazanie.tex.j2',  'Załącznik 9 (Zobowiązanie poufności)'),
}

def log_audit(enrollment_id, doc_type, action, details=""):
    _repo_logs.zapisz_log(DocumentAuditLog(
        id=uuid.uuid4(),
        user_id=current_user.id,
        enrollment_id=enrollment_id,
        document_type=doc_type,
        action=action,
        details=details
    ))
    db.session.commit()

@documents_bp.route('/zapis/<uuid:id>', methods=['GET'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def panel(id):
    enrollment = _repo_enrollments.znajdz_po_id(id) or abort(404)
    logs       = _repo_logs.ostatnie_dla_zapisu(id)
    docs       = {k: v for k, v in DOCUMENTS.items()
                  if k != 'ZAL_8' or enrollment.final_grade is not None}
    return render_template('documents/panel.html', zapis=enrollment, docs=docs, logs=logs)

@documents_bp.route('/zapis/<uuid:id>/generuj_auto/<doc_type>', methods=['POST'], endpoint='generuj_auto')
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
@limiter.limit("60 per hour")
def generate_automatic_enrollment(id, doc_type):
    enrollment = _repo_enrollments.znajdz_po_id(id) or abort(404)
    if doc_type not in DOCUMENTS:
        abort(404)

    template_name, _ = DOCUMENTS[doc_type]

    context = build_context(enrollment, doc_type)

    try:
        task = generate_pdf_from_template.delay(template_name, context, doc_type.lower())
        log_audit(enrollment.id, doc_type, 'GENERATED_AUTO', f'Wygenerowano {doc_type}')
        return jsonify({'task_id': task.id, 'status': 'PENDING'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


generuj_auto = generate_automatic_enrollment

@documents_bp.route('/status/<task_id>', methods=['GET'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def status_pdf(task_id):
    """Legacy polling endpoint — zachowany dla kompatybilności wstecznej."""
    try:
        task = celery.AsyncResult(task_id)
        if task.state == 'SUCCESS':
            return jsonify({'status': 'SUCCESS', 'download_url': url_for('documents.pobierz_pdf', task_id=task_id)})
        elif task.state == 'FAILURE':
            return jsonify({'status': 'FAILURE', 'error': str(task.info)})
        else:
            return jsonify({'status': task.state})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

_SSE_MAX_SECONDS = 30    # po tym czasie klient powinien przełączyć się na polling

@documents_bp.route('/stream/<task_id>', methods=['GET'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def stream_status(task_id):
    """Server-Sent Events — status generowania PDF."""
    def generate():
        dl_url = url_for('documents.pobierz_pdf', task_id=task_id)
        yield from sse_pdf_status(task_id, dl_url, celery, _SSE_MAX_SECONDS)

    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@documents_bp.route('/pobierz/<task_id>', methods=['GET'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def pobierz_pdf(task_id):
    try:
        task = celery.AsyncResult(task_id)
        if task.state != 'SUCCESS':
            abort(404)
        result   = task.result
        pdf_path = Path(result['path'])
        if not pdf_path.exists():
            abort(404)
        return send_file(pdf_path, mimetype='application/pdf', as_attachment=True, download_name=result['filename'])
    except Exception:
        abort(500)
