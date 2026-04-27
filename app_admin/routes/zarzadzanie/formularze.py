import uuid
import csv
import io
import datetime
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from core.modele import User, Student
from core.repozytoria import UserRepository

_repo_uzytk = UserRepository()

_LABEL_UOPZ        = _LABEL_UOPZ
_ERR_EMAIL_EXISTS  = 'Konto z tym e-mailem już istnieje.'
_ERR_ALBUM_EXISTS  = 'Student z tym nr albumu już istnieje.'


# ── Formularze ────────────────────────────────────────────────────────────────

class StudentForm(FlaskForm):
    first_name   = StringField('Imię',      validators=[DataRequired(), Length(max=100)])
    last_name    = StringField('Nazwisko',  validators=[DataRequired(), Length(max=100)])
    email        = StringField('E-mail',    validators=[DataRequired(), Email(), Length(max=255)])
    album_number = StringField('Nr albumu', validators=[DataRequired(), Length(max=20)])
    gender       = SelectField('Płeć', choices=[('', '--- Wybierz ---'), ('M', 'Mężczyzna'), ('K', 'Kobieta')], validators=[Optional()])
    field_of_study  = StringField('Kierunek studiów', validators=[Optional(), Length(max=100)])
    specialization  = StringField('Specjalność', validators=[Optional(), Length(max=100)])
    study_mode      = SelectField('Tryb studiów', choices=[('', '--- Wybierz ---'), ('stacjonarne', 'Stacjonarne'), ('niestacjonarne', 'Niestacjonarne')], validators=[Optional()])
    uopz_id         = SelectField(_LABEL_UOPZ, choices=[], validators=[DataRequired(message='Wybierz opiekuna UOPZ.')])

    def validate_email(self, field):
        u = _repo_uzytk.znajdz_po_emailu(field.data.lower().strip())
        if u:
            raise ValidationError(_ERR_EMAIL_EXISTS)

    def validate_album_number(self, field):
        s = _repo_uzytk.znajdz_studenta_po_albumie(field.data.strip())
        if s:
            raise ValidationError(_ERR_ALBUM_EXISTS)


class StudentEditForm(StudentForm):
    def __init__(self, user_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._uid = user_id

    def validate_email(self, field):
        u = _repo_uzytk.znajdz_po_emailu(field.data.lower().strip())
        if u and str(u.id) != str(self._uid):
            raise ValidationError(_ERR_EMAIL_EXISTS)

    def validate_album_number(self, field):
        s = _repo_uzytk.znajdz_studenta_po_albumie(field.data.strip())
        if s and str(s.id) != str(self._uid):
            raise ValidationError(_ERR_ALBUM_EXISTS)


class StaffForm(FlaskForm):
    first_name = StringField('Imię',     validators=[DataRequired(), Length(max=100)])
    last_name  = StringField('Nazwisko', validators=[DataRequired(), Length(max=100)])
    email      = StringField('E-mail',   validators=[DataRequired(), Email(), Length(max=255)])
    role       = SelectField('Rola', choices=[
        ('UOPZ',  _LABEL_UOPZ),
        ('ADMIN', 'Administrator'),
    ], validators=[DataRequired()])

    def validate_email(self, field):
        u = _repo_uzytk.znajdz_po_emailu(field.data.lower().strip())
        if u:
            raise ValidationError(_ERR_EMAIL_EXISTS)


class CsvImportForm(FlaskForm):
    file    = FileField('Plik CSV', validators=[
        DataRequired(),
        FileAllowed(['csv'], 'Tylko pliki CSV.')
    ])
    uopz_id = SelectField(_LABEL_UOPZ, choices=[], validators=[DataRequired(message='Wybierz opiekuna UOPZ.')])


class CompanyForm(FlaskForm):
    name       = StringField('Nazwa firmy', validators=[DataRequired(), Length(max=255)])
    address    = StringField('Adres',       validators=[Optional(), Length(max=255)])
    city       = StringField('Miasto',      validators=[Optional(), Length(max=100)])
    vat_number = StringField('NIP/KRS',     validators=[Optional(), Length(max=50)])


class InternshipForm(FlaskForm):
    academic_year  = StringField('Rok uczelniany', validators=[DataRequired(), Length(max=9)])
    semester       = SelectField('Semestr', choices=[
        ('zimowy', 'Zimowy'),
        ('letni',  'Letni'),
    ], validators=[DataRequired()])
    required_hours = StringField('Wymiar godzin (h)', validators=[DataRequired()])

    def validate_academic_year(self, field):
        import re
        if not re.fullmatch(r'\d{4}/\d{4}', field.data or ''):
            raise ValidationError('Podaj rok w formacie RRRR/RRRR (np. 2025/2026).')
        rok1, rok2 = int(field.data[:4]), int(field.data[5:])
        if rok2 != rok1 + 1:
            raise ValidationError('Drugi rok musi być o 1 większy od pierwszego (np. 2025/2026).')

    def validate_required_hours(self, field):
        try:
            val = int(field.data)
        except (ValueError, TypeError):
            raise ValidationError('Podaj liczbę całkowitą.')
        if val <= 0:
            raise ValidationError('Wymiar godzin musi być większy od zera.')


# Backward-compatible aliases (used by star-imports in sibling modules that may
# still reference the old names; remove after all call sites are updated).
FormularzStudenta      = StudentForm
FormularzEdycjiStudenta = StudentEditForm
FormularzPracownika    = StaffForm
FormularzImportuCSV    = CsvImportForm
FormularzFirmy         = CompanyForm
FormularzPraktyki      = InternshipForm
