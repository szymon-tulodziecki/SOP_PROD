import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms.validators import DataRequired

from app_student.extensions import db
from app_student.models import ZapisPraktyki, SprawozdaniePraktyki as Sprawozdanie, StatusZapisu

sprawozdania_bp = Blueprint('sprawozdania', __name__)

class FormularzSprawozdania(FlaskForm):
    charakterystyka = TextAreaField('Charakterystyka miejsca praktyki', validators=[DataRequired()])
    opis = TextAreaField('Opis i analiza prac', validators=[DataRequired()])

@sprawozdania_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    zapis = db.session.query(ZapisPraktyki).filter(
        ZapisPraktyki.student_id == current_user.id,
        ZapisPraktyki.status == StatusZapisu.IN_PROGRESS
    ).first()

    if not zapis:
        zapis_test = db.session.query(ZapisPraktyki).filter_by(student_id=current_user.id).first()
        return render_template('sprawozdania/index.html', zapis=None, ma_zapis=zapis_test)

    # Upewnij się, że obiekt sprawozdania istnieje dla tego zapisu
    if not zapis.sprawozdanie:
        nowe_spr = Sprawozdanie(
            id=uuid.uuid4(),
            enrollment_id=zapis.id,
            charakterystyka_miejsca='',
            opis_i_analiza=''
        )
        db.session.add(nowe_spr)
        db.session.commit()
        # Odśwież zapytanie
        zapis = db.session.get(ZapisPraktyki, zapis.id)

    form = FormularzSprawozdania()

    if form.validate_on_submit():
        zapis.sprawozdanie.charakterystyka_miejsca = form.charakterystyka.data
        zapis.sprawozdanie.opis_i_analiza = form.opis.data
        db.session.commit()
        flash('Sprawozdanie zostało zapisane.', 'success')
        return redirect(url_for('sprawozdania.index'))
    elif request.method == 'GET':
        form.charakterystyka.data = zapis.sprawozdanie.charakterystyka_miejsca
        form.opis.data = zapis.sprawozdanie.opis_i_analiza

    return render_template('sprawozdania/index.html', zapis=zapis, form=form, ma_zapis=zapis)
