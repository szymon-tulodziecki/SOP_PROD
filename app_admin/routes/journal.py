"""Widoki administracyjnego monitorowania dzienników."""

import io
from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user

from core.extensions import db
from core.i18n import t
from core.models import UserRole
from core.repositories import EnrollmentRepository, JournalRepository
from core.auth import roles_required
from core.services.journal import JournalService
from core.services.tex_client import TexServiceError, generuj_pdf

journal_bp = Blueprint("journal", __name__)

_repo_enrollments = EnrollmentRepository()
_repo_entries = JournalRepository()


def _uopz_can_access(enrollment) -> bool:
    if current_user.role != UserRole.UOPZ:
        return True
    if enrollment.supervisor_id == current_user.id:
        return True
    return getattr(enrollment.student, "supervisor_id", None) == current_user.id


@journal_bp.route("/", methods=["GET"], endpoint="lista_dziennikow")
@roles_required(UserRole.ADMIN, UserRole.UOPZ, UserRole.DYREKTOR)
def journal_list():
    search_query = request.args.get("szukaj", "").strip()
    page = request.args.get("strona", 1, type=int)
    supervisor_id = current_user.id if current_user.role == UserRole.UOPZ else None

    paginated_enrollments = _repo_enrollments.w_trakcie_strona(
        szukaj=search_query, supervisor_id=supervisor_id, strona=page
    )
    stats = _repo_entries.statystyki_dla_zapisow([z.id for z in paginated_enrollments.items])

    rows = []
    today = date.today()
    for enrollment in paginated_enrollments.items:
        path_val = (
            enrollment.path_type.value
            if hasattr(enrollment.path_type, "value")
            else str(enrollment.path_type)
        )
        if path_val != "STANDARD":
            continue

        last_entry_date, entry_count = stats.get(enrollment.id, (None, 0))
        alert = False
        if last_entry_date:
            alert = JournalService.count_working_days(last_entry_date, today) > 3

        rows.append(
            {
                "zapis": enrollment,
                "liczba_wpisow": entry_count,
                "ostatni_wpis": last_entry_date,
                "alert": alert,
            }
        )

    return render_template(
        "journal/lista.html", rows=rows, paginated_enrollments=paginated_enrollments
    )


@journal_bp.route("/zapis/<uuid:id>", methods=["GET"], endpoint="dziennik_zapisu")
@roles_required(UserRole.ADMIN, UserRole.UOPZ, UserRole.DYREKTOR)
def enrollment_journal(id):
    from datetime import date as _date

    enrollment = _repo_enrollments.znajdz_po_id(id) or abort(404)
    if not _uopz_can_access(enrollment):
        abort(403)

    def _parse_date(key):
        val = request.args.get(key, "").strip()
        try:
            return _date.fromisoformat(val) if val else None
        except ValueError:
            return None

    date_from = _parse_date("od")
    date_to = _parse_date("do")

    entries = _repo_entries.get_by_enrollment(
        id, descending=True, start_date=date_from, end_date=date_to
    )
    gaps = JournalService.detect_gaps(entries)
    total_hours = sum(e.duration_hours for e in entries)
    return render_template(
        "journal/dziennik.html",
        zapis=enrollment,
        entries=entries,
        gaps=gaps,
        total_hours=total_hours,
        data_od=date_from,
        data_do=date_to,
    )


@journal_bp.route(
    "/zapis/<uuid:id>/wpis/<uuid:wpis_id>/komentarz", methods=["POST"], endpoint="komentarz_wpisu"
)
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def entry_comment(id, wpis_id):
    """Zapisuje (lub czyści) komentarz opiekuna praktyki przy wpisie dziennika."""
    enrollment = _repo_enrollments.znajdz_po_id(id) or abort(404)
    if not _uopz_can_access(enrollment):
        abort(403)

    entry = _repo_entries.znajdz_po_id(wpis_id)
    if entry is None or entry.enrollment_id != enrollment.id:
        abort(404)

    comment = request.form.get("komentarz", "").strip()
    entry.supervisor_comment = comment or None
    db.session.commit()

    if comment:
        flash(t("Komentarz do wpisu został zapisany."), "success")
    else:
        flash(t("Komentarz do wpisu został usunięty."), "success")
    return redirect(url_for("journal.dziennik_zapisu", id=enrollment.id))


@journal_bp.route("/zapis/<uuid:id>/pdf", methods=["GET"])
@roles_required(UserRole.ADMIN, UserRole.UOPZ, UserRole.DYREKTOR)
def pdf_dziennik(id):
    enrollment = _repo_enrollments.znajdz_po_id(id) or abort(404)
    if not _uopz_can_access(enrollment):
        abort(403)
    try:
        from core.services.documents import build_context

        context = build_context(enrollment, "ZAL_6")
        pdf = generuj_pdf("zal6_dziennik.tex.j2", context, timeout=90.0)
        filename = f"dziennik_{enrollment.student.last_name}_{enrollment.student.first_name}.pdf"
        return send_file(
            io.BytesIO(pdf),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )
    except TexServiceError:
        abort(503)
    except Exception:
        current_app.logger.exception("PDF dziennik generation failed for %s", id)
        abort(500)


lista_dziennikow = journal_list
dziennik_zapisu = enrollment_journal
