import uuid
import csv
import io
import datetime
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from core.modele import User, Student
from core.repozytoria import RepozytoriumUzytkownikow

_repo_uzytk = RepozytoriumUzytkownikow()


# ── Formularze ────────────────────────────────────────────────────────────────

class FormularzStudenta(FlaskForm):
    imie         = StringField('Imię',      validators=[DataRequired(), Length(max=100)])
    nazwisko     = StringField('Nazwisko',  validators=[DataRequired(), Length(max=100)])
    email        = StringField('E-mail',    validators=[DataRequired(), Email(), Length(max=255)])
    numer_albumu = StringField('Nr albumu', validators=[DataRequired(), Length(max=20)])
    plec         = SelectField('Płeć', choices=[('', '--- Wybierz ---'), ('M', 'Mężczyzna'), ('K', 'Kobieta')], validators=[Optional()])
    kierunek     = StringField('Kierunek studiów', validators=[Optional(), Length(max=100)])
    specjalnosc  = StringField('Specjalność', validators=[Optional(), Length(max=100)])
    tryb_studiow = SelectField('Tryb studiów', choices=[('', '--- Wybierz ---'), ('stacjonarne', 'Stacjonarne'), ('niestacjonarne', 'Niestacjonarne')], validators=[Optional()])
    uopz_id      = SelectField('Opiekun uczelniany (UOPZ)', choices=[], validators=[DataRequired(message='Wybierz opiekuna UOPZ.')])

    def validate_email(self, pole):
        u = _repo_uzytk.znajdz_po_emailu(pole.data.lower().strip())
        if u:
            raise ValidationError('Konto z tym e-mailem już istnieje.')

    def validate_numer_albumu(self, pole):
        s = _repo_uzytk.znajdz_studenta_po_albumie(pole.data.strip())
        if s:
            raise ValidationError('Student z tym nr albumu już istnieje.')


class FormularzEdycjiStudenta(FormularzStudenta):
    def __init__(self, uzytkownik_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._uid = uzytkownik_id

    def validate_email(self, pole):
        u = _repo_uzytk.znajdz_po_emailu(pole.data.lower().strip())
        if u and str(u.id) != str(self._uid):
            raise ValidationError('Konto z tym e-mailem już istnieje.')

    def validate_numer_albumu(self, pole):
        s = _repo_uzytk.znajdz_studenta_po_albumie(pole.data.strip())
        if s and str(s.id) != str(self._uid):
            raise ValidationError('Student z tym nr albumu już istnieje.')


class FormularzPracownika(FlaskForm):
    imie     = StringField('Imię',     validators=[DataRequired(), Length(max=100)])
    nazwisko = StringField('Nazwisko', validators=[DataRequired(), Length(max=100)])
    email    = StringField('E-mail',   validators=[DataRequired(), Email(), Length(max=255)])
    rola     = SelectField('Rola', choices=[
        ('UOPZ',  'Opiekun uczelniany (UOPZ)'),
        ('ADMIN', 'Administrator'),
    ], validators=[DataRequired()])

    def validate_email(self, pole):
        u = _repo_uzytk.znajdz_po_emailu(pole.data.lower().strip())
        if u:
            raise ValidationError('Konto z tym e-mailem już istnieje.')


class FormularzImportuCSV(FlaskForm):
    plik    = FileField('Plik CSV', validators=[
        DataRequired(),
        FileAllowed(['csv'], 'Tylko pliki CSV.')
    ])
    uopz_id = SelectField('Opiekun uczelniany (UOPZ)', choices=[], validators=[DataRequired(message='Wybierz opiekuna UOPZ.')])


class FormularzFirmy(FlaskForm):
    nazwa  = StringField('Nazwa firmy', validators=[DataRequired(), Length(max=255)])
    adres  = StringField('Adres',       validators=[Optional(), Length(max=255)])
    miasto = StringField('Miasto',      validators=[Optional(), Length(max=100)])
    nip_krs = StringField('NIP/KRS',   validators=[Optional(), Length(max=50)])


class FormularzPraktyki(FlaskForm):
    rok_uczelniany = StringField('Rok uczelniany', validators=[DataRequired(), Length(max=9)])
    semestr = SelectField('Semestr', choices=[
        ('zimowy', 'Zimowy'),
        ('letni',  'Letni'),
    ], validators=[DataRequired()])
    wymiar_godzin = StringField('Wymiar godzin (h)', validators=[DataRequired()])

    def validate_rok_uczelniany(self, field):
        import re
        if not re.fullmatch(r'\d{4}/\d{4}', field.data or ''):
            raise ValidationError('Podaj rok w formacie RRRR/RRRR (np. 2025/2026).')
        rok1, rok2 = int(field.data[:4]), int(field.data[5:])
        if rok2 != rok1 + 1:
            raise ValidationError('Drugi rok musi być o 1 większy od pierwszego (np. 2025/2026).')

    def validate_wymiar_godzin(self, field):
        try:
            val = int(field.data)
        except (ValueError, TypeError):
            raise ValidationError('Podaj liczbę całkowitą.')
        if val <= 0:
            raise ValidationError('Wymiar godzin musi być większy od zera.')


