"""app_student/routes/agreements_public.py

Publiczny formularz porozumienia dla osoby upoważnionej z zakładu pracy.

Dostęp bez logowania — autoryzacją jest unikalny token z e-maila
(256 bitów entropii, w bazie tylko SHA-256). Link wygasa po terminie
ważności albo po wypełnieniu formularza.
"""

from flask import Blueprint, render_template
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from core.extensions import db, limiter
from core.i18n import t, lazy_t
from core.models import AgreementStatus
from core.services import notifications as noty
from core.services.agreements import AgreementService

agreements_public_bp = Blueprint("porozumienie", __name__)

_TPL_WYNIK = "porozumienie/wynik.html"


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

    form = AgreementFillForm()
    if form.validate_on_submit():
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
    )
