from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import SelectField, StringField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

from core.repozytoria import UserRepository

user_repository = UserRepository()

UOPZ_LABEL = 'Opiekun uczelniany (UOPZ)'
EMAIL_EXISTS_ERROR = 'Konto z tym e-mailem już istnieje.'
ALBUM_EXISTS_ERROR = 'Student z tym nr albumu już istnieje.'


class StudentForm(FlaskForm):
    first_name = StringField('Imię', validators=[DataRequired(), Length(max=100)])
    last_name = StringField('Nazwisko', validators=[DataRequired(), Length(max=100)])
    email = StringField('E-mail', validators=[DataRequired(), Email(), Length(max=255)])
    album_number = StringField('Nr albumu', validators=[DataRequired(), Length(max=20)])
    gender = SelectField(
        'Płeć',
        choices=[('', '--- Wybierz ---'), ('M', 'Mężczyzna'), ('K', 'Kobieta')],
        validators=[Optional()],
    )
    field_of_study = StringField('Kierunek studiów', validators=[Optional(), Length(max=100)])
    specialization = StringField('Specjalność', validators=[Optional(), Length(max=100)])
    study_mode = SelectField(
        'Tryb studiów',
        choices=[('', '--- Wybierz ---'), ('stacjonarne', 'Stacjonarne'), ('niestacjonarne', 'Niestacjonarne')],
        validators=[Optional()],
    )
    uopz_id = SelectField(UOPZ_LABEL, choices=[], validators=[DataRequired(message='Wybierz opiekuna UOPZ.')])

    def validate_email(self, field):
        user = user_repository.find_by_email(field.data.lower().strip())
        if user:
            raise ValidationError(EMAIL_EXISTS_ERROR)

    def validate_album_number(self, field):
        student = user_repository.find_student_by_album(field.data.strip())
        if student:
            raise ValidationError(ALBUM_EXISTS_ERROR)


class StudentEditForm(StudentForm):
    def __init__(self, user_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_id = user_id

    def validate_email(self, field):
        user = user_repository.find_by_email(field.data.lower().strip())
        if user and str(user.id) != str(self._user_id):
            raise ValidationError(EMAIL_EXISTS_ERROR)

    def validate_album_number(self, field):
        student = user_repository.find_student_by_album(field.data.strip())
        if student and str(student.id) != str(self._user_id):
            raise ValidationError(ALBUM_EXISTS_ERROR)


class StaffForm(FlaskForm):
    first_name = StringField('Imię', validators=[DataRequired(), Length(max=100)])
    last_name = StringField('Nazwisko', validators=[DataRequired(), Length(max=100)])
    email = StringField('E-mail', validators=[DataRequired(), Email(), Length(max=255)])
    role = SelectField('Rola', choices=[
        ('UOPZ', UOPZ_LABEL),
        ('ADMIN', 'Administrator'),
    ], validators=[DataRequired()])

    def validate_email(self, field):
        user = user_repository.find_by_email(field.data.lower().strip())
        if user:
            raise ValidationError(EMAIL_EXISTS_ERROR)


class CsvImportForm(FlaskForm):
    file = FileField('Plik CSV', validators=[
        DataRequired(),
        FileAllowed(['csv'], 'Tylko pliki CSV.'),
    ])
    uopz_id = SelectField(UOPZ_LABEL, choices=[], validators=[DataRequired(message='Wybierz opiekuna UOPZ.')])


class CompanyForm(FlaskForm):
    name = StringField('Nazwa firmy', validators=[DataRequired(), Length(max=255)])
    address = StringField('Adres', validators=[Optional(), Length(max=255)])
    city = StringField('Miasto', validators=[Optional(), Length(max=100)])
    vat_number = StringField('NIP/KRS', validators=[Optional(), Length(max=50)])


class InternshipForm(FlaskForm):
    academic_year = StringField('Rok uczelniany', validators=[DataRequired(), Length(max=9)])
    semester = SelectField('Semestr', choices=[
        ('zimowy', 'Zimowy'),
        ('letni', 'Letni'),
    ], validators=[DataRequired()])
    required_hours = StringField('Wymiar godzin (h)', validators=[DataRequired()])

    def validate_academic_year(self, field):
        import re
        if not re.fullmatch(r'\d{4}/\d{4}', field.data or ''):
            raise ValidationError('Podaj rok w formacie RRRR/RRRR (np. 2025/2026).')
        first_year, second_year = int(field.data[:4]), int(field.data[5:])
        if second_year != first_year + 1:
            raise ValidationError('Drugi rok musi być o 1 większy od pierwszego (np. 2025/2026).')

    def validate_required_hours(self, field):
        try:
            value = int(field.data)
        except (ValueError, TypeError):
            raise ValidationError('Podaj liczbę całkowitą.')
        if value <= 0:
            raise ValidationError('Wymiar godzin musi być większy od zera.')
