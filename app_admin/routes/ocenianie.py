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

_repo_zapisow = RepozytoriumZapisow()
_repo_efektow = RepozytoriumEfektow()
_repo_ocen    = RepozytoriumOcen()

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

    def _is_path_b(zapis):
        pt = zapis.path_type
        val = pt.value if hasattr(pt, 'value') else str(pt)
        return val in _PATH_B_VALS

    zapisy  = _repo_zapisow.aktywne_i_zakonczone(supervisor_id=uopz_id)

    from datetime import date, timedelta

    zapisy_z_deadlinami = []
    for zapis in zapisy:
        deadline = None
        dni_do_deadline = None
        przekroczony = False
        is_path_b = _is_path_b(zapis)

        if zapis.end_date and zapis.status == EnrollmentStatus.COMPLETED:
            deadline = zapis.end_date + timedelta(days=7)
            dni_do_deadline = (deadline - date.today()).days
            przekroczony = dni_do_deadline < 0

        zapisy_z_deadlinami.append({
            'zapis': zapis,
            'deadline': deadline,
            'dni_do_deadline': dni_do_deadline,
            'przekroczony': przekroczony,
            'w_trakcie': zapis.status == EnrollmentStatus.IN_PROGRESS,
            'zakonczona': zapis.status == EnrollmentStatus.COMPLETED,
            'is_path_b': is_path_b,
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
    zakonczone = [z for z in zapisy_z_deadlinami
                  if z['zakonczona'] or (z['w_trakcie'] and z['is_path_b'])]

    for z in zakonczone:
        z['oceniony'] = _ma_oceny(z['zapis'])

    # nieocenieni pierwsi, potem ocenieni
    zakonczone.sort(key=lambda z: z['oceniony'])

    filtr = request.args.get('filtr')
    if filtr == 'nieocenione':
        widoczne = [z for z in zakonczone if not z['oceniony']]
    elif filtr == 'ocenione':
        widoczne = [z for z in zakonczone if z['oceniony']]
    else:
        widoczne = zakonczone

    return render_template('evaluation/lista_ocen.html',
                           widoczne=widoczne,
                           zakonczone=zakonczone,
                           filtr=filtr)

@evaluation_bp.route('/zapis/<uuid:id>/karta_ocen', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def ocen_praktyke(id):
    zapis = db.session.get(InternshipEnrollment, id) or abort(404)

    if request.method == 'POST':
        from core.uslugi.ocenianie import GradeFormData

        dane = GradeFormData(
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

        wynik = SerwisOceniania.zapisz_oceny(zapis, dane)

        if not wynik.success:
            flash(wynik.error_message, 'danger')
            return redirect(url_for('evaluation.ocen_praktyke', id=zapis.id))

        db.session.commit()
        if dane.finalize:
            flash('Oceny zostały zatwierdzone.', 'success')
            return redirect(url_for('evaluation.lista_ocen'))
        flash('Oceny zostały zapisane.', 'success')
        return redirect(url_for('evaluation.ocen_praktyke', id=zapis.id))

    from flask_wtf import FlaskForm
    from core.modele.uzytkownicy import UniversityMentor, Administrator
    pracownicy = db.session.execute(
        db.select(UniversityMentor).filter_by(is_active=True).order_by(
            UniversityMentor.last_name, UniversityMentor.first_name)
    ).scalars().all()
    csrf_form = FlaskForm()
    return render_template('evaluation/karta_ocen.html',
                           zapis=zapis, practically=zapis,
                           pracownicy=pracownicy,
                           csrf_form=csrf_form)

@evaluation_bp.route('/zapis/<uuid:id>/sprawozdanie', methods=['GET'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def podglad_sprawozdania(id):
    zapis = db.session.get(InternshipEnrollment, id) or abort(404)
    return render_template('evaluation/podglad_sprawozdania.html', zapis=zapis)

@evaluation_bp.route('/zapis/<uuid:id>', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def ocen_zapis(id):
    zapis  = db.session.get(InternshipEnrollment, id) or abort(404)
    efekty = _repo_efektow.wszystkie()

    istniejace = {
        str(o.learning_outcome_id): o
        for o in _repo_ocen.dla_zapisu(id)
    }

    if request.method == 'POST':
        for efekt in efekty:
            wynik_str = request.form.get(f'wynik_{efekt.id}')
            uwagi     = request.form.get(f'uwagi_{efekt.id}', '').strip()
            if not wynik_str:
                continue
            try:
                wynik = AssessmentResult[wynik_str]
            except KeyError:
                continue
            ocena = istniejace.get(str(efekt.id))
            if ocena:
                ocena.result = wynik
                ocena.notes  = uwagi or None
            else:
                db.session.add(OutcomeAssessment(
                    id                  = uuid.uuid4(),
                    enrollment_id       = zapis.id,
                    learning_outcome_id = efekt.id,
                    result              = wynik,
                    notes               = uwagi or None,
                ))
        db.session.commit()
        flash('Oceny zostały zapisane.', 'success')
        return redirect(url_for('evaluation.ocen_zapis', id=id))

    return render_template('evaluation/formularz_ocen.html',
                           zapis=zapis, efekty=efekty, istniejace=istniejace)

@evaluation_bp.route('/zapis/<uuid:id>/zakoncz', methods=['POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def zakoncz_zapis(id):
    zapis = db.session.get(InternshipEnrollment, id) or abort(404)
    from core.uslugi.workflow import ZapisFSM
    ZapisFSM(zapis).zakoncz()
    db.session.commit()
    flash(f'Praktyka studenta {zapis.student.first_name} {zapis.student.last_name} została zakończona.', 'success')
    return redirect(url_for('evaluation.lista_ocen'))

@evaluation_bp.route('/zapis/<uuid:id>/protokol', methods=['GET'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def generuj_protokol(id):
    """Generuje Protokół egzaminu (zał.8) przez tex-service."""
    import httpx, unicodedata
    from flask import make_response, current_app
    from datetime import date

    zapis = db.session.get(InternshipEnrollment, id) or abort(404)
    ok = zapis.final_grades
    sp = zapis.examination
    if not (ok and ok.supervisor_grade):
        flash('Protokół dostępny dopiero po wystawieniu oceny UOPZ.', 'warning')
        return redirect(url_for('evaluation.ocen_praktyke', id=id))

    s = zapis.student
    tex_url = current_app.config.get('TEX_SERVICE_URL', 'http://tex-service:5002')
    dm = zapis.workplace_details
    firma_nazwa = (zapis.firma.name if zapis.firma else (dm.company_name if dm else None)) or ''

    def _f(v):
        return float(v) if v is not None else None

    ctx = {
        'zapis': {
            'firma_nazwa':          firma_nazwa,
            'termin_od':            zapis.start_date.strftime('%d.%m.%Y') if zapis.start_date else '',
            'termin_do':            zapis.end_date.strftime('%d.%m.%Y') if zapis.end_date else '',
            'ocena_sprawozdania':   _f(ok.report_grade if ok else None),
            'ocena_uopz':           _f(ok.supervisor_grade if ok else None),
            'ocena_zopz':           _f(ok.workplace_grade if ok else None),
            'sprawdzian_pytanie_1': sp.question_1 if sp else None,
            'sprawdzian_ocena_1':   _f(sp.grade_1 if sp else None),
            'sprawdzian_pytanie_2': sp.question_2 if sp else None,
            'sprawdzian_ocena_2':   _f(sp.grade_2 if sp else None),
            'sprawdzian_pytanie_3': sp.question_3 if sp else None,
            'sprawdzian_ocena_3':   _f(sp.grade_3 if sp else None),
            'uopz': {'first_name': zapis.uopz.first_name, 'last_name': zapis.uopz.last_name} if zapis.uopz else None,
            'komisja_przewodniczacy': sp.commission_chair    if sp else None,
            'komisja_czlonek_2':      sp.commission_member_2 if sp else None,
            'komisja_czlonek_3':      sp.commission_member_3 if sp else None,
        },
        'student': {
            'imie': s.first_name, 'nazwisko': s.last_name,
            'first_name': s.first_name, 'last_name': s.last_name,
            'nr_albumu': s.album_number or '', 'album_number': s.album_number or '',
            'kierunek': getattr(s, 'field_of_study', 'Informatyka') or 'Informatyka',
        },
        'specjalnosc': getattr(s, 'specialization', '') or getattr(zapis, 'specialization', '') or '',
        'praktyka': {
            'rok_uczelniany': zapis.internship.academic_year if zapis.internship else '',
            'semestr':        zapis.internship.semester      if zapis.internship else '',
            'wymiar_godzin':  zapis.internship.required_hours if zapis.internship else 960,
        },
        'data_egzaminu': date.today().strftime('%d.%m.%Y'),
    }
    try:
        r = httpx.post(f'{tex_url}/generuj',
                       json={'template': 'zal8_protokol.tex.j2', 'context': ctx, 'filename': 'zal8_protokol.pdf'},
                       timeout=60)
        if r.status_code == 200:
            import unicodedata
            from urllib.parse import quote
            full_name = f"zal8_protokol_{s.last_name}.pdf"
            ascii_fb = (unicodedata.normalize('NFKD', full_name)
                        .encode('ascii', 'ignore').decode('ascii').strip() or 'zal8_protokol.pdf')
            utf8_enc = quote(full_name, safe='')
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
