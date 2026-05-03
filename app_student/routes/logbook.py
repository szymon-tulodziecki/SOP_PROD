import uuid
from datetime import date

from flask import Blueprint, abort, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectMultipleField, TextAreaField
from wtforms.validators import DataRequired, ValidationError
from wtforms.widgets import ListWidget, CheckboxInput

from sqlalchemy.exc import IntegrityError

from core.models import JournalEntry, EnrollmentStatus
from core.extensions import db
from core.repositories import EnrollmentRepository, OutcomeRepository, JournalRepository
from app_student.services import LogbookEntryDTO

_repo_zapisow = EnrollmentRepository()
_repo_efektow = OutcomeRepository()
_repo_wpisow  = JournalRepository()

logbook_bp = Blueprint('logbook', __name__)

_ROUTE_INDEX  = 'logbook.index'
_TPL_NOWY_WPIS = 'dziennik/nowy_wpis.html'


class JournalEntryForm(FlaskForm):
    entry_date    = StringField('Data', validators=[DataRequired()])
    hours_count = StringField('Liczba godzin (1–8)', validators=[DataRequired()])
    description          = TextAreaField('Opis wykonanych prac', validators=[DataRequired()])
    outcome_ids    = SelectMultipleField(
        'Efekty uczenia się',
        validators=[DataRequired(message='Wybierz co najmniej jeden learning_outcome uczenia się.')],
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput(),
    )

    def validate_hours_count(self, pole):
        try:
            val = int(pole.data)
        except (ValueError, TypeError):
            raise ValidationError('Podaj liczbę całkowitą.')
        if val < 1 or val > 8:
            raise ValidationError('Maksymalnie 8 godzin dziennie (regulamin ANS).')

    def validate_entry_date(self, pole):
        try:
            date.fromisoformat(pole.data)
        except ValueError:
            raise ValidationError('Nieprawidłowy format daty.')

    def populate_to_model(self, model_instance):
        model_instance.entry_date = date.fromisoformat(self.entry_date.data)
        model_instance.duration_hours = int(self.hours_count.data)
        model_instance.description = self.description.data.strip()
        model_instance.learning_outcomes = _repo_efektow.po_ids([int(i) for i in self.outcome_ids.data])
        return model_instance


def _aktywny_zapis():
    return _repo_zapisow.aktywny_dla_studenta(current_user.id, [
        EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMMISSION_REVIEW,
        EnrollmentStatus.DIRECTOR_APPROVAL, EnrollmentStatus.COMPLETED,
    ])


@logbook_bp.route('/', methods=['GET'])
@login_required
def index():
    zapis = _aktywny_zapis()
    
    # Jeśli student nie ma aktywnego zapisu, szukamy jakiegokolwiek innego (np. zakończonego)
    if not zapis:
        jakikolwiek = _repo_zapisow.pierwszy_dla_studenta(current_user.id)
        # Zwracamy puste wpisy, żeby szablon się nie wysypał
        return render_template('dziennik/index.html', zapis=None, wpisy=[], jakikolwiek=jakikolwiek, csrf_form=FlaskForm())

    def _parse_date(key):
        val = request.args.get(key, '').strip()
        try:
            return date.fromisoformat(val) if val else None
        except ValueError:
            return None

    data_od = _parse_date('od')
    data_do = _parse_date('do')

    wpisy = [
        LogbookEntryDTO.from_model(entry)
        for entry in _repo_wpisow.get_by_enrollment(zapis.id, start_date=data_od, end_date=data_do)
    ]
    liczba_wpisow_ogolem, godziny_ogolem = _repo_wpisow.statystyki_dla_zapisu(zapis.id)
    csrf_form = FlaskForm()
    entries_progress_percent = min(int(liczba_wpisow_ogolem / 120 * 100), 100)
    return render_template('dziennik/index.html', zapis=zapis, wpisy=wpisy,
                           jakikolwiek=zapis, csrf_form=csrf_form,
                           data_od=data_od, data_do=data_do,
                           liczba_wpisow_ogolem=liczba_wpisow_ogolem,
                           godziny_ogolem=godziny_ogolem,
                           entries_progress_percent=entries_progress_percent)


@logbook_bp.route('/nowy', methods=['GET', 'POST'])
@login_required
def nowy_wpis():
    zapis = _aktywny_zapis()
    if not zapis:
        flash('Nie masz aktywnej praktyki. Skontaktuj się z opiekunem.', 'danger')
        return redirect(url_for(_ROUTE_INDEX))

    efekty = _repo_efektow.wszystkie()
    efekty_opisy = {str(e.id): f'{e.code}: {e.description}' for e in efekty}
    form = JournalEntryForm()
    form.outcome_ids.choices = [
        (str(e.id), e.description)
        for e in efekty
    ]

    if form.validate_on_submit():
        data = date.fromisoformat(form.entry_date.data)
        duplikat = _repo_wpisow.znajdz_duplikat(zapis.id, data)
        if duplikat:
            flash('Wpis na ten dzień już istnieje. Możesz go edytować.', 'danger')
            return render_template(_TPL_NOWY_WPIS, form=form, zapis=zapis, efekty_opisy=efekty_opisy)

        godziny = int(form.hours_count.data)
        wymagane = zapis.internship.required_hours
        zalogowane = sum(w.duration_hours for w in _repo_wpisow.get_by_enrollment(zapis.id))
        if zalogowane + godziny > wymagane:
            pozostalo = wymagane - zalogowane
            if pozostalo <= 0:
                flash(f'Osiągnięto wymagany limit {wymagane} h. Nie można dodać więcej wpisów.', 'danger')
            else:
                flash(f'Możesz dodać maksymalnie {pozostalo} h (limit: {wymagane} h). Zmniejsz liczbę godzin.', 'danger')
            return render_template(_TPL_NOWY_WPIS, form=form, zapis=zapis, efekty_opisy=efekty_opisy)
        wpis = JournalEntry(
            id               = uuid.uuid4(),
            enrollment_id    = zapis.id,
        )
        form.populate_to_model(wpis)
        _repo_wpisow.zapisz(wpis)
        try:
            db.session.commit()
        except IntegrityError:
            # Race: another tab/request inserted the same date between our check and insert.
            db.session.rollback()
            flash('Wpis na ten dzień już istnieje. Możesz go edytować.', 'danger')
            return render_template(_TPL_NOWY_WPIS, form=form, zapis=zapis, efekty_opisy=efekty_opisy)
        flash(f'Wpis z dnia {data.strftime("%d.%m.%Y")} został dodany ({godziny} h).', 'success')
        return redirect(url_for(_ROUTE_INDEX))

    if request.method == 'GET':
        form.entry_date.data = date.today().isoformat()

    return render_template(_TPL_NOWY_WPIS, form=form, zapis=zapis, efekty_opisy=efekty_opisy)


@logbook_bp.route('/edytuj/<uuid:wpis_id>', methods=['GET', 'POST'])
@login_required
def edytuj_wpis(wpis_id):
    wpis = _repo_wpisow.znajdz_po_id(wpis_id)
    if not wpis:
        abort(404)

    zapis = _repo_zapisow.znajdz_po_id(wpis.enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(403)

    efekty = _repo_efektow.wszystkie()
    efekty_opisy = {str(e.id): f'{e.code}: {e.description}' for e in efekty}
    form = JournalEntryForm()
    form.outcome_ids.choices = [
        (str(e.id), e.description)
        for e in efekty
    ]

    if form.validate_on_submit():
        form.populate_to_model(wpis)
        db.session.commit()
        flash('Wpis został zaktualizowany.', 'success')
        return redirect(url_for(_ROUTE_INDEX))

    if request.method == 'GET':
        form.entry_date.data    = wpis.entry_date.isoformat()
        form.hours_count.data = str(wpis.duration_hours)
        form.description.data          = wpis.description
        form.outcome_ids.data    = [str(e.id) for e in wpis.learning_outcomes]

    return render_template(_TPL_NOWY_WPIS, form=form, zapis=zapis, edycja=True, wpis=wpis, efekty_opisy=efekty_opisy)


@logbook_bp.route('/usun/<uuid:wpis_id>', methods=['POST'])
@login_required
def usun_wpis(wpis_id):
    wpis = _repo_wpisow.znajdz_po_id(wpis_id)
    if not wpis:
        abort(404)
    zapis = _repo_zapisow.znajdz_po_id(wpis.enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(403)
    _repo_wpisow.usun(wpis)
    db.session.commit()
    flash('Wpis został usunięty.', 'success')
    return redirect(url_for(_ROUTE_INDEX))
