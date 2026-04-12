import uuid
import csv
import io
import datetime
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from core.modele import Uzytkownik, Student
from core.extensions import db


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
        q = db.session.query(Uzytkownik).filter_by(email=pole.data.lower().strip()).first()
        if q:
            raise ValidationError('Konto z tym e-mailem już istnieje.')

    def validate_numer_albumu(self, pole):
        q = db.session.query(Student).filter_by(album_number=pole.data.strip()).first()
        if q:
            raise ValidationError('Student z tym nr albumu już istnieje.')


class FormularzEdycjiStudenta(FormularzStudenta):
    def __init__(self, uzytkownik_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._uid = uzytkownik_id

    def validate_email(self, pole):
        q = db.session.query(Uzytkownik).filter_by(email=pole.data.lower().strip()).first()
        if q and str(q.id) != str(self._uid):
            raise ValidationError('Konto z tym e-mailem już istnieje.')

    def validate_numer_albumu(self, pole):
        q = db.session.query(Student).filter_by(album_number=pole.data.strip()).first()
        if q and str(q.id) != str(self._uid):
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
        q = db.session.query(Uzytkownik).filter_by(email=pole.data.lower().strip()).first()
        if q:
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


