"""Widoki oceny efektów uczenia się dla zapisów na praktykę."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm

from core.auth import roles_required
from core.extensions import db, limiter
from core.i18n import t
from core.models import UserRole
from core.presenters import employment_path_label, path_label, split_outcome_description
from core.repositories import AssessmentRepository, EnrollmentRepository, OutcomeRepository, UserRepository
from core.services import AssessmentService as GradingService
from core.services.documents import build_context
from core.services.evaluation import EvaluationService, GradeFormData
from core.services.tex_client import TexServiceError, dyspozycja_pdf, generuj_pdf, odpowiedz_pdf
from core.services.workflow import EnrollmentStateMachine

outcome_repository = OutcomeRepository()
assessment_repository = AssessmentRepository()
enrollment_repository = EnrollmentRepository()
user_repository = UserRepository()

evaluation_bp = Blueprint('evaluation', __name__)

GRADE_FORM_ENDPOINT = 'evaluation.evaluate_internship'


def _can_grade(enrollment) -> bool:
    if current_user.role == UserRole.ADMIN:
        return True
    if current_user.role == UserRole.UOPZ:
        if enrollment.supervisor_id == current_user.id:
            return True
        return getattr(enrollment.student, 'supervisor_id', None) == current_user.id
    return False


def get_urgent_assessments(supervisor_id=None):
    return GradingService.get_urgent_assessments(supervisor_id)


@evaluation_bp.route('/', methods=['GET'])
@login_required
def lista_ocen():
    supervisor_id = current_user.id if current_user.role == UserRole.UOPZ else None
    data = GradingService.prepare_grading_list(supervisor_id=supervisor_id, filtr=request.args.get('filtr'))
    return render_template(
        'evaluation/lista_ocen.html',
        widoczne=data['widoczne'],
        zakonczone=data['zakonczone'],
        filtr=data['filtr'],
        liczba_ocenione=data['liczba_ocenione'],
        liczba_nieocenione=data['liczba_nieocenione'],
    )


@evaluation_bp.route('/auto-complete', methods=['POST'])
@roles_required(UserRole.ADMIN)
@limiter.limit("5 per minute")
def auto_zakoncz_praktyki():
    """Endpoint for scheduled auto-completion of internships past their end date."""
    result = GradingService.auto_complete_internships()
    return {'completed': result['completed'], 'skipped': result['skipped']}, 200


@evaluation_bp.route('/zapis/<uuid:id>/karta_ocen', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
@limiter.limit("60 per hour", methods=['POST'])
def evaluate_internship(id):
    enrollment = enrollment_repository.znajdz_po_id(id) or abort(404)
    if not _can_grade(enrollment):
        abort(403)
    outcomes = outcome_repository.wszystkie()
    existing_assessments = {
        str(assessment.learning_outcome_id): assessment
        for assessment in assessment_repository.get_by_enrollment(id)
    }

    if request.method == 'POST':
        try:
            grade_data = GradeFormData(
                report_grade=EvaluationService.parse_grade(request.form.get('report_grade', '')),
                supervisor_grade=EvaluationService.parse_grade(request.form.get('supervisor_grade', '')),
                workplace_grade=EvaluationService.parse_grade(request.form.get('workplace_grade', '')),
                supervisor_grade_description=request.form.get('supervisor_grade_description'),
                workplace_grade_description=request.form.get('workplace_grade_description'),
                exam_question_1=request.form.get('exam_question_1'),
                exam_grade_1=EvaluationService.parse_grade(request.form.get('exam_grade_1', '')),
                exam_question_2=request.form.get('exam_question_2'),
                exam_grade_2=EvaluationService.parse_grade(request.form.get('exam_grade_2', '')),
                exam_question_3=request.form.get('exam_question_3'),
                exam_grade_3=EvaluationService.parse_grade(request.form.get('exam_grade_3', '')),
                commission_chair=request.form.get('komisja_przewodniczacy'),
                commission_member_2=request.form.get('komisja_czlonek_2'),
                commission_member_3=request.form.get('komisja_czlonek_3'),
                finalize=bool(request.form.get('complete')),
            )
        except ValueError as exc:
            flash(t(str(exc)), 'danger')
            return redirect(url_for(GRADE_FORM_ENDPOINT, id=enrollment.id)), 400

        result = GradingService.save_grades(enrollment, grade_data)
        if not result.success:
            flash(t(result.error_message), 'danger')
            return redirect(url_for(GRADE_FORM_ENDPOINT, id=enrollment.id))

        outcome_error = EvaluationService.validate_outcome_grades(
            outcomes, request.form, enrollment.is_path_b, grade_data.finalize
        )
        if outcome_error:
            db.session.rollback()
            flash(t(outcome_error), 'danger')
            return redirect(url_for(GRADE_FORM_ENDPOINT, id=enrollment.id))

        for outcome in outcomes:
            notes = request.form.get(f'notes_{outcome.id}', '').strip()
            EvaluationService.upsert_assessment(
                outcome,
                request.form.get(f'outcome_{outcome.id}'),
                notes,
                existing_assessments,
                enrollment.id,
            )

        db.session.commit()
        if grade_data.finalize:
            flash(t('Oceny zostały zatwierdzone.'), 'success')
            return redirect(url_for('evaluation.lista_ocen'))
        flash(t('Oceny zostały zapisane.'), 'success')
        return redirect(url_for(GRADE_FORM_ENDPOINT, id=enrollment.id))

    staff = user_repository.active_university_mentors()
    csrf_form = FlaskForm()
    return render_template(
        'evaluation/karta_ocen.html',
        zapis=enrollment,
        practically=enrollment,
        pracownicy=staff,
        csrf_form=csrf_form,
        efekty=outcomes,
        istniejace=existing_assessments,
        path_label=employment_path_label(enrollment.path_type),
    )


@evaluation_bp.route('/zapis/<uuid:id>/report', methods=['GET'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def podglad_sprawozdania(id):
    enrollment = enrollment_repository.znajdz_po_id(id) or abort(404)
    if not _can_grade(enrollment):
        abort(403)
    return render_template('evaluation/podglad_sprawozdania.html', zapis=enrollment)


@evaluation_bp.route('/zapis/<uuid:id>', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def ocen_zapis(id):
    enrollment = enrollment_repository.znajdz_po_id(id) or abort(404)
    if not _can_grade(enrollment):
        abort(403)
    outcomes = outcome_repository.wszystkie()

    existing_assessments = {
        str(assessment.learning_outcome_id): assessment
        for assessment in assessment_repository.get_by_enrollment(id)
    }

    if request.method == 'POST':
        for outcome in outcomes:
            notes = request.form.get(f'uwagi_{outcome.id}', '').strip()
            EvaluationService.upsert_assessment(
                outcome,
                request.form.get(f'wynik_{outcome.id}'),
                notes,
                existing_assessments,
                enrollment.id,
            )
        db.session.commit()
        flash(t('Oceny zostały zapisane.'), 'success')
        return redirect(url_for('evaluation.ocen_zapis', id=id))

    efekty_wiersze = [
        {'efekt': o, **split_outcome_description(o.description, o.id)}
        for o in outcomes
    ]
    return render_template(
        'evaluation/formularz_ocen.html',
        zapis=enrollment,
        efekty_wiersze=efekty_wiersze,
        istniejace=existing_assessments,
        sciezka_label=path_label(enrollment.path_type.value),
    )


@evaluation_bp.route('/zapis/<uuid:id>/complete', methods=['POST'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def zakoncz_zapis(id):
    enrollment = enrollment_repository.znajdz_po_id(id) or abort(404)
    if not _can_grade(enrollment):
        abort(403)
    EnrollmentStateMachine(enrollment).complete()
    db.session.commit()
    flash(
        t('Praktyka studenta {imie} {nazwisko} została zakończona.',
          imie=enrollment.student.first_name, nazwisko=enrollment.student.last_name),
        'success',
    )
    return redirect(url_for('evaluation.lista_ocen'))


@evaluation_bp.route('/zapis/<uuid:id>/protokol', methods=['GET'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def generuj_protokol(id):
    """Generates the exam protocol PDF through tex-service."""
    enrollment = enrollment_repository.znajdz_po_id(id) or abort(404)
    if not _can_grade(enrollment):
        abort(403)
    if not (enrollment.final_grades and enrollment.final_grades.supervisor_grade):
        flash(t('Protokół dostępny dopiero po wystawieniu oceny UOPZ.'), 'warning')
        return redirect(url_for(GRADE_FORM_ENDPOINT, id=id))

    context = build_context(enrollment, 'ZAL_8')
    student = enrollment.student
    try:
        pdf = generuj_pdf('zal8_protokol.tex.j2', context, 'zal8_protokol.pdf', timeout=60)
        return odpowiedz_pdf(pdf, dyspozycja_pdf('zal8_protokol', student.last_name))
    except TexServiceError as exc:
        if exc.status_code:
            current_app.logger.warning("tex-service returned %s for protokol %s", exc.status_code, id)
            flash(t('Błąd generowania protokołu. Spróbuj ponownie później.'), 'danger')
        else:
            current_app.logger.error("tex-service unreachable for protokol %s: %s", id, exc)
            flash(t('Błąd połączenia z serwisem PDF. Spróbuj ponownie później.'), 'danger')
    return redirect(url_for(GRADE_FORM_ENDPOINT, id=id))
