import os
import uuid
import mimetypes
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_from_directory, abort, flash, redirect, url_for
from flask_login import login_required, current_user

from app_student.models import ZapisPraktyki, RolaUzytkownika
from app_student.extensions import db

uploads_bp = Blueprint('uploads', __name__)

# Model dla uploadowanych dokumentów (używamy taki sam jak w admin)
class UploadedDocument:
    """Temporary class for document uploads - same structure as in admin"""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

# Konfiguracja uploadów
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
    'application/vnd.rar'
}

def allowed_file(filename, content_type):
    """Sprawdza czy plik ma dozwolone rozszerzenie i typ MIME"""
    if not filename:
        return False
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS and content_type in ALLOWED_MIME_TYPES


@uploads_bp.route('/enrollment/<uuid:enrollment_id>/upload', methods=['POST'])
@login_required
def upload_document(enrollment_id):
    """Upload dokumentu dla zgłoszenia - wersja dla studentów"""

    # Sprawdź czy zgłoszenie istnieje i należy do studenta
    zapis = db.session.get(ZapisPraktyki, enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    # Sprawdź czy przesłano plik
    if 'file' not in request.files:
        return jsonify({'error': 'Brak pliku'}), 400

    file = request.files['file']
    document_type = request.form.get('document_type', '').strip()

    if not file.filename or not document_type:
        return jsonify({'error': 'Brak pliku lub typu dokumentu'}), 400

    # Sprawdź rozmiar pliku
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        return jsonify({'error': f'Plik zbyt duży. Maksymalny rozmiar: {MAX_FILE_SIZE // (1024*1024)}MB'}), 400

    # Sprawdź typ pliku
    content_type = file.content_type
    if not allowed_file(file.filename, content_type):
        return jsonify({'error': 'Niedozwolony typ pliku'}), 400

    try:
        # Generuj bezpieczną nazwę pliku
        original_filename = secure_filename(file.filename)
        file_ext = Path(original_filename).suffix.lower()
        stored_filename = f"{uuid.uuid4().hex}{file_ext}"

        # Zapisz plik na dysk
        file_path = UPLOAD_FOLDER / stored_filename
        file.save(file_path)

        # Zapisz metadane w bazie danych używając raw SQL (bo nie mamy modelu UploadedDocument w app_student)
        from sqlalchemy import text

        insert_sql = text("""
            INSERT INTO uploaded_documents (
                enrollment_id, document_type, original_filename, stored_filename,
                file_path, file_size, mime_type, uploaded_by_id
            ) VALUES (
                :enrollment_id, :document_type, :original_filename, :stored_filename,
                :file_path, :file_size, :mime_type, :uploaded_by_id
            ) RETURNING id
        """)

        result = db.session.execute(insert_sql, {
            'enrollment_id': str(enrollment_id),
            'document_type': document_type,
            'original_filename': original_filename,
            'stored_filename': stored_filename,
            'file_path': str(file_path),
            'file_size': file_size,
            'mime_type': content_type,
            'uploaded_by_id': str(current_user.id)
        })

        doc_id = result.fetchone()[0]
        db.session.commit()

        return jsonify({
            'success': True,
            'document_id': str(doc_id),
            'filename': original_filename,
            'size': file_size
        })

    except Exception as e:
        # Usuń plik z dysku jeśli wystąpił błąd
        if 'file_path' in locals() and file_path.exists():
            file_path.unlink()

        db.session.rollback()
        return jsonify({'error': f'Błąd podczas zapisywania: {str(e)}'}), 500


@uploads_bp.route('/document/<uuid:document_id>/download')
@login_required
def download_document(document_id):
    """Pobieranie dokumentu - wersja dla studentów"""

    from sqlalchemy import text

    # Znajdź dokument używając raw SQL
    query_sql = text("""
        SELECT ud.*, ie.student_id
        FROM uploaded_documents ud
        JOIN internship_enrollments ie ON ud.enrollment_id = ie.id
        WHERE ud.id = :document_id
    """)

    result = db.session.execute(query_sql, {'document_id': str(document_id)}).fetchone()

    if not result:
        abort(404)

    # Sprawdź czy dokument należy do aktualnego studenta
    if str(result.student_id) != str(current_user.id):
        abort(403)

    # Sprawdź czy plik istnieje na dysku
    file_path = Path(result.file_path)
    if not file_path.exists():
        abort(404, "Plik nie został znaleziony na dysku")

    return send_from_directory(
        file_path.parent,
        file_path.name,
        as_attachment=True,
        download_name=result.original_filename,
        mimetype=result.mime_type
    )


@uploads_bp.route('/document/<uuid:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    """Usuwanie dokumentu - wersja dla studentów"""

    from sqlalchemy import text

    # Znajdź dokument i sprawdź właściciela
    query_sql = text("""
        SELECT ud.*, ie.student_id
        FROM uploaded_documents ud
        JOIN internship_enrollments ie ON ud.enrollment_id = ie.id
        WHERE ud.id = :document_id
    """)

    result = db.session.execute(query_sql, {'document_id': str(document_id)}).fetchone()

    if not result or str(result.student_id) != str(current_user.id):
        abort(404)

    try:
        # Usuń plik z dysku
        file_path = Path(result.file_path)
        if file_path.exists():
            file_path.unlink()

        # Usuń wpis z bazy
        delete_sql = text("DELETE FROM uploaded_documents WHERE id = :document_id")
        db.session.execute(delete_sql, {'document_id': str(document_id)})
        db.session.commit()

        flash('Dokument został usunięty.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Błąd podczas usuwania dokumentu: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('dashboard.index'))


@uploads_bp.route('/enrollment/<uuid:enrollment_id>/documents')
@login_required
def list_documents(enrollment_id):
    """API - lista dokumentów dla zgłoszenia - wersja dla studentów"""

    # Sprawdź czy zgłoszenie należy do studenta
    zapis = db.session.get(ZapisPraktyki, enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    from sqlalchemy import text

    query_sql = text("""
        SELECT ud.*, u.first_name, u.last_name
        FROM uploaded_documents ud
        LEFT JOIN users u ON ud.uploaded_by_id = u.id
        WHERE ud.enrollment_id = :enrollment_id
        ORDER BY ud.uploaded_at DESC
    """)

    results = db.session.execute(query_sql, {'enrollment_id': str(enrollment_id)}).fetchall()

    return jsonify([{
        'id': str(row.id),
        'document_type': row.document_type,
        'original_filename': row.original_filename,
        'file_size': row.file_size,
        'mime_type': row.mime_type,
        'uploaded_at': row.uploaded_at.isoformat(),
        'uploaded_by': f"{row.first_name} {row.last_name}" if row.first_name else None,
        'download_url': url_for('uploads.download_document', document_id=row.id),
        'delete_url': url_for('uploads.delete_document', document_id=row.id)
    } for row in results])