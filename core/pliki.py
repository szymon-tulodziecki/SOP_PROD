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
import httpx
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, Response, abort, url_for
from flask_login import login_required, current_user

import logging

from core.modele import InternshipEnrollment, UserRole, UploadedDocument
from core.extensions import db, limiter

logger = logging.getLogger(__name__)
from core.szyfrowanie import zaszyfruj_strumieniowo, odszyfruj_strumieniowo
from core.repozytoria import EnrollmentRepository, StudentDocumentRepository

_repo_enrollments = EnrollmentRepository()
_repo_docs        = StudentDocumentRepository()


# ── Fileserver ────────────────────────────────────────────────────────────────

FILESERVER_URL = os.environ.get('FILESERVER_URL', 'http://fileserver:5003')
FILESERVER_KEY = os.environ.get('FILESERVER_API_KEY', '')


def _fs_headers():
    return {'X-API-Key': FILESERVER_KEY}


def _fs_put(filename: str, data) -> None:
    """Wysyła plik na fileserver. data może być bytes lub iteratorem bajtów."""
    r = httpx.put(f'{FILESERVER_URL}/files/{filename}', content=data, headers=_fs_headers(), timeout=30)
    r.raise_for_status()


def _fs_get(filename: str) -> bytes:
    r = httpx.get(f'{FILESERVER_URL}/files/{filename}', headers=_fs_headers(), timeout=30)
    r.raise_for_status()
    return r.content


def _fs_get_stream(filename: str):
    """Zwraca otwarty kontekst httpx do strumieniowego pobrania zaszyfrowanego pliku."""
    return httpx.stream('GET', f'{FILESERVER_URL}/files/{filename}',
                        headers=_fs_headers(), timeout=30)


def _fs_delete(filename: str) -> None:
    r = httpx.delete(f'{FILESERVER_URL}/files/{filename}', headers=_fs_headers(), timeout=10)
    if r.status_code != 404:
        r.raise_for_status()

MAX_FILE_SIZE   = 10 * 1024 * 1024  # 10 MB

# Dozwolone rozszerzenia — wyłącznie te
ALLOWED_EXTENSIONS = frozenset({
    '.pdf', '.doc', '.docx',
    '.jpg', '.jpeg', '.png',
    '.zip', '.rar',
})

# Dozwolone typy MIME deklarowane przez klienta (pierwsza warstwa)
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

# Magic bytes → akceptowane typy rzeczywiste (druga warstwa, niefałszowalna)
# python-magic zwraca te wartości dla danych binarnych odczytanych z pliku.
_MAGIC_ALLOWED: frozenset[str] = frozenset({
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/zip',           # .docx/.xlsx są ZIP-em wewnętrznie — OK
    'image/jpeg',
    'image/png',
    'application/x-rar-compressed',
    'application/vnd.rar',
    'application/x-rar',
})


def _dozwolony_plik(filename: str, content_type: str) -> bool:
    """Warstwa 1: walidacja rozszerzenia + nagłówka HTTP Content-Type."""
    if not filename:
        return False
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS and content_type in ALLOWED_MIME_TYPES


class MagicBytesError(RuntimeError):
    """Rzucany gdy weryfikacja magic bytes jest niemożliwa do przeprowadzenia."""


def _weryfikuj_magic_bytes(raw_bytes: bytes) -> bool:
    """Warstwa 2: weryfikacja rzeczywistego formatu przez analizę magic bytes.

    Używa python-magic (libmagic), która analizuje sygnaturę binarną pliku
    niezależnie od rozszerzenia i nagłówka HTTP — odporna na spoofing.

    Fail-Closed: jeśli libmagic jest niedostępna lub rzuci błąd, funkcja
    propaguje wyjątek zamiast przepuszczać plik. Upload jest wtedy odrzucany
    z HTTP 500, co zapobiega przemycaniu plików przez awarię walidatora.
    """
    try:
        import magic
    except ImportError as exc:
        raise MagicBytesError(
            "python-magic (libmagic) jest niedostępna — weryfikacja binarna niemożliwa."
        ) from exc

    try:
        detected = magic.from_buffer(raw_bytes[:4096], mime=True)
    except Exception as exc:
        raise MagicBytesError(
            f"Błąd analizy magic bytes: {exc}"
        ) from exc

    return detected in _MAGIC_ALLOWED


def _sprawdz_dostep_do_zapisu(zapis: InternshipEnrollment) -> bool:
    """Domyślna kontrola dostępu: student widzi tylko swoje, admin/uopz/komisja/dyrektor wszystko."""
    if current_user.role == UserRole.STUDENT:
        return zapis.student_id == current_user.id
    if current_user.role == UserRole.UOPZ:
        return zapis.supervisor_id == current_user.id
    return current_user.role in (UserRole.ADMIN, UserRole.KOMISJA, UserRole.DYREKTOR)


# ── Przetwarzanie uploadu ─────────────────────────────────────────────────────

def _przetworz_plik(file, document_type: str, enrollment_id, user_id) -> UploadedDocument:
    """Waliduje, szyfruje i wysyła plik na fileserver; zwraca niezapisany UploadedDocument."""
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        raise ValueError(f'Plik zbyt duży (max {MAX_FILE_SIZE // (1024 * 1024)} MB)')
    if not _dozwolony_plik(file.filename, file.content_type):
        raise ValueError('Niedozwolony typ pliku')

    original_filename = secure_filename(file.filename)
    if not original_filename:
        raise ValueError('Nieprawidłowa nazwa pliku')

    file_ext        = Path(original_filename).suffix.lower()
    stored_filename = f"{uuid.uuid4().hex}{file_ext}"

    header = file.read(4096)
    if not _weryfikuj_magic_bytes(header):   # raises MagicBytesError on unavailability
        raise ValueError('Niedozwolony format pliku (weryfikacja binarna)')

    def _chunks():
        yield header
        while chunk := file.read(64 * 1024):
            yield chunk

    _fs_put(stored_filename, zaszyfruj_strumieniowo(_chunks()))

    return UploadedDocument(
        enrollment_id     = enrollment_id,
        document_type     = document_type,
        original_filename = original_filename,
        stored_filename   = stored_filename,
        file_path         = stored_filename,
        file_size         = file_size,
        mime_type         = file.content_type,
        uploaded_by_id    = user_id,
    )


# ── Handlery blueprintu (poza fabryką — redukuje cognitive complexity) ────────

def _handle_upload(enrollment_id, sprawdz):
    zapis = _repo_enrollments.znajdz_po_id(enrollment_id)
    if not zapis or not sprawdz(zapis):
        abort(403)
    if 'file' not in request.files:
        return jsonify({'error': 'Brak pliku'}), 400
    file          = request.files['file']
    document_type = request.form.get('document_type', '').strip()
    if not file.filename or not document_type:
        return jsonify({'error': 'Brak pliku lub typu dokumentu'}), 400
    try:
        doc = _przetworz_plik(file, document_type, enrollment_id, current_user.id)
    except MagicBytesError as exc:
        logger.error("Magic bytes check failed: %s", exc)
        return jsonify({'error': 'Weryfikacja formatu pliku chwilowo niedostępna.'}), 503
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'error': f'Błąd podczas zapisywania: {str(exc)}'}), 500
    try:
        _repo_docs.zapisz(doc)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({'error': f'Błąd podczas zapisywania: {str(exc)}'}), 500
    return jsonify({'success': True, 'document_id': str(doc.id),
                    'filename': doc.original_filename, 'size': doc.file_size})


def _handle_download(document_id, sprawdz):
    doc = _repo_docs.znajdz_po_id(document_id)
    if not doc:
        abort(404)
    if not doc.enrollment or not sprawdz(doc.enrollment):
        abort(403)
    try:
        encrypted = _fs_get(doc.file_path)
    except httpx.HTTPStatusError as e:
        abort(404 if e.response.status_code == 404 else 500)
    except Exception:
        abort(500)
    plain = b''.join(odszyfruj_strumieniowo(iter([encrypted])))
    return Response(plain, mimetype=doc.mime_type, headers={
        'Content-Disposition': f'attachment; filename="{doc.original_filename}"',
        'X-Content-Type-Options': 'nosniff',
    })


def _handle_delete(document_id, sprawdz):
    doc = _repo_docs.znajdz_po_id(document_id)
    if not doc:
        return jsonify({'error': 'Nie znaleziono dokumentu'}), 404
    if not doc.enrollment or not sprawdz(doc.enrollment):
        abort(403)
    try:
        _fs_delete(doc.file_path)
        doc.is_deleted = True
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


def _handle_list(enrollment_id, sprawdz):
    zapis = _repo_enrollments.znajdz_po_id(enrollment_id)
    if not zapis or not sprawdz(zapis):
        abort(403)
    docs = _repo_docs.dokumenty_zapisu_posortowane(enrollment_id)
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


# ── Fabryka blueprintu ────────────────────────────────────────────────────────

def stworz_blueprint_pliki(sprawdzacz_dostepu=None) -> Blueprint:
    """Tworzy blueprint 'uploads' ze scentralizowaną logiką bezpieczeństwa."""
    uploads_bp = Blueprint('uploads', __name__)
    _sprawdz = sprawdzacz_dostepu or _sprawdz_dostep_do_zapisu

    @uploads_bp.route('/enrollment/<uuid:enrollment_id>/upload', methods=['POST'])
    @login_required
    @limiter.limit("30 per hour")
    def upload_document(enrollment_id):
        return _handle_upload(enrollment_id, _sprawdz)

    @uploads_bp.route('/document/<uuid:document_id>/download', methods=['GET'])
    @login_required
    def download_document(document_id):
        return _handle_download(document_id, _sprawdz)

    @uploads_bp.route('/document/<uuid:document_id>/delete', methods=['POST'])
    @login_required
    def delete_document(document_id):
        return _handle_delete(document_id, _sprawdz)

    @uploads_bp.route('/enrollment/<uuid:enrollment_id>/documents', methods=['GET'])
    @login_required
    def list_documents(enrollment_id):
        return _handle_list(enrollment_id, _sprawdz)

    return uploads_bp
