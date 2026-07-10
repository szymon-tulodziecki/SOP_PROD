from flask import current_app
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import SelectField, SelectMultipleField, StringField, widgets
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from core.i18n import t, lazy_t
from core.repositories import UserRepository

user_repository = UserRepository()

UOPZ_LABEL = "Opiekun uczelniany (UOPZ)"
EMAIL_EXISTS_ERROR = "Konto z tym e-mailem już istnieje."
ALBUM_EXISTS_ERROR = "Student z tym nr albumu już istnieje."


class MultiCheckboxField(SelectMultipleField):
    """SelectMultipleField wyświetlone jako lista checkboxów."""

    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


def _validate_university_domain(field):
    """Wymusza domenę uczelni (z ALLOWED_EMAIL_DOMAIN, lista po przecinku)."""
    allowed_raw = current_app.config.get("ALLOWED_EMAIL_DOMAIN") or ""
    allowed = [d.strip().lower() for d in allowed_raw.split(",") if d.strip()]
    if not allowed:
        return
    email = (field.data or "").lower().strip()
    domain = email.split("@")[-1] if "@" in email else ""
    if not any(domain == d or domain.endswith("." + d) for d in allowed):
        domeny = ", ".join("@" + d for d in allowed)
        raise ValidationError(t("E-mail musi być w domenie uczelni ({domeny}).", domeny=domeny))


class StudentForm(FlaskForm):
    first_name = StringField(lazy_t("Imię"), validators=[DataRequired(), Length(max=100)])
    last_name = StringField(lazy_t("Nazwisko"), validators=[DataRequired(), Length(max=100)])
    email = StringField(lazy_t("E-mail"), validators=[DataRequired(), Email(), Length(max=255)])
    album_number = StringField(lazy_t("Nr albumu"), validators=[DataRequired(), Length(max=20)])
    gender = SelectField(
        lazy_t("Płeć"),
        choices=[
            ("", lazy_t("--- Wybierz ---")),
            ("M", lazy_t("Mężczyzna")),
            ("F", lazy_t("Kobieta")),
        ],
        validators=[Optional()],
    )
    field_of_study = StringField(
        lazy_t("Kierunek studiów"), validators=[Optional(), Length(max=100)]
    )
    specialization = StringField(lazy_t("Specjalność"), validators=[Optional(), Length(max=100)])
    study_mode = SelectField(
        lazy_t("Tryb studiów"),
        choices=[
            ("", lazy_t("--- Wybierz ---")),
            ("full-time", lazy_t("Stacjonarne")),
            ("part-time", lazy_t("Niestacjonarne")),
        ],
        validators=[Optional()],
    )
    supervisor_id = SelectField(
        lazy_t(UOPZ_LABEL),
        choices=[],
        validators=[DataRequired(message=lazy_t("Wybierz opiekuna UOPZ."))],
    )

    def validate_email(self, field):
        _validate_university_domain(field)
        user = user_repository.find_by_email(field.data.lower().strip())
        if user:
            raise ValidationError(t(EMAIL_EXISTS_ERROR))

    def validate_album_number(self, field):
        student = user_repository.find_student_by_album(field.data.strip())
        if student:
            raise ValidationError(t(ALBUM_EXISTS_ERROR))


class StudentEditForm(StudentForm):
    def __init__(self, user_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_id = user_id

    def validate_email(self, field):
        _validate_university_domain(field)
        user = user_repository.find_by_email(field.data.lower().strip())
        if user and str(user.id) != str(self._user_id):
            raise ValidationError(t(EMAIL_EXISTS_ERROR))

    def validate_album_number(self, field):
        student = user_repository.find_student_by_album(field.data.strip())
        if student and str(student.id) != str(self._user_id):
            raise ValidationError(t(ALBUM_EXISTS_ERROR))


class StaffForm(FlaskForm):
    first_name = StringField(lazy_t("Imię"), validators=[DataRequired(), Length(max=100)])
    last_name = StringField(lazy_t("Nazwisko"), validators=[DataRequired(), Length(max=100)])
    email = StringField(lazy_t("E-mail"), validators=[DataRequired(), Email(), Length(max=255)])
    roles = MultiCheckboxField(
        lazy_t("Role w systemie"),
        choices=[
            ("UOPZ", lazy_t(UOPZ_LABEL)),
            ("KOMISJA", lazy_t("Komisja ds. praktyk")),
            ("DYREKTOR", lazy_t("Dyrektor Instytutu")),
            ("DZIEKANAT", lazy_t("Dziekanat")),
            ("ADMIN", lazy_t("Administrator")),
        ],
        validators=[DataRequired(message=lazy_t("Zaznacz co najmniej jedną rolę."))],
    )

    def validate_email(self, field):
        _validate_university_domain(field)
        user = user_repository.find_by_email(field.data.lower().strip())
        if user:
            raise ValidationError(t(EMAIL_EXISTS_ERROR))

    def validate_roles(self, field):
        selected = set(field.data or [])
        if "ADMIN" in selected and len(selected) > 1:
            raise ValidationError(t("Rola Administrator nie może być łączona z innymi rolami."))
        if "STUDENT" in selected:
            raise ValidationError(t("Rola Student nie jest dostępna w tym formularzu."))


class StaffEditForm(StaffForm):
    def __init__(self, user_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_id = user_id

    def validate_email(self, field):
        _validate_university_domain(field)
        user = user_repository.find_by_email(field.data.lower().strip())
        if user and str(user.id) != str(self._user_id):
            raise ValidationError(t(EMAIL_EXISTS_ERROR))


class CsvImportForm(FlaskForm):
    file = FileField(
        lazy_t("Plik CSV"),
        validators=[
            DataRequired(),
            FileAllowed(["csv"], lazy_t("Tylko pliki CSV.")),
        ],
    )
    supervisor_id = SelectField(
        lazy_t(UOPZ_LABEL),
        choices=[],
        validators=[DataRequired(message=lazy_t("Wybierz opiekuna UOPZ."))],
    )


class CompanyForm(FlaskForm):
    name = StringField(lazy_t("Nazwa firmy"), validators=[DataRequired(), Length(max=255)])
    address = StringField(lazy_t("Adres"), validators=[Optional(), Length(max=255)])
    city = StringField(lazy_t("Miasto"), validators=[Optional(), Length(max=100)])
    vat_number = StringField(lazy_t("NIP/KRS"), validators=[Optional(), Length(max=50)])


class InternshipForm(FlaskForm):
    academic_year = StringField(
        lazy_t("Rok uczelniany"), validators=[DataRequired(), Length(max=9)]
    )
    semester = SelectField(
        lazy_t("Semestr"),
        choices=[
            ("winter", lazy_t("Zimowy")),
            ("summer", lazy_t("Letni")),
        ],
        validators=[DataRequired()],
    )
    required_hours = StringField(lazy_t("Wymiar godzin (h)"), validators=[DataRequired()])

    def validate_academic_year(self, field):
        import re

        if not re.fullmatch(r"\d{4}/\d{4}", field.data or ""):
            raise ValidationError(t("Podaj rok w formacie RRRR/RRRR (np. 2025/2026)."))
        first_year, second_year = int(field.data[:4]), int(field.data[5:])
        if second_year != first_year + 1:
            raise ValidationError(
                t("Drugi rok musi być o 1 większy od pierwszego (np. 2025/2026).")
            )

    def validate_required_hours(self, field):
        try:
            value = int(field.data)
        except (ValueError, TypeError):
            raise ValidationError(t("Podaj liczbę całkowitą."))
        if value <= 0:
            raise ValidationError(t("Wymiar godzin musi być większy od zera."))
