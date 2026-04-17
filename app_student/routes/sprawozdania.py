import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms.validators import DataRequired, Optional

from core.extensions import db
from core.modele import InternshipEnrollment, InternshipReport, EnrollmentStatus, InternshipPath
from core.repozytoria import RepozytoriumZapisow

_repo_zapisow = RepozytoriumZapisow()

sprawozdania_bp = Blueprint('sprawozdania', __name__)


class FormularzSprawozdaniaStandard(FlaskForm):
    """Zał. 7 — ścieżka A: standardowa praktyka."""
    charakterystyka = TextAreaField('I. Charakterystyka miejsca odbywania praktyki', validators=[DataRequired()])
    opis = TextAreaField('II. Opis i analiza wykonywanych prac', validators=[DataRequired()])
    wiedza = TextAreaField('III. Wiedza i umiejętności uzyskane w trakcie praktyki', validators=[Optional()])


class FormularzSprawozdaniaPracaZawodowa(FlaskForm):
    """Zał. 7a — ścieżki B/C: praca zawodowa lub działalność gospodarcza."""
    charakterystyka = TextAreaField('I. Charakterystyka miejsca pracy / działalności', validators=[DataRequired()])
    opis = TextAreaField('II. Opis i analiza wykonywanych prac / działalności', validators=[DataRequired()])
    wiedza = TextAreaField('III. Wiedza i umiejętności uzyskane w trakcie pracy zawodowej lub działalności', validators=[Optional()])


@sprawozdania_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    zapis = _repo_zapisow.aktywny_dla_studenta(current_user.id, [
        EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMMISSION_REVIEW,
        EnrollmentStatus.DEAN_APPROVAL, EnrollmentStatus.COMPLETED, EnrollmentStatus.AWAITING_APPROVAL,
    ])

    if not zapis:
        ma_zapis = _repo_zapisow.pierwszy_dla_studenta(current_user.id)
        return render_template('sprawozdania/index.html', zapis=None, ma_zapis=ma_zapis)

    # Utwórz sprawozdanie jeśli nie istnieje
    if not zapis.sprawozdanie:
        nowe_spr = InternshipReport(
            id=uuid.uuid4(),
            enrollment_id=zapis.id,
            charakterystyka_miejsca='',
            opis_i_analiza=''
        )
        db.session.add(nowe_spr)
        db.session.commit()
        zapis = db.session.get(InternshipEnrollment, zapis.id)

    # Wybierz formularz i szablon wg ścieżki
    sciezka = zapis.path_type.value if zapis.path_type else 'STANDARD'
    is_standard = sciezka == 'STANDARD'

    FormClass = FormularzSprawozdaniaStandard if is_standard else FormularzSprawozdaniaPracaZawodowa
    form = FormClass()

    if form.validate_on_submit():
        zapis.sprawozdanie.charakterystyka_miejsca = form.charakterystyka.data
        zapis.sprawozdanie.opis_i_analiza = form.opis.data
        db.session.commit()
        flash('InternshipReport zostało zapisane.', 'success')
        return redirect(url_for('sprawozdania.index'))
    elif request.method == 'GET':
        form.charakterystyka.data = zapis.sprawozdanie.charakterystyka_miejsca
        form.opis.data = zapis.sprawozdanie.opis_i_analiza

    return render_template('sprawozdania/index.html',
                           zapis=zapis, form=form, ma_zapis=zapis,
                           is_standard=is_standard, sciezka=sciezka)
