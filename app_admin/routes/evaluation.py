"""Learning outcome grading routes for InternshipEnrollment."""
from urllib.parse import quote

import httpx
import unicodedata
from flask import Blueprint, abort, current_app, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm

from core.autoryzacja import roles_required
from core.extensions import db
from core.modele import UserRole
from core.repozytoria import AssessmentRepository, EnrollmentRepository, OutcomeRepository, UserRepository
from core.uslugi import SerwisOceniania as GradingService
from core.uslugi.documents import build_context
from core.uslugi.evaluation import EvaluationService, GradeFormData
from core.uslugi.workflow import ZapisFSM

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


def get_pilne_oceny(uopz_id=None):
    return GradingService.get_pilne_oceny(uopz_id)


@evaluation_bp.route('/', methods=['GET'])
@login_required
def lista_ocen():
    supervisor_id = current_user.id if current_user.role == UserRole.UOPZ else None
    data = GradingService.przygotuj_liste_ocen(supervisor_id=supervisor_id, filtr=request.args.get('filtr'))
    return render_template(
        'evaluation/lista_ocen.html',
        widoczne=data['widoczne'],
        zakonczone=data['zakonczone'],
        filtr=data['filtr'],
    )


@evaluation_bp.route('/auto-zakoncz', methods=['POST'])
@roles_required(UserRole.ADMIN)
def auto_zakoncz_praktyki():
    """Endpoint for scheduled auto-completion of internships past their end date."""
    result = GradingService.auto_complete_internships()
    return {'completed': result['completed'], 'skipped': result['skipped']}, 200


@evaluation_bp.route('/zapis/<uuid:id>/karta_ocen', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
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
                report_grade=EvaluationService.parse_grade(request.form.get('ocena_sprawozdania', '')),
                supervisor_grade=EvaluationService.parse_grade(request.form.get('ocena_uopz', '')),
                workplace_grade=EvaluationService.parse_grade(request.form.get('ocena_zopz', '')),
                supervisor_grade_description=request.form.get('ocena_opisowa_uopz'),
                workplace_grade_description=request.form.get('ocena_opisowa_zopz'),
                exam_question_1=request.form.get('sprawdzian_pytanie_1'),
                exam_grade_1=EvaluationService.parse_grade(request.form.get('sprawdzian_ocena_1', '')),
                exam_question_2=request.form.get('sprawdzian_pytanie_2'),
                exam_grade_2=EvaluationService.parse_grade(request.form.get('sprawdzian_ocena_2', '')),
                exam_question_3=request.form.get('sprawdzian_pytanie_3'),
                exam_grade_3=EvaluationService.parse_grade(request.form.get('sprawdzian_ocena_3', '')),
                commission_chair=request.form.get('komisja_przewodniczacy'),
                commission_member_2=request.form.get('komisja_czlonek_2'),
                commission_member_3=request.form.get('komisja_czlonek_3'),
                finalize=bool(request.form.get('zakoncz')),
            )
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for(GRADE_FORM_ENDPOINT, id=enrollment.id)), 400

        result = GradingService.zapisz_oceny(enrollment, grade_data)
        if not result.success:
            flash(result.error_message, 'danger')
            return redirect(url_for(GRADE_FORM_ENDPOINT, id=enrollment.id))

        outcome_error = EvaluationService.waliduj_efekty_ocen(
            outcomes, request.form, enrollment.is_path_b, grade_data.finalize
        )
        if outcome_error:
            db.session.rollback()
            flash(outcome_error, 'danger')
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
            flash('Oceny zostały zatwierdzone.', 'success')
            return redirect(url_for('evaluation.lista_ocen'))
        flash('Oceny zostały zapisane.', 'success')
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
    )


@evaluation_bp.route('/zapis/<uuid:id>/sprawozdanie', methods=['GET'])
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
        flash('Oceny zostały zapisane.', 'success')
        return redirect(url_for('evaluation.ocen_zapis', id=id))

    return render_template(
        'evaluation/formularz_ocen.html',
        zapis=enrollment,
        efekty=outcomes,
        istniejace=existing_assessments,
    )


@evaluation_bp.route('/zapis/<uuid:id>/zakoncz', methods=['POST'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def zakoncz_zapis(id):
    enrollment = enrollment_repository.znajdz_po_id(id) or abort(404)
    if not _can_grade(enrollment):
        abort(403)
    ZapisFSM(enrollment).zakoncz()
    db.session.commit()
    flash(
        f'Praktyka studenta {enrollment.student.first_name} {enrollment.student.last_name} została zakończona.',
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
        flash('Protokół dostępny dopiero po wystawieniu oceny UOPZ.', 'warning')
        return redirect(url_for(GRADE_FORM_ENDPOINT, id=id))

    context = build_context(enrollment, 'ZAL_8')
    student = enrollment.student
    tex_url = current_app.config['TEX_SERVICE_URL']
    try:
        response = httpx.post(
            f'{tex_url}/generuj',
            json={'template': 'zal8_protokol.tex.j2', 'context': context, 'filename': 'zal8_protokol.pdf'},
            timeout=60,
        )
        if response.status_code == 200:
            full_name = f"zal8_protokol_{student.last_name}.pdf"
            ascii_fallback = (
                unicodedata.normalize('NFKD', full_name)
                .encode('ascii', 'ignore').decode('ascii')
                .strip() or 'zal8_protokol.pdf'
            )
            utf8_encoded = quote(full_name, safe='')
            pdf_response = make_response(response.content)
            pdf_response.headers['Content-Type'] = 'application/pdf'
            pdf_response.headers['Content-Disposition'] = (
                f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_encoded}"
            )
            return pdf_response
        current_app.logger.warning("tex-service returned %s for protokol %s", response.status_code, id)
        flash('Błąd generowania protokołu. Spróbuj ponownie później.', 'danger')
    except httpx.HTTPError as exc:
        current_app.logger.error("tex-service unreachable for protokol %s: %s", id, exc)
        flash('Błąd połączenia z serwisem PDF. Spróbuj ponownie później.', 'danger')
    return redirect(url_for(GRADE_FORM_ENDPOINT, id=id))
