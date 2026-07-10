"""app_admin/routes/dziekanat.py

Panel dziekanatu — porozumienia z zakładami pracy (Zał. 1).

Studenci ścieżki A pogrupowani po zakładach pracy; dziekanat zaznacza
studentów z jednego zakładu i wysyła osobie upoważnionej unikalny link
z formularzem porozumienia. Jedno porozumienie obejmuje 1..N studentów.
"""

import re
import uuid

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf import FlaskForm

from core.auth import roles_required
from core.extensions import db, limiter
from core.i18n import t
from core.models import (
    AgreementStatus,
    EnrollmentStatus,
    InternshipAgreement,
    InternshipEnrollment,
    InternshipPath,
    UserRole,
)
from core.presenters import agreement_status_badge
from core.services import notifications as noty
from core.services.agreements import AgreementService
from core.services.tex_client import TexServiceError, dyspozycja_pdf, generuj_pdf, odpowiedz_pdf

dziekanat_bp = Blueprint("dziekanat", __name__)

_ROUTE_LISTA = "dziekanat.porozumienia_lista"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Zapisy, dla których porozumienie ma sens: student złożył zgłoszenie
# ścieżki A i nie zostało ono odrzucone.
_AKTYWNE_STATUSY = (
    EnrollmentStatus.AWAITING_APPROVAL,
    EnrollmentStatus.COMMISSION_REVIEW,
    EnrollmentStatus.DIRECTOR_APPROVAL,
    EnrollmentStatus.IN_PROGRESS,
)


def _klucz_firmy(zapis) -> str:
    """Klucz grupowania: firma z bazy po id, wpisana ręcznie po nazwie+NIP."""
    if zapis.company_id:
        return f"db:{zapis.company_id}"
    nazwa = (zapis.company_display_name or "").strip().lower()
    nip = (zapis.company_display_tax_id or "").strip()
    return f"custom:{nazwa}|{nip}"


def _zapisy_do_porozumien() -> list[InternshipEnrollment]:
    zapisy = (
        db.session.query(InternshipEnrollment)
        .filter(InternshipEnrollment.path_type == InternshipPath.STANDARD)
        .filter(InternshipEnrollment.status.in_(_AKTYWNE_STATUSY))
        .all()
    )
    zapisy = [z for z in zapisy if z.company_display_name]
    pokryte = AgreementService.enrollment_ids_with_open_agreement([z.id for z in zapisy])
    return [z for z in zapisy if z.id not in pokryte]


def _grupy_po_firmach(zapisy) -> list[dict]:
    grupy: dict[str, dict] = {}
    for z in zapisy:
        klucz = _klucz_firmy(z)
        grupa = grupy.setdefault(
            klucz,
            {
                "klucz": klucz,
                "nazwa": z.company_display_name,
                "adres": z.company_display_address,
                "miasto": z.company_city,
                "nip": z.company_display_tax_id,
                "zapisy": [],
                "odbiorca_imie": "",
                "odbiorca_stanowisko": "",
                "odbiorca_email": "",
            },
        )
        grupa["zapisy"].append(z)
        # Podpowiedź odbiorcy: pierwszy student, który podał osobę upoważnioną
        if not grupa["odbiorca_imie"] and z.authorized_person:
            grupa["odbiorca_imie"] = z.authorized_person
            grupa["odbiorca_stanowisko"] = z.authorized_person_position or ""
            grupa["odbiorca_email"] = z.authorized_person_email or ""
    return sorted(grupy.values(), key=lambda g: (g["nazwa"] or "").lower())


@dziekanat_bp.route("/", methods=["GET"])
@roles_required(UserRole.ADMIN, UserRole.DZIEKANAT)
def porozumienia_lista():
    zapisy = _zapisy_do_porozumien()
    grupy = _grupy_po_firmach(zapisy)

    porozumienia = (
        db.session.query(InternshipAgreement).order_by(InternshipAgreement.created_at.desc()).all()
    )
    wiersze = [{"p": p, "badge": agreement_status_badge(p.status.value)} for p in porozumienia]
    csrf_form = FlaskForm()
    return render_template(
        "dziekanat/porozumienia.html", grupy=grupy, porozumienia=wiersze, csrf_form=csrf_form
    )


def _walidacja_wysylki(zapisy, recipient_name, recipient_email) -> str | None:
    """Zwraca komunikat błędu albo None gdy dane są poprawne."""
    if not zapisy:
        return "Zaznacz co najmniej jednego studenta."
    # Te same warunki co lista — POST nie może objąć zapisów spoza niej
    # (ścieżka B, odrzucone/szkicowe, bez zakładu pracy).
    if any(
        z.path_type != InternshipPath.STANDARD
        or z.status not in _AKTYWNE_STATUSY
        or not z.company_display_name
        for z in zapisy
    ):
        return "Część zaznaczonych zgłoszeń nie kwalifikuje się do porozumienia."
    if not recipient_name or len(recipient_name.split()) < 2:
        return "Podaj imię i nazwisko osoby upoważnionej."
    if not recipient_email or not _EMAIL_RE.fullmatch(recipient_email):
        return "Podaj poprawny adres e-mail osoby upoważnionej."
    klucze = {_klucz_firmy(z) for z in zapisy}
    if len(klucze) > 1:
        return "Wszyscy zaznaczeni studenci muszą odbywać praktykę w tym samym zakładzie pracy."
    pokryte = AgreementService.enrollment_ids_with_open_agreement([z.id for z in zapisy])
    if pokryte:
        return "Część zaznaczonych studentów ma już wysłane porozumienie."
    return None


@dziekanat_bp.route("/wyslij", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.DZIEKANAT)
@limiter.limit("30 per hour")
def wyslij_porozumienie():
    form = FlaskForm()
    if not form.validate_on_submit():
        abort(400)

    try:
        ids = [uuid.UUID(v) for v in request.form.getlist("enrollment_ids")]
    except ValueError:
        abort(400)

    zapisy = (
        (db.session.query(InternshipEnrollment).filter(InternshipEnrollment.id.in_(ids)).all())
        if ids
        else []
    )

    recipient_name = request.form.get("recipient_name", "").strip()
    recipient_position = request.form.get("recipient_position", "").strip()
    recipient_email = request.form.get("recipient_email", "").strip().lower()

    blad = _walidacja_wysylki(zapisy, recipient_name, recipient_email)
    if blad:
        flash(t(blad), "danger")
        return redirect(url_for(_ROUTE_LISTA))

    agreement, token = AgreementService.create_agreement(
        zapisy,
        recipient_name=recipient_name,
        recipient_email=recipient_email,
        recipient_position=recipient_position,
        created_by_id=current_user.id,
    )
    db.session.commit()
    noty.notify_agreement_recipient(agreement, token)

    flash(
        t(
            "Porozumienie dla {firma} ({liczba} stud.) zostało wysłane na adres {email}.",
            firma=agreement.company_name,
            liczba=len(zapisy),
            email=recipient_email,
        ),
        "success",
    )
    return redirect(url_for(_ROUTE_LISTA))


@dziekanat_bp.route("/<uuid:id>/anuluj", methods=["POST"])
@roles_required(UserRole.ADMIN, UserRole.DZIEKANAT)
def anuluj_porozumienie(id):
    form = FlaskForm()
    if not form.validate_on_submit():
        abort(400)
    agreement = db.session.get(InternshipAgreement, id) or abort(404)
    if agreement.status == AgreementStatus.CANCELLED:
        flash(t("Porozumienie jest już anulowane."), "info")
        return redirect(url_for(_ROUTE_LISTA))
    AgreementService.cancel(agreement)
    db.session.commit()
    flash(t("Porozumienie zostało anulowane — link przestał działać."), "success")
    return redirect(url_for(_ROUTE_LISTA))


def _fmt_data(value) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


@dziekanat_bp.route("/<uuid:id>/pdf", methods=["GET"])
@roles_required(UserRole.ADMIN, UserRole.DZIEKANAT)
def porozumienie_pdf(id):
    agreement = db.session.get(InternshipAgreement, id) or abort(404)

    studenci = []
    for ae in agreement.enrollments:
        z = ae.enrollment
        if not z or not z.student:
            continue
        studenci.append(
            {
                "imie": z.student.first_name,
                "nazwisko": z.student.last_name,
                "od": _fmt_data(z.start_date),
                "do": _fmt_data(z.end_date),
                "wymiar": z.internship.required_hours if z.internship else 160,
            }
        )
    if not studenci:
        flash(t("Porozumienie nie ma powiązanych studentów."), "danger")
        return redirect(url_for(_ROUTE_LISTA))

    context = {
        "porozumienie_numer": "",
        "porozumienie_data": _fmt_data(agreement.filled_at),
        "company": {"nazwa": agreement.company_name},
        "firma_upowazniony": agreement.signer_name or agreement.recipient_name,
        "studenci": studenci,
    }
    try:
        pdf = generuj_pdf("zal1_porozumienie.tex.j2", context, "zal1_porozumienie.pdf", timeout=60)
    except TexServiceError:
        abort(500)

    return odpowiedz_pdf(pdf, dyspozycja_pdf("zal1_porozumienie.pdf"))
