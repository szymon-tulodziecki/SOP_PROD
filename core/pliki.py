"""
core/pliki.py
Kanoniczny moduł obsługi przesyłania plików — jeden dla całej platformy SOP.

Rejestracja w aplikacji:
    from core.pliki import stworz_blueprint_pliki, SprawdzaczDostepuPliku
    app.register_blueprint(stworz_blueprint_pliki(
        sprawdzacz=SprawdzaczDostepuPliku.tylko_student,
        url_prefix='/uploads',
    ))

Centralny punkt wszystkich zabezpieczeń: walidacja MIME, rozszerzeń,
rozmiaru, secure_filename oraz ochrona przed Path Traversal.
"""
import os
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, send_from_directory, abort, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import text

from core.modele import ZapisPraktyki, RolaUzytkownika, UploadedDocument
from core.extensions import db


# ── Polityka bezpieczeństwa plików — JEDEN punkt konfiguracji ────────────────

UPLOAD_FOLDER   = Path(__file__).parent.parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

MAX_FILE_SIZE   = 10 * 1024 * 1024  # 10 MB

# Dozwolone rozszerzenia — wyłącznie te
ALLOWED_EXTENSIONS = frozenset({
    '.pdf', '.doc', '.docx',
    '.jpg', '.jpeg', '.png',
    '.zip', '.rar',
})

# Dozwolone typy MIME — muszą odpowiadać rozszerzeniu (double-check)
ALLOWED_MIME_TYPES = frozenset({
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'image/jpeg',
    'image/png',
    'application/zip',
    'application/x-rar-compressed',
    'application/vnd.rar',
})


def _dozwolony_plik(filename: str, content_type: str) -> bool:
    """Walidacja rozszerzenia + MIME. Obie warstwy muszą być zgodne."""
    if not filename:
        return False
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS and content_type in ALLOWED_MIME_TYPES


def _sprawdz_dostep_do_zapisu(zapis: ZapisPraktyki) -> bool:
    """Domyślna kontrola dostępu: student widzi tylko swoje, admin/uopz wszystko."""
    if current_user.role == RolaUzytkownika.STUDENT:
        return zapis.student_id == current_user.id
    if current_user.role == RolaUzytkownika.UOPZ:
        return zapis.uopz_id == current_user.id
    return current_user.role == RolaUzytkownika.ADMIN


# ── Fabryka blueprintu ────────────────────────────────────────────────────────

def stworz_blueprint_pliki(
    sprawdzacz_dostepu=None,
) -> Blueprint:
    """
    Tworzy blueprint 'uploads' ze scentralizowaną logiką bezpieczeństwa.

    sprawdzacz_dostepu — callable(zapis) → bool; None = domyślna logika RBAC.
    """
    uploads_bp = Blueprint('uploads', __name__)
    _sprawdz = sprawdzacz_dostepu or _sprawdz_dostep_do_zapisu

    @uploads_bp.route('/enrollment/<uuid:enrollment_id>/upload', methods=['POST'])
    @login_required
    def upload_document(enrollment_id):
        zapis = db.session.get(ZapisPraktyki, enrollment_id)
        if not zapis or not _sprawdz(zapis):
            abort(403)

        if 'file' not in request.files:
            return jsonify({'error': 'Brak pliku'}), 400

        file          = request.files['file']
        document_type = request.form.get('document_type', '').strip()

        if not file.filename or not document_type:
            return jsonify({'error': 'Brak pliku lub typu dokumentu'}), 400

        # ── Walidacja rozmiaru ────────────────────────────────────────────────
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)

        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': f'Plik zbyt duży (max {MAX_FILE_SIZE // (1024*1024)} MB)'}), 400

        # ── Walidacja MIME + rozszerzenia ─────────────────────────────────────
        content_type = file.content_type
        if not _dozwolony_plik(file.filename, content_type):
            return jsonify({'error': 'Niedozwolony typ pliku'}), 400

        try:
            # ── secure_filename: ochrona przed Path Traversal ─────────────────
            original_filename = secure_filename(file.filename)
            if not original_filename:
                return jsonify({'error': 'Nieprawidłowa nazwa pliku'}), 400

            file_ext        = Path(original_filename).suffix.lower()
            stored_filename = f"{uuid.uuid4().hex}{file_ext}"

            # ── Zapis poza katalogiem webowym ─────────────────────────────────
            file_path = UPLOAD_FOLDER / stored_filename
            file.save(file_path)

            doc = UploadedDocument(
                enrollment_id     = enrollment_id,
                document_type     = document_type,
                original_filename = original_filename,
                stored_filename   = stored_filename,
                file_path         = str(file_path),
                file_size         = file_size,
                mime_type         = content_type,
                uploaded_by_id    = current_user.id,
            )
            db.session.add(doc)
            db.session.commit()

            return jsonify({
                'success':     True,
                'document_id': str(doc.id),
                'filename':    original_filename,
                'size':        file_size,
            })

        except Exception as e:
            if 'file_path' in locals() and Path(file_path).exists():
                Path(file_path).unlink()
            db.session.rollback()
            return jsonify({'error': f'Błąd podczas zapisywania: {str(e)}'}), 500

    @uploads_bp.route('/document/<uuid:document_id>/download')
    @login_required
    def download_document(document_id):
        doc = db.session.get(UploadedDocument, document_id)
        if not doc:
            abort(404)
        zapis = doc.enrollment
        if not _sprawdz(zapis):
            abort(403)

        file_path = Path(doc.file_path)
        if not file_path.exists():
            abort(404)

        # ── Bezpieczne wysyłanie: send_from_directory zapobiega Path Traversal ─
        return send_from_directory(
            file_path.parent, file_path.name,
            as_attachment=True,
            download_name=doc.original_filename,
            mimetype=doc.mime_type,
        )

    @uploads_bp.route('/document/<uuid:document_id>/delete', methods=['POST'])
    @login_required
    def delete_document(document_id):
        doc = db.session.get(UploadedDocument, document_id)
        if not doc:
            abort(404)
        if not _sprawdz(doc.enrollment):
            abort(403)

        try:
            file_path = Path(doc.file_path)
            if file_path.exists():
                file_path.unlink()
            db.session.delete(doc)
            db.session.commit()
            flash('Dokument został usunięty.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Błąd podczas usuwania: {str(e)}', 'danger')

        return redirect(request.referrer or url_for('dashboard.index'))

    @uploads_bp.route('/enrollment/<uuid:enrollment_id>/documents')
    @login_required
    def list_documents(enrollment_id):
        zapis = db.session.get(ZapisPraktyki, enrollment_id)
        if not zapis or not _sprawdz(zapis):
            abort(403)

        docs = db.session.query(UploadedDocument)\
                 .filter_by(zapis_id=enrollment_id)\
                 .order_by(UploadedDocument.przeslano_o.desc())\
                 .all()

        return jsonify([{
            'id':                str(d.id),
            'document_type':     d.document_type,
            'original_filename': d.original_filename,
            'file_size':         d.file_size,
            'mime_type':         d.mime_type,
            'uploaded_at':       d.uploaded_at.isoformat(),
            'uploaded_by':       (f"{d.uploaded_by.first_name} {d.uploaded_by.last_name}"
                                  if d.uploaded_by else None),
            'download_url':      url_for('uploads.download_document', document_id=d.id),
            'delete_url':        url_for('uploads.delete_document',   document_id=d.id),
        } for d in docs])

    return uploads_bp
