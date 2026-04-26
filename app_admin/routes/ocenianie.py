"""
app_admin/routes/ocenianie.py
Oceny efektów uczenia się — operuje na InternshipEnrollment (enrollment).
Przemianowano z evaluation.py.
"""
import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from core.modele import (InternshipEnrollment, OutcomeAssessment, LearningOutcome,
                    UserRole, EnrollmentStatus, AssessmentResult)
from core.extensions import db
from core.autoryzacja import wymaga_roli
from core.repozytoria import RepozytoriumZapisow, RepozytoriumEfektow, RepozytoriumOcen

_repo_enrollments = RepozytoriumZapisow()
_repo_outcomes    = RepozytoriumEfektow()
_repo_assessments = RepozytoriumOcen()

evaluation_bp = Blueprint('evaluation', __name__)


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
    from core.modele.praktyki import InternshipPath
    _PATH_B_VALS = ('EMPLOYMENT', 'OWN_BUSINESS')

    def _is_path_b(enrollment):
        pt  = enrollment.path_type
        val = pt.value if hasattr(pt, 'value') else str(pt)
        return val in _PATH_B_VALS

    enrollments = _repo_enrollments.aktywne_i_zakonczone(supervisor_id=uopz_id)

    from datetime import date, timedelta

    enrollments_with_deadlines = []
    for enrollment in enrollments:
        deadline      = None
        days_to_deadline = None
        overdue       = False
        is_path_b     = _is_path_b(enrollment)

        if enrollment.end_date and enrollment.status == EnrollmentStatus.COMPLETED:
            deadline         = enrollment.end_date + timedelta(days=7)
            days_to_deadline = (deadline - date.today()).days
            overdue          = days_to_deadline < 0

        enrollments_with_deadlines.append({
            'zapis':          enrollment,
            'deadline':       deadline,
            'dni_do_deadline': days_to_deadline,
            'przekroczony':   overdue,
            'w_trakcie':      enrollment.status == EnrollmentStatus.IN_PROGRESS,
            'zakonczona':     enrollment.status == EnrollmentStatus.COMPLETED,
            'is_path_b':      is_path_b,
        })

    def _ma_oceny(p):
        fg = p.final_grades
        if not fg:
            return False
        if _is_path_b(p):
            return fg.report_grade is not None and p.exam_grade is not None
        return (fg.supervisor_grade is not None
                and fg.report_grade is not None and fg.workplace_grade is not None)

    # path B IN_PROGRESS also appear — UOPZ grades them immediately after Director approves
    completed_list = [z for z in enrollments_with_deadlines
                      if z['zakonczona'] or (z['w_trakcie'] and z['is_path_b'])]

    for z in completed_list:
        z['oceniony'] = _ma_oceny(z['zapis'])

    # nieocenieni pierwsi, potem ocenieni
    completed_list.sort(key=lambda z: z['oceniony'])

    filter_val = request.args.get('filtr')
    if filter_val == 'nieocenione':
        visible = [z for z in completed_list if not z['oceniony']]
    elif filter_val == 'ocenione':
        visible = [z for z in completed_list if z['oceniony']]
    else:
        visible = completed_list

    return render_template('evaluation/lista_ocen.html',
                           widoczne=visible,
                           zakonczone=completed_list,
                           filtr=filter_val)

@evaluation_bp.route('/zapis/<uuid:id>/karta_ocen', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def ocen_praktyke(id):
    enrollment = db.session.get(InternshipEnrollment, id) or abort(404)

    if request.method == 'POST':
        from core.uslugi.ocenianie import GradeFormData

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
            return redirect(url_for('evaluation.ocen_praktyke', id=enrollment.id))

        db.session.commit()
        if grade_data.finalize:
            flash('Oceny zostały zatwierdzone.', 'success')
            return redirect(url_for('evaluation.lista_ocen'))
        flash('Oceny zostały zapisane.', 'success')
        return redirect(url_for('evaluation.ocen_praktyke', id=enrollment.id))

    from flask_wtf import FlaskForm
    from core.modele.uzytkownicy import UniversityMentor, Administrator
    staff = db.session.execute(
        db.select(UniversityMentor).filter_by(is_active=True).order_by(
            UniversityMentor.last_name, UniversityMentor.first_name)
    ).scalars().all()
    csrf_form = FlaskForm()
    return render_template('evaluation/karta_ocen.html',
                           zapis=enrollment, practically=enrollment,
                           pracownicy=staff,
                           csrf_form=csrf_form)

@evaluation_bp.route('/zapis/<uuid:id>/sprawozdanie', methods=['GET'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def podglad_sprawozdania(id):
    enrollment = db.session.get(InternshipEnrollment, id) or abort(404)
    return render_template('evaluation/podglad_sprawozdania.html', zapis=enrollment)

@evaluation_bp.route('/zapis/<uuid:id>', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def ocen_zapis(id):
    enrollment          = db.session.get(InternshipEnrollment, id) or abort(404)
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
                db.session.add(OutcomeAssessment(
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
    enrollment = db.session.get(InternshipEnrollment, id) or abort(404)
    from core.uslugi.workflow import ZapisFSM
    ZapisFSM(enrollment).zakoncz()
    db.session.commit()
    flash(f'Praktyka studenta {enrollment.student.first_name} {enrollment.student.last_name} została zakończona.', 'success')
    return redirect(url_for('evaluation.lista_ocen'))

@evaluation_bp.route('/zapis/<uuid:id>/protokol', methods=['GET'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def generuj_protokol(id):
    """Generuje Protokół egzaminu (zał.8) przez tex-service."""
    import httpx, unicodedata
    from flask import make_response, current_app
    from datetime import date

    enrollment    = db.session.get(InternshipEnrollment, id) or abort(404)
    final_grades  = enrollment.final_grades
    examination   = enrollment.examination
    if not (final_grades and final_grades.supervisor_grade):
        flash('Protokół dostępny dopiero po wystawieniu oceny UOPZ.', 'warning')
        return redirect(url_for('evaluation.ocen_praktyke', id=id))

    student         = enrollment.student
    tex_url         = current_app.config.get('TEX_SERVICE_URL', 'http://tex-service:5002')
    workplace_details = enrollment.workplace_details
    company_name    = (enrollment.firma.name if enrollment.firma else (workplace_details.company_name if workplace_details else None)) or ''

    def _f(v):
        return float(v) if v is not None else None

    context = {
        'zapis': {
            'firma_nazwa':          company_name,
            'termin_od':            enrollment.start_date.strftime('%d.%m.%Y') if enrollment.start_date else '',
            'termin_do':            enrollment.end_date.strftime('%d.%m.%Y') if enrollment.end_date else '',
            'ocena_sprawozdania':   _f(final_grades.report_grade if final_grades else None),
            'ocena_uopz':           _f(final_grades.supervisor_grade if final_grades else None),
            'ocena_zopz':           _f(final_grades.workplace_grade if final_grades else None),
            'sprawdzian_pytanie_1': examination.question_1 if examination else None,
            'sprawdzian_ocena_1':   _f(examination.grade_1 if examination else None),
            'sprawdzian_pytanie_2': examination.question_2 if examination else None,
            'sprawdzian_ocena_2':   _f(examination.grade_2 if examination else None),
            'sprawdzian_pytanie_3': examination.question_3 if examination else None,
            'sprawdzian_ocena_3':   _f(examination.grade_3 if examination else None),
            'uopz': {'first_name': enrollment.uopz.first_name, 'last_name': enrollment.uopz.last_name} if enrollment.uopz else None,
            'komisja_przewodniczacy': examination.commission_chair    if examination else None,
            'komisja_czlonek_2':      examination.commission_member_2 if examination else None,
            'komisja_czlonek_3':      examination.commission_member_3 if examination else None,
        },
        'student': {
            'imie': student.first_name, 'nazwisko': student.last_name,
            'first_name': student.first_name, 'last_name': student.last_name,
            'nr_albumu': student.album_number or '', 'album_number': student.album_number or '',
            'kierunek': getattr(student, 'field_of_study', 'Informatyka') or 'Informatyka',
        },
        'specjalnosc': getattr(student, 'specialization', '') or getattr(enrollment, 'specialization', '') or '',
        'praktyka': {
            'rok_uczelniany': enrollment.internship.academic_year if enrollment.internship else '',
            'semestr':        enrollment.internship.semester      if enrollment.internship else '',
            'wymiar_godzin':  enrollment.internship.required_hours if enrollment.internship else 960,
        },
        'data_egzaminu': date.today().strftime('%d.%m.%Y'),
    }
    try:
        r = httpx.post(f'{tex_url}/generuj',
                       json={'template': 'zal8_protokol.tex.j2', 'context': context, 'filename': 'zal8_protokol.pdf'},
                       timeout=60)
        if r.status_code == 200:
            from urllib.parse import quote
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
    return redirect(url_for('evaluation.ocen_praktyke', id=id))
