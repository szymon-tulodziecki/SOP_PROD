import uuid

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import TextAreaField
from wtforms.validators import DataRequired, Optional

from core.extensions import db
from core.modele import InternshipReport, EnrollmentStatus
from core.repozytoria import EnrollmentRepository

_repo_zapisow = EnrollmentRepository()

reports_bp = Blueprint('reports', __name__)


class StandardReportForm(FlaskForm):
    """Zał. 7, ścieżka A: standardowa praktyka."""
    workplace_characteristics = TextAreaField(
        'I. Charakterystyka miejsca odbywania praktyki',
        validators=[DataRequired()],
    )
    work_description = TextAreaField(
        'II. Opis i analiza wykonywanych prac',
        validators=[DataRequired()],
    )
    acquired_knowledge = TextAreaField(
        'III. Wiedza i umiejętności uzyskane w trakcie praktyki',
        validators=[Optional()],
    )

    def populate_to_model(self, model_instance):
        model_instance.charakterystyka_miejsca = self.workplace_characteristics.data
        model_instance.opis_i_analiza = self.work_description.data
        if self.acquired_knowledge.data:
            model_instance.wiedza = self.acquired_knowledge.data
        return model_instance


class EmploymentReportForm(FlaskForm):
    """Zał. 7a, ścieżki B/C: praca zawodowa lub działalność gospodarcza."""
    workplace_characteristics = TextAreaField(
        'I. Charakterystyka miejsca pracy / działalności',
        validators=[DataRequired()],
    )
    duties_scope = TextAreaField(
        'II. Zakres obowiązków',
        validators=[DataRequired()],
    )
    work_analysis = TextAreaField(
        'III. Opis i analiza wykonywanych prac / działalności',
        validators=[DataRequired()],
    )
    acquired_knowledge = TextAreaField(
        'IV. Wiedza i umiejętności uzyskane w trakcie pracy zawodowej lub działalności',
        validators=[Optional()],
    )

    def populate_to_model(self, model_instance):
        model_instance.charakterystyka_miejsca = self.workplace_characteristics.data
        model_instance.opis_i_analiza = f"{self.duties_scope.data}\n\n{self.work_analysis.data}"
        if self.acquired_knowledge.data:
            model_instance.wiedza = self.acquired_knowledge.data
        return model_instance


@reports_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    zapis = _repo_zapisow.aktywny_dla_studenta(current_user.id, [
        EnrollmentStatus.IN_PROGRESS,
        EnrollmentStatus.COMMISSION_REVIEW,
        EnrollmentStatus.DIRECTOR_APPROVAL,
        EnrollmentStatus.COMPLETED,
        EnrollmentStatus.AWAITING_APPROVAL,
    ])

    if not zapis:
        ma_zapis = _repo_zapisow.pierwszy_dla_studenta(current_user.id)
        return render_template('sprawozdania/index.html', zapis=None, ma_zapis=ma_zapis)

    if not zapis.sprawozdanie:
        new_report = InternshipReport(
            id=uuid.uuid4(),
            enrollment_id=zapis.id,
            charakterystyka_miejsca='',
            opis_i_analiza='',
        )
        db.session.add(new_report)
        db.session.commit()
        zapis = _repo_zapisow.znajdz_po_id(zapis.id)

    path_type = zapis.path_type.value if zapis.path_type else 'STANDARD'
    is_standard = path_type == 'STANDARD'
    FormClass = StandardReportForm if is_standard else EmploymentReportForm
    form = FormClass()

    if form.validate_on_submit():
        form.populate_to_model(zapis.sprawozdanie)
        db.session.commit()
        flash('Sprawozdanie zostało zapisane.', 'success')
        return redirect(url_for('reports.index'))

    if request.method == 'GET':
        form.workplace_characteristics.data = zapis.sprawozdanie.charakterystyka_miejsca
        if is_standard:
            form.work_description.data = zapis.sprawozdanie.opis_i_analiza
        else:
            form.duties_scope.data = ''
            form.work_analysis.data = zapis.sprawozdanie.opis_i_analiza
        form.acquired_knowledge.data = zapis.sprawozdanie.wiedza

    return render_template(
        'sprawozdania/index.html',
        zapis=zapis,
        form=form,
        ma_zapis=zapis,
        is_standard=is_standard,
        sciezka=path_type,
    )
