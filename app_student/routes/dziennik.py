import uuid
import io
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, send_file
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, TextAreaField
from wtforms.validators import DataRequired, ValidationError

from app_student.models import ZapisPraktyki, WpisDziennika, EfektUczenia, StatusZapisu
from app_student.extensions import db


dziennik_bp = Blueprint('dziennik', __name__)


class FormularzWpisu(FlaskForm):
    data_wpisu    = StringField('Data', validators=[DataRequired()])
    liczba_godzin = StringField('Liczba godzin (1–8)', validators=[DataRequired()])
    opis          = TextAreaField('Opis wykonanych prac', validators=[DataRequired()])
    efekt_id      = SelectField('Efekt uczenia się', validators=[DataRequired()])

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
    return db.session.query(ZapisPraktyki).filter(
        ZapisPraktyki.student_id == current_user.id,
        ZapisPraktyki.status == StatusZapisu.IN_PROGRESS,
    ).first()


@dziennik_bp.route('/')
@login_required
def index():
    zapis = _aktywny_zapis()
    if not zapis:
        jakikolwiek = db.session.query(ZapisPraktyki).filter_by(student_id=current_user.id).first()
        return render_template('dziennik/index.html', zapis=None, wpisy=[], jakikolwiek=jakikolwiek)

    wpisy = db.session.query(WpisDziennika).filter_by(enrollment_id=zapis.id).order_by(WpisDziennika.entry_date.desc()).all()
    return render_template('dziennik/index.html', zapis=zapis, wpisy=wpisy, jakikolwiek=zapis)


@dziennik_bp.route('/nowy', methods=['GET', 'POST'])
@login_required
def nowy_wpis():
    zapis = _aktywny_zapis()
    if not zapis:
        flash('Nie masz aktywnej praktyki. Skontaktuj się z opiekunem.', 'danger')
        return redirect(url_for('dziennik.index'))

    form = FormularzWpisu()
    form.efekt_id.choices = [
        (str(e.id), f'{e.kod}: {e.description[:80]}...' if len(e.description) > 80 else f'{e.kod}: {e.description}')
        for e in db.session.query(EfektUczenia).order_by(EfektUczenia.id).all()
    ]

    if form.validate_on_submit():
        data = date.fromisoformat(form.data_wpisu.data)
        duplikat = db.session.query(WpisDziennika).filter_by(enrollment_id=zapis.id, entry_date=data).first()
        if duplikat:
            flash('Wpis na ten dzień już istnieje. Możesz go edytować.', 'danger')
            return render_template('dziennik/nowy_wpis.html', form=form, zapis=zapis)
        godziny = int(form.liczba_godzin.data)
        wpis = WpisDziennika(
            id = uuid.uuid4(),
            enrollment_id = zapis.id,
            entry_date = data,
            duration_hours = godziny,
            description = form.opis.data.strip(),
            learning_outcome_id = int(form.efekt_id.data),
        )
        db.session.add(wpis)
        db.session.commit()
        flash(f'Wpis z dnia {data.strftime("%d.%m.%Y")} został dodany ({godziny} h).', 'success')
        return redirect(url_for('dziennik.index'))

    if request.method == 'GET':
        form.data_wpisu.data = date.today().isoformat()

    return render_template('dziennik/nowy_wpis.html', form=form, zapis=zapis)


@dziennik_bp.route('/pdf', methods=['POST'])
@login_required
def zlec_pdf():
    zapis = db.session.query(ZapisPraktyki).filter_by(student_id=current_user.id).order_by(ZapisPraktyki.enrolled_at.desc()).first()
    if not zapis:
        return jsonify({'error': 'Brak zapisu'}), 404
    try:
        from celery_app import generate_pdf_dziennik
        task = generate_pdf_dziennik.delay(str(zapis.id))
        return jsonify({'task_id': task.id, 'status': 'PENDING'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dziennik_bp.route('/pdf/status/<task_id>')
@login_required
def status_pdf(task_id):
    try:
        from celery_app import celery
        task = celery.AsyncResult(task_id)
        if task.state == 'SUCCESS':
            return jsonify({'status': 'SUCCESS', 'download_url': url_for('dziennik.pobierz_pdf', task_id=task_id)})
        elif task.state == 'FAILURE':
            return jsonify({'status': 'FAILURE', 'error': str(task.info)})
        else:
            progress = task.info.get('progress', 0) if task.info else 0
            return jsonify({'status': task.state, 'progress': progress})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@dziennik_bp.route('/pdf/pobierz/<task_id>')
@login_required
def pobierz_pdf(task_id):
    from pathlib import Path
    try:
        from celery_app import celery
        task = celery.AsyncResult(task_id)
        if task.state != 'SUCCESS':
            abort(404)
        result = task.result
        pdf_path = Path(result['path'])
        nazwa = result['filename']
        if not pdf_path.exists():
            abort(404)
        return send_file(pdf_path, mimetype='application/pdf', as_attachment=True, download_name=nazwa)
    except Exception:
        abort(500)
