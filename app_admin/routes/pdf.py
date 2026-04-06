"""
app_admin/routes/pdf.py

Blueprint Flask do pobierania wygenerowanych PDF-ów.
Rejestracja w app_admin/__init__.py:
    from routes.pdf import pdf_bp
    app.register_blueprint(pdf_bp)
"""

import io
import sys
import os

from flask import Blueprint, send_file, abort, current_app
from flask_login import login_required, current_user

# Dodaj tex_engine do ścieżki Pythona (gdy uruchamiasz z app_admin/)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tex_engine.pdf_service import pdf_service
from tex_engine.compiler import TexCompilationError
from core.models import Praktyka, RolaUzytkownika

pdf_bp = Blueprint("pdf", __name__, url_prefix="/pdf")


def _get_praktyka_or_403(praktyka_id: str):
    """
    Pobiera praktykę z bazy i sprawdza prawa dostępu.
    Student widzi tylko własne praktyki, UOPZ/ADMIN widzą wszystkie.
    """
    praktyka = Praktyka.query.get_or_404(praktyka_id)

    if current_user.role == RolaUzytkownika.STUDENT:
        if str(praktyka.student_id) != str(current_user.id):
            abort(403)
    elif current_user.role == RolaUzytkownika.UOPZ:
        if str(praktyka.uopz_id) != str(current_user.id):
            abort(403)
    # ADMIN widzi wszystko

    return praktyka


@pdf_bp.route("/dziennik/<uuid:praktyka_id>")
@login_required
def download_dziennik(praktyka_id):
    """GET /pdf/dziennik/<uuid> → Załącznik 6 – Dziennik praktyki zawodowej."""
    praktyka = _get_praktyka_or_403(str(praktyka_id))
    try:
        pdf_bytes = pdf_service.get_dziennik(praktyka)
    except TexCompilationError as e:
        current_app.logger.error("Błąd kompilacji PDF (dziennik): %s\nLog:\n%s", e, e.log)
        abort(500, description="Błąd generowania dziennika. Skontaktuj się z administratorem.")

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"dziennik_{praktyka.student.album_number}.pdf",
    )


@pdf_bp.route("/efekty/<uuid:praktyka_id>")
@login_required
def download_efekty(praktyka_id):
    """GET /pdf/efekty/<uuid> → Załącznik 4 – Potwierdzenie efektów uczenia."""
    praktyka = _get_praktyka_or_403(str(praktyka_id))
    try:
        pdf_bytes = pdf_service.get_efekty(praktyka)
    except TexCompilationError as e:
        current_app.logger.error("Błąd kompilacji PDF (efekty): %s\nLog:\n%s", e, e.log)
        abort(500, description="Błąd generowania dokumentu efektów.")

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"efekty_{praktyka.student.album_number}.pdf",
    )


@pdf_bp.route("/sprawozdanie/<uuid:praktyka_id>")
@login_required
def download_sprawozdanie(praktyka_id):
    """
    GET /pdf/sprawozdanie/<uuid> → Załącznik 7 – Sprawozdanie studenta.
    Pobiera treść sprawozdania z JSONB kolumny tasks_scope lub
    z request.json jeśli wysłane POST-em.
    """
    praktyka = _get_praktyka_or_403(str(praktyka_id))

    # Treść sprawozdania trzymana w kolumnie JSONB tasks_scope
    tresc = praktyka.tasks_scope or {}

    try:
        pdf_bytes = pdf_service.get_sprawozdanie(praktyka, tresc)
    except TexCompilationError as e:
        current_app.logger.error("Błąd kompilacji PDF (sprawozdanie): %s\nLog:\n%s", e, e.log)
        abort(500, description="Błąd generowania sprawozdania.")

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sprawozdanie_{praktyka.student.album_number}.pdf",
    )
