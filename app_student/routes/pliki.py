import os
import uuid
import mimetypes
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_from_directory, abort, flash, redirect, url_for
from flask_login import login_required, current_user

from core.modele import ZapisPraktyki, RolaUzytkownika
from core.extensions import db

uploads_bp = Blueprint('uploads', __name__)

UPLOAD_FOLDER = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.zip', '.rar'}
ALLOWED_MIME_TYPES = {
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'image/jpeg',
    'image/png',
    'application/zip',
    'application/x-rar-compressed',
    'application/vnd.rar',
}


def allowed_file(filename, content_type):
    if not filename:
        return False
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS and content_type in ALLOWED_MIME_TYPES


@uploads_bp.route('/enrollment/<uuid:enrollment_id>/upload', methods=['POST'])
@login_required
def upload_document(enrollment_id):
    zapis = db.session.get(ZapisPraktyki, enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    if 'file' not in request.files:
        return jsonify({'error': 'Brak pliku'}), 400

    file          = request.files['file']
    document_type = request.form.get('document_type', '').strip()

    if not file.filename or not document_type:
        return jsonify({'error': 'Brak pliku lub typu dokumentu'}), 400

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        return jsonify({'error': f'Plik zbyt duży. Maksymalny rozmiar: {MAX_FILE_SIZE // (1024*1024)}MB'}), 400

    content_type = file.content_type
    if not allowed_file(file.filename, content_type):
        return jsonify({'error': 'Niedozwolony typ pliku'}), 400

    try:
        original_filename = secure_filename(file.filename)
        file_ext          = Path(original_filename).suffix.lower()
        stored_filename   = f"{uuid.uuid4().hex}{file_ext}"
        file_path         = UPLOAD_FOLDER / stored_filename
        file.save(file_path)

        from sqlalchemy import text
        result = db.session.execute(text("""
            INSERT INTO uploaded_documents (
                enrollment_id, document_type, original_filename, stored_filename,
                file_path, file_size, mime_type, uploaded_by_id
            ) VALUES (
                :enrollment_id, :document_type, :original_filename, :stored_filename,
                :file_path, :file_size, :mime_type, :uploaded_by_id
            ) RETURNING id
        """), {
            'enrollment_id':    str(enrollment_id),
            'document_type':    document_type,
            'original_filename': original_filename,
            'stored_filename':  stored_filename,
            'file_path':        str(file_path),
            'file_size':        file_size,
            'mime_type':        content_type,
            'uploaded_by_id':   str(current_user.id),
        })
        doc_id = result.fetchone()[0]
        db.session.commit()

        return jsonify({'success': True, 'document_id': str(doc_id),
                        'filename': original_filename, 'size': file_size})

    except Exception as e:
        if 'file_path' in locals() and file_path.exists():
            file_path.unlink()
        db.session.rollback()
        return jsonify({'error': f'Błąd podczas zapisywania: {str(e)}'}), 500


@uploads_bp.route('/document/<uuid:document_id>/download')
@login_required
def download_document(document_id):
    from sqlalchemy import text
    result = db.session.execute(text("""
        SELECT ud.*, ie.student_id
        FROM uploaded_documents ud
        JOIN internship_enrollments ie ON ud.enrollment_id = ie.id
        WHERE ud.id = :document_id
    """), {'document_id': str(document_id)}).fetchone()

    if not result:
        abort(404)
    if str(result.student_id) != str(current_user.id):
        abort(403)

    file_path = Path(result.file_path)
    if not file_path.exists():
        abort(404)

    return send_from_directory(file_path.parent, file_path.name,
                               as_attachment=True, download_name=result.original_filename,
                               mimetype=result.mime_type)


@uploads_bp.route('/document/<uuid:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    from sqlalchemy import text
    result = db.session.execute(text("""
        SELECT ud.*, ie.student_id
        FROM uploaded_documents ud
        JOIN internship_enrollments ie ON ud.enrollment_id = ie.id
        WHERE ud.id = :document_id
    """), {'document_id': str(document_id)}).fetchone()

    if not result or str(result.student_id) != str(current_user.id):
        abort(404)

    try:
        file_path = Path(result.file_path)
        if file_path.exists():
            file_path.unlink()
        db.session.execute(text("DELETE FROM uploaded_documents WHERE id = :document_id"),
                           {'document_id': str(document_id)})
        db.session.commit()
        flash('Dokument został usunięty.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Błąd podczas usuwania dokumentu: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('dashboard.index'))


@uploads_bp.route('/enrollment/<uuid:enrollment_id>/documents')
@login_required
def list_documents(enrollment_id):
    zapis = db.session.get(ZapisPraktyki, enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    from sqlalchemy import text
    results = db.session.execute(text("""
        SELECT ud.*, u.first_name, u.last_name
        FROM uploaded_documents ud
        LEFT JOIN users u ON ud.uploaded_by_id = u.id
        WHERE ud.enrollment_id = :enrollment_id
        ORDER BY ud.uploaded_at DESC
    """), {'enrollment_id': str(enrollment_id)}).fetchall()

    return jsonify([{
        'id':                str(row.id),
        'document_type':     row.document_type,
        'original_filename': row.original_filename,
        'file_size':         row.file_size,
        'mime_type':         row.mime_type,
        'uploaded_at':       row.uploaded_at.isoformat(),
        'uploaded_by':       f"{row.first_name} {row.last_name}" if row.first_name else None,
        'download_url':      url_for('uploads.download_document', document_id=row.id),
        'delete_url':        url_for('uploads.delete_document', document_id=row.id),
    } for row in results])
