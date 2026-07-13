"""app_student/routes/agreements_public.py

Publiczny formularz porozumienia dla osoby upoważnionej z zakładu pracy.

Dostęp bez logowania — autoryzacją jest unikalny token z e-maila
(256 bitów entropii, w bazie tylko SHA-256). Link wygasa po terminie
ważności albo po wypełnieniu formularza.
"""

import uuid

from flask import Blueprint, render_template, request
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from core.extensions import db, limiter
from core.i18n import t, lazy_t
from core.models import AgreementStatus, InternshipSchedule
from core.repositories.internships import EnrollmentRepository
from core.repositories.outcomes import OutcomeRepository
from core.services import notifications as noty
from core.services.agreements import AgreementService

agreements_public_bp = Blueprint("porozumienie", __name__)

_TPL_WYNIK = "porozumienie/wynik.html"
_repo_zapisow = EnrollmentRepository()
_repo_efektow = OutcomeRepository()


class AgreementFillForm(FlaskForm):
    signer_name = StringField(
        lazy_t("Imię i nazwisko osoby reprezentującej zakład pracy"),
        validators=[DataRequired(message=lazy_t("Podaj imię i nazwisko.")), Length(max=255)],
    )
    signer_position = StringField(
        lazy_t("Stanowisko"),
        validators=[Optional(), Length(max=255)],
    )
    company_notes = TextAreaField(
        lazy_t("Uwagi do porozumienia (opcjonalnie)"),
        validators=[Optional(), Length(max=2000)],
    )

    def validate_signer_name(self, field):
        parts = (field.data or "").strip().split()
        if len(parts) < 2:
            raise ValidationError(t("Podaj imię i nazwisko (co najmniej dwa wyrazy)."))
        if any(ch.isdigit() for ch in field.data):
            raise ValidationError(t("Imię i nazwisko nie może zawierać cyfr."))


def _harmonogram_z_formularza(efekty) -> dict[str, dict]:
    return {
        str(e.id): {
            "dzial": request.form.get(f"dzial_{e.id}", ""),
            "prace": request.form.get(f"prace_{e.id}", ""),
            "dni": request.form.get(f"dni_{e.id}", ""),
        }
        for e in efekty
    }


def _wiersze_harmonogramu(efekty, enrollment_ids) -> list[InternshipSchedule]:
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
        for enrollment_id in enrollment_ids:
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


def _zapisz_harmonogram_grupy(agreement, efekty) -> None:
    """Zakład wypełnia jeden harmonogram — trafia do każdego zapisu z porozumienia."""
    enrollment_ids = [ae.enrollment_id for ae in agreement.enrollments]
    for enrollment_id in enrollment_ids:
        _repo_zapisow.usun_harmonogram(enrollment_id)
    _repo_zapisow.zapisz_harmonogram(_wiersze_harmonogramu(efekty, enrollment_ids))


def _studenci(agreement) -> list[dict]:
    wiersze = []
    for ae in agreement.enrollments:
        z = ae.enrollment
        if not z or not z.student:
            continue
        wiersze.append(
            {
                "imie_nazwisko": f"{z.student.first_name} {z.student.last_name}",
                "od": z.start_date.strftime("%d.%m.%Y") if z.start_date else "—",
                "do": z.end_date.strftime("%d.%m.%Y") if z.end_date else "—",
                "wymiar": z.internship.required_hours if z.internship else 160,
            }
        )
    return wiersze


@agreements_public_bp.route("/<token>", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def formularz(token):
    agreement = AgreementService.find_by_token(token)

    if agreement is None:
        return render_template(_TPL_WYNIK, wariant="nieaktywny"), 404
    if agreement.status == AgreementStatus.FILLED:
        return render_template(_TPL_WYNIK, wariant="wypelnione")
    if not agreement.is_open:
        return render_template(_TPL_WYNIK, wariant="nieaktywny"), 410

    efekty = _repo_efektow.wszystkie()
    form = AgreementFillForm()
    if form.validate_on_submit():
        _zapisz_harmonogram_grupy(agreement, efekty)
        AgreementService.fill_agreement(
            agreement,
            signer_name=form.signer_name.data.strip(),
            signer_position=(form.signer_position.data or "").strip(),
            company_notes=(form.company_notes.data or "").strip(),
        )
        db.session.commit()
        noty.notify_agreement_filled(agreement)
        return render_template(_TPL_WYNIK, wariant="dziekujemy")

    if not form.signer_name.data:
        form.signer_name.data = agreement.recipient_name
        form.signer_position.data = agreement.recipient_position

    return render_template(
        "porozumienie/formularz.html",
        porozumienie=agreement,
        studenci=_studenci(agreement),
        form=form,
        efekty=efekty,
        harmonogram=_harmonogram_z_formularza(efekty) if request.method == "POST" else {},
    )
