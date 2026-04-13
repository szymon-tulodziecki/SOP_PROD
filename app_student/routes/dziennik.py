import uuid
from datetime import date

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectMultipleField, TextAreaField
from wtforms.validators import DataRequired, ValidationError
from wtforms.widgets import ListWidget, CheckboxInput

from core.modele import InternshipEnrollment, JournalEntry, LearningOutcome, EnrollmentStatus
from core.extensions import db
from core.repozytoria import RepozytoriumZapisow, RepozytoriumEfektow, RepozytoriumWpisow

_repo_zapisow = RepozytoriumZapisow()
_repo_efektow = RepozytoriumEfektow()
_repo_wpisow  = RepozytoriumWpisow()

dziennik_bp = Blueprint('dziennik', __name__)


class FormularzWpisu(FlaskForm):
    data_wpisu    = StringField('Data', validators=[DataRequired()])
    liczba_godzin = StringField('Liczba godzin (1–8)', validators=[DataRequired()])
    opis          = TextAreaField('Opis wykonanych prac', validators=[DataRequired()])
    efekty_ids    = SelectMultipleField(
        'Efekty uczenia się',
        validators=[DataRequired(message='Wybierz co najmniej jeden efekt uczenia się.')],
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput(),
    )

    def validate_liczba_godzin(self, pole):
        try:
            val = int(pole.data)
        except (ValueError, TypeError):
            raise ValidationError('Podaj liczbę całkowitą.')
        if val < 1 or val > 8:
            raise ValidationError('Maksymalnie 8 godzin dziennie (regulamin ANS).')

    def validate_data_wpisu(self, pole):
        try:
            date.fromisoformat(pole.data)
        except ValueError:
            raise ValidationError('Nieprawidłowy format daty.')


def _aktywny_zapis():
    return _repo_zapisow.aktywny_dla_studenta(current_user.id, [
        EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMMISSION_REVIEW,
        EnrollmentStatus.DEAN_APPROVAL, EnrollmentStatus.COMPLETED,
    ])


@dziennik_bp.route('/')
@login_required
def index():
    zapis = _aktywny_zapis()
    
    # Jeśli student nie ma aktywnego zapisu, szukamy jakiegokolwiek innego (np. zakończonego)
    if not zapis:
        jakikolwiek = _repo_zapisow.pierwszy_dla_studenta(current_user.id)
        # Zwracamy puste wpisy, żeby szablon się nie wysypał
        return render_template('dziennik/index.html', zapis=None, wpisy=[], jakikolwiek=jakikolwiek, csrf_form=FlaskForm())

    # Jeśli jest aktywny zapis, normalnie ładujemy wpisy
    wpisy = _repo_wpisow.dla_zapisu(zapis.id)
    csrf_form = FlaskForm()
    return render_template('dziennik/index.html', zapis=zapis, wpisy=wpisy, jakikolwiek=zapis, csrf_form=csrf_form)


@dziennik_bp.route('/nowy', methods=['GET', 'POST'])
@login_required
def nowy_wpis():
    zapis = _aktywny_zapis()
    if not zapis:
        flash('Nie masz aktywnej praktyki. Skontaktuj się z opiekunem.', 'danger')
        return redirect(url_for('dziennik.index'))

    efekty = _repo_efektow.wszystkie()
    form = FormularzWpisu()
    form.efekty_ids.choices = [
        (str(e.id), f'{e.kod}: {e.description[:80]}...' if len(e.description) > 80 else f'{e.kod}: {e.description}')
        for e in efekty
    ]

    if form.validate_on_submit():
        data = date.fromisoformat(form.data_wpisu.data)
        duplikat = _repo_wpisow.znajdz_duplikat(zapis.id, data)
        if duplikat:
            flash('Wpis na ten dzień już istnieje. Możesz go edytować.', 'danger')
            return render_template('dziennik/nowy_wpis.html', form=form, zapis=zapis)

        godziny = int(form.liczba_godzin.data)
        wybrane_efekty = _repo_efektow.po_ids([int(i) for i in form.efekty_ids.data])
        wpis = JournalEntry(
            id               = uuid.uuid4(),
            enrollment_id    = zapis.id,
            entry_date       = data,
            duration_hours   = godziny,
            description      = form.opis.data.strip(),
            learning_outcomes = wybrane_efekty,
        )
        db.session.add(wpis)
        db.session.commit()
        flash(f'Wpis z dnia {data.strftime("%d.%m.%Y")} został dodany ({godziny} h).', 'success')
        return redirect(url_for('dziennik.index'))

    if request.method == 'GET':
        form.data_wpisu.data = date.today().isoformat()

    return render_template('dziennik/nowy_wpis.html', form=form, zapis=zapis)


@dziennik_bp.route('/edytuj/<uuid:wpis_id>', methods=['GET', 'POST'])
@login_required
def edytuj_wpis(wpis_id):
    wpis = db.session.get(JournalEntry, wpis_id)
    if not wpis:
        from flask import abort
        abort(404)

    zapis = db.session.get(InternshipEnrollment, wpis.enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        from flask import abort
        abort(403)

    efekty = _repo_efektow.wszystkie()
    form = FormularzWpisu()
    form.efekty_ids.choices = [
        (str(e.id), f'{e.kod}: {e.description[:80]}...' if len(e.description) > 80 else f'{e.kod}: {e.description}')
        for e in efekty
    ]

    if form.validate_on_submit():
        wpis.entry_date     = date.fromisoformat(form.data_wpisu.data)
        wpis.duration_hours = int(form.liczba_godzin.data)
        wpis.description    = form.opis.data.strip()
        wpis.efekty_uczenia = _repo_efektow.po_ids([int(i) for i in form.efekty_ids.data])
        db.session.commit()
        flash('Wpis został zaktualizowany.', 'success')
        return redirect(url_for('dziennik.index'))

    if request.method == 'GET':
        form.data_wpisu.data    = wpis.entry_date.isoformat()
        form.liczba_godzin.data = str(wpis.duration_hours)
        form.opis.data          = wpis.description
        form.efekty_ids.data    = [str(e.id) for e in wpis.efekty_uczenia]

    return render_template('dziennik/nowy_wpis.html', form=form, zapis=zapis, edycja=True, wpis=wpis)


@dziennik_bp.route('/usun/<uuid:wpis_id>', methods=['POST'])
@login_required
def usun_wpis(wpis_id):
    wpis = db.session.get(JournalEntry, wpis_id)
    if not wpis:
        from flask import abort
        abort(404)
    zapis = db.session.get(InternshipEnrollment, wpis.enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        from flask import abort
        abort(403)
    db.session.delete(wpis)
    db.session.commit()
    flash('Wpis został usunięty.', 'success')
    return redirect(url_for('dziennik.index'))