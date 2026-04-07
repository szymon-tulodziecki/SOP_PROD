import os
import uuid
import mimetypes
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_from_directory, abort, flash, redirect, url_for
from flask_login import login_required, current_user

from core.modele import ZapisPraktyki, DokumentPrzeslany, Uzytkownik, RolaUzytkownika
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

        doc = DokumentPrzeslany(
            zapis_id=enrollment_id,
            typ_dokumentu=document_type,
            oryginalna_nazwa=original_filename,
            zapisana_nazwa=stored_filename,
            sciezka_pliku=str(file_path),
            rozmiar_pliku=file_size,
            typ_mime=content_type,
            przeslane_przez_id=current_user.id,
        )
        db.session.add(doc)
        db.session.commit()

        return jsonify({'success': True, 'document_id': str(doc.id),
                        'filename': original_filename, 'size': file_size})

    except Exception as e:
        if 'file_path' in locals() and file_path.exists():
            file_path.unlink()
        db.session.rollback()
        return jsonify({'error': f'Błąd podczas zapisywania: {str(e)}'}), 500


@uploads_bp.route('/document/<uuid:document_id>/download')
@login_required
def download_document(document_id):
    doc = db.session.get(DokumentPrzeslany, document_id)
    if not doc or not doc.zapis:
        abort(404)
    if str(doc.zapis.student_id) != str(current_user.id):
        abort(403)

    file_path = Path(doc.sciezka_pliku)
    if not file_path.exists():
        abort(404)

    return send_from_directory(file_path.parent, file_path.name,
                               as_attachment=True, download_name=doc.oryginalna_nazwa,
                               mimetype=doc.typ_mime)


@uploads_bp.route('/document/<uuid:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    doc = db.session.get(DokumentPrzeslany, document_id)
    if not doc or not doc.zapis:
        abort(404)
    if str(doc.zapis.student_id) != str(current_user.id):
        abort(404)

    try:
        file_path = Path(doc.sciezka_pliku)
        if file_path.exists():
            file_path.unlink()
        db.session.delete(doc)
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

    results = (
        db.session.query(DokumentPrzeslany, Uzytkownik)
        .outerjoin(Uzytkownik, DokumentPrzeslany.przeslane_przez_id == Uzytkownik.id)
        .filter(DokumentPrzeslany.zapis_id == enrollment_id)
        .order_by(DokumentPrzeslany.przeslano_o.desc())
        .all()
    )

    payload = []
    for doc, user in results:
        uploaded_by = None
        if user is not None:
            uploaded_by = f"{user.imie} {user.nazwisko}".strip() or None

        payload.append({
            'id':                str(doc.id),
            'document_type':     doc.typ_dokumentu,
            'original_filename': doc.oryginalna_nazwa,
            'file_size':         doc.rozmiar_pliku,
            'mime_type':         doc.typ_mime,
            'uploaded_at':       doc.przeslano_o.isoformat() if doc.przeslano_o else None,
            'uploaded_by':       uploaded_by,
            'download_url':      url_for('uploads.download_document', document_id=doc.id),
            'delete_url':        url_for('uploads.delete_document', document_id=doc.id),
        })

    return jsonify(payload)
