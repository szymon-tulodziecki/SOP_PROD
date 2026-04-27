"""
app_admin/routes/ocenianie.py
Oceny efektów uczenia się — operuje na InternshipEnrollment (enrollment).
Przemianowano z evaluation.py.
"""
import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from core.modele import (InternshipEnrollment, OutcomeAssessment, LearningOutcome,
                    UserRole, AssessmentResult)
from core.extensions import db
from core.autoryzacja import wymaga_roli
from core.repozytoria import OutcomeRepository, AssessmentRepository, EnrollmentRepository, UserRepository
from core.uslugi.workflow import ZapisFSM
from core.uslugi.ocenianie import GradeFormData

_repo_outcomes    = OutcomeRepository()
_repo_assessments = AssessmentRepository()
_repo_zapisow     = EnrollmentRepository()
_repo_uzytk       = UserRepository()

evaluation_bp = Blueprint('evaluation', __name__)

_ROUTE_OCEN = 'evaluation.ocen_praktyke'


def _parse_grade(val: str):
    """Konwertuje ocenę z formularza na float, obsługując przecinki i kropki."""
    if not val or not val.strip():
        return None
    try:
        return float(val.strip().replace(',', '.'))
    except (ValueError, AttributeError):
        return None


from core.uslugi import SerwisOceniania


def get_pilne_oceny(uopz_id=None):
    return SerwisOceniania.get_pilne_oceny(uopz_id)


@evaluation_bp.route('/', methods=['GET'])
@login_required
def lista_ocen():
    SerwisOceniania.auto_complete_internships()
    uopz_id = current_user.id if current_user.role == UserRole.UOPZ else None
    data = SerwisOceniania.przygotuj_liste_ocen(supervisor_id=uopz_id, filtr=request.args.get('filtr'))
    return render_template('evaluation/lista_ocen.html',
                           widoczne=data['widoczne'],
                           zakonczone=data['zakonczone'],
                           filtr=data['filtr'])

@evaluation_bp.route('/zapis/<uuid:id>/karta_ocen', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def ocen_praktyke(id):
    enrollment = _repo_zapisow.znajdz_po_id(id) or abort(404)

    if request.method == 'POST':
        grade_data = GradeFormData(
            report_grade                 = _parse_grade(request.form.get('ocena_sprawozdania', '')),
            supervisor_grade             = _parse_grade(request.form.get('ocena_uopz', '')),
            workplace_grade              = _parse_grade(request.form.get('ocena_zopz', '')),
            supervisor_grade_description = request.form.get('ocena_opisowa_uopz'),
            workplace_grade_description  = request.form.get('ocena_opisowa_zopz'),
            exam_question_1              = request.form.get('sprawdzian_pytanie_1'),
            exam_grade_1                 = _parse_grade(request.form.get('sprawdzian_ocena_1', '')),
            exam_question_2              = request.form.get('sprawdzian_pytanie_2'),
            exam_grade_2                 = _parse_grade(request.form.get('sprawdzian_ocena_2', '')),
            exam_question_3              = request.form.get('sprawdzian_pytanie_3'),
            exam_grade_3                 = _parse_grade(request.form.get('sprawdzian_ocena_3', '')),
            commission_chair             = request.form.get('komisja_przewodniczacy'),
            commission_member_2          = request.form.get('komisja_czlonek_2'),
            commission_member_3          = request.form.get('komisja_czlonek_3'),
            finalize                     = bool(request.form.get('zakoncz')),
        )

        result = SerwisOceniania.zapisz_oceny(enrollment, grade_data)

        if not result.success:
            flash(result.error_message, 'danger')
            return redirect(url_for(_ROUTE_OCEN, id=enrollment.id))

        db.session.commit()
        if grade_data.finalize:
            flash('Oceny zostały zatwierdzone.', 'success')
            return redirect(url_for('evaluation.lista_ocen'))
        flash('Oceny zostały zapisane.', 'success')
        return redirect(url_for(_ROUTE_OCEN, id=enrollment.id))

    from flask_wtf import FlaskForm
    staff = _repo_uzytk.aktywni_mentorzy()
    csrf_form = FlaskForm()
    return render_template('evaluation/karta_ocen.html',
                           zapis=enrollment, practically=enrollment,
                           pracownicy=staff,
                           csrf_form=csrf_form)

@evaluation_bp.route('/zapis/<uuid:id>/sprawozdanie', methods=['GET'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def podglad_sprawozdania(id):
    enrollment = _repo_zapisow.znajdz_po_id(id) or abort(404)
    return render_template('evaluation/podglad_sprawozdania.html', zapis=enrollment)

@evaluation_bp.route('/zapis/<uuid:id>', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def ocen_zapis(id):
    enrollment = _repo_zapisow.znajdz_po_id(id) or abort(404)
    outcomes            = _repo_outcomes.wszystkie()

    existing_assessments = {
        str(o.learning_outcome_id): o
        for o in _repo_assessments.dla_zapisu(id)
    }

    if request.method == 'POST':
        for outcome in outcomes:
            result_str = request.form.get(f'wynik_{outcome.id}')
            notes      = request.form.get(f'uwagi_{outcome.id}', '').strip()
            if not result_str:
                continue
            try:
                result = AssessmentResult[result_str]
            except KeyError:
                continue
            assessment = existing_assessments.get(str(outcome.id))
            if assessment:
                assessment.result = result
                assessment.notes  = notes or None
            else:
                _repo_assessments.zapisz(OutcomeAssessment(
                    id                  = uuid.uuid4(),
                    enrollment_id       = enrollment.id,
                    learning_outcome_id = outcome.id,
                    result              = result,
                    notes               = notes or None,
                ))
        db.session.commit()
        flash('Oceny zostały zapisane.', 'success')
        return redirect(url_for('evaluation.ocen_zapis', id=id))

    return render_template('evaluation/formularz_ocen.html',
                           zapis=enrollment, efekty=outcomes, istniejace=existing_assessments)

@evaluation_bp.route('/zapis/<uuid:id>/zakoncz', methods=['POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def zakoncz_zapis(id):
    enrollment = _repo_zapisow.znajdz_po_id(id) or abort(404)
    ZapisFSM(enrollment).zakoncz()
    db.session.commit()
    flash(f'Praktyka studenta {enrollment.student.first_name} {enrollment.student.last_name} została zakończona.', 'success')
    return redirect(url_for('evaluation.lista_ocen'))

@evaluation_bp.route('/zapis/<uuid:id>/protokol', methods=['GET'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def generuj_protokol(id):
    """Generuje Protokół egzaminu (zał.8) przez tex-service."""
    import httpx
    import unicodedata
    from urllib.parse import quote
    from flask import make_response, current_app
    from core.uslugi.dokumenty import buduj_kontekst

    enrollment = _repo_zapisow.znajdz_po_id(id) or abort(404)
    if not (enrollment.final_grades and enrollment.final_grades.supervisor_grade):
        flash('Protokół dostępny dopiero po wystawieniu oceny UOPZ.', 'warning')
        return redirect(url_for(_ROUTE_OCEN, id=id))

    context  = buduj_kontekst(enrollment, 'ZAL_8')
    student  = enrollment.student
    tex_url  = current_app.config.get('TEX_SERVICE_URL', 'http://tex-service:5002')
    try:
        r = httpx.post(
            f'{tex_url}/generuj',
            json={'template': 'zal8_protokol.tex.j2', 'context': context, 'filename': 'zal8_protokol.pdf'},
            timeout=60,
        )
        if r.status_code == 200:
            full_name = f"zal8_protokol_{student.last_name}.pdf"
            ascii_fb  = (unicodedata.normalize('NFKD', full_name)
                         .encode('ascii', 'ignore').decode('ascii').strip() or 'zal8_protokol.pdf')
            utf8_enc  = quote(full_name, safe='')
            resp = make_response(r.content)
            resp.headers['Content-Type'] = 'application/pdf'
            resp.headers['Content-Disposition'] = (
                f"attachment; filename=\"{ascii_fb}\"; filename*=UTF-8''{utf8_enc}"
            )
            return resp
        flash(f'Błąd generowania protokołu: {r.text[:200]}', 'danger')
    except Exception as e:
        flash(f'Błąd połączenia z tex-service: {str(e)}', 'danger')
    return redirect(url_for(_ROUTE_OCEN, id=id))
