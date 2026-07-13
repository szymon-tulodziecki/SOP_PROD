"""app_student/routes/harmonogram.py

Harmonogram efektów uczenia się (Zał. 2a) wypełniany przez studenta
pod koniec praktyki — edytowalny w statusie IN_PROGRESS, po zakończeniu
tylko do odczytu.
"""

import uuid

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm

from core.extensions import db
from core.i18n import t
from core.models import EnrollmentStatus, InternshipSchedule
from core.presenters import schedule_summary
from core.repositories.internships import EnrollmentRepository
from core.repositories.outcomes import OutcomeRepository

harmonogram_bp = Blueprint("harmonogram", __name__)

_repo_zapisow = EnrollmentRepository()
_repo_efektow = OutcomeRepository()


def _aktywny_zapis_standard():
    zapis = _repo_zapisow.aktywny_dla_studenta(
        current_user.id, [EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMPLETED]
    )
    if not zapis:
        return None
    path = zapis.path_type.value if zapis.path_type else "STANDARD"
    return zapis if path == "STANDARD" else None


def _wiersze_z_formularza(efekty, enrollment_id) -> list[InternshipSchedule]:
    wiersze = []
    for e in efekty:
        dzial = request.form.get(f"dzial_{e.id}", "").strip()
        prace = request.form.get(f"prace_{e.id}", "").strip()
        try:
            dni = int(request.form.get(f"dni_{e.id}", "0") or 0)
        except (TypeError, ValueError):
            dni = 0
        if not (dzial and prace):
            continue
        wiersze.append(
            InternshipSchedule(
                id=uuid.uuid4(),
                enrollment_id=enrollment_id,
                learning_outcome_id=e.id,
                department_name=dzial,
                example_tasks=prace,
                days_count=dni,
            )
        )
    return wiersze


def _prefill_z_bazy(zapis) -> dict[str, dict]:
    return {
        str(h.learning_outcome_id): {
            "dzial": h.department_name or "",
            "prace": h.example_tasks or "",
            "dni": h.days_count or "",
        }
        for h in zapis.schedule
    }


@harmonogram_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    zapis = _aktywny_zapis_standard()
    if not zapis:
        abort(404)

    edytowalny = zapis.status == EnrollmentStatus.IN_PROGRESS
    efekty = _repo_efektow.wszystkie()
    csrf_form = FlaskForm()

    if request.method == "POST":
        if not edytowalny or not csrf_form.validate_on_submit():
            abort(403)
        _repo_zapisow.usun_harmonogram(zapis.id)
        _repo_zapisow.zapisz_harmonogram(_wiersze_z_formularza(efekty, zapis.id))
        db.session.commit()
        flash(t("Harmonogram został zapisany."), "success")
        return redirect(url_for("harmonogram.index"))

    harmonogram_dict = {h.learning_outcome_id: h for h in zapis.schedule}
    return render_template(
        "harmonogram/index.html",
        zapis=zapis,
        efekty=efekty,
        harmonogram=_prefill_z_bazy(zapis),
        podsumowanie=schedule_summary(efekty, harmonogram_dict),
        edytowalny=edytowalny,
        csrf_form=csrf_form,
    )
