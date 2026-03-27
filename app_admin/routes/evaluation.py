"""
app_admin/routes/evaluation.py
Oceny efektów uczenia się — operuje na ZapisPraktyki (enrollment).
"""
import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app_admin.models import (ZapisPraktyki, OcenaPraktyki, EfektUczenia,
                    RolaUzytkownika, StatusZapisu, WynikOceny)
from app_admin.extensions import db
from app_admin.routes.auth import wymaga_roli

evaluation_bp = Blueprint('evaluation', __name__)


def get_pilne_oceny(uopz_id=None):
    """Zwraca listę praktyk z pilnymi ocenami dla danego UOPZ lub wszystkich."""
    from datetime import date, timedelta

    q = db.session.query(ZapisPraktyki).filter_by(status=StatusZapisu.COMPLETED)

    if uopz_id:
        q = q.filter_by(uopz_id=uopz_id)

    zapisy = q.all()
    pilne_oceny = []

    for zapis in zapisy:
        if zapis.termin_do:
            deadline = zapis.termin_do + timedelta(days=7)  # 7 dni na ocenę
            dni_do_deadline = (deadline - date.today()).days

            # Tylko pilne (3 dni lub mniej) lub przekroczone
            if dni_do_deadline <= 3:
                pilne_oceny.append({
                    'zapis': zapis,
                    'deadline': deadline,
                    'dni_do_deadline': dni_do_deadline,
                    'przekroczony': dni_do_deadline < 0
                })

    return sorted(pilne_oceny, key=lambda x: x['dni_do_deadline'])


def _auto_complete_internships():
    """Automatycznie przenosi praktyki do statusu COMPLETED po zakończeniu terminu."""
    from datetime import date

    # Znajdź praktyki IN_PROGRESS z przekroczonym terminem zakończenia
    praktyki_do_zakonczenia = db.session.query(ZapisPraktyki).filter(
        ZapisPraktyki.status == StatusZapisu.IN_PROGRESS,
        ZapisPraktyki.termin_do < date.today()
    ).all()

    for praktyka in praktyki_do_zakonczenia:
        praktyka.status = StatusZapisu.COMPLETED
        # TODO: Wysłać notyfikację email do UOPZ o nowej praktyce do oceny

    if praktyki_do_zakonczenia:
        db.session.commit()


@evaluation_bp.route('/')
@login_required
def lista_ocen():
    # Automatycznie przenoś praktyki do COMPLETED jeśli minęła data zakończenia
    _auto_complete_internships()

    q = db.session.query(ZapisPraktyki).filter_by(status=StatusZapisu.COMPLETED)

    if current_user.role == RolaUzytkownika.UOPZ:
        q = q.filter_by(uopz_id=current_user.id)

    zapisy = q.order_by(ZapisPraktyki.enrolled_at.desc()).all()

    # Dodaj informacje o deadline'ach dla każdego zapisu
    from datetime import date, timedelta

    zapisy_z_deadlinami = []
    for zapis in zapisy:
        deadline = None
        dni_do_deadline = None
        przekroczony = False

        if zapis.termin_do:
            deadline = zapis.termin_do + timedelta(days=7)  # 7 dni na ocenę
            dni_do_deadline = (deadline - date.today()).days
            przekroczony = dni_do_deadline < 0

        zapisy_z_deadlinami.append({
            'zapis': zapis,
            'deadline': deadline,
            'dni_do_deadline': dni_do_deadline,
            'przekroczony': przekroczony
        })

    return render_template('evaluation/lista_ocen.html', zapisy_z_deadlinami=zapisy_z_deadlinami)

@evaluation_bp.route('/zapis/<uuid:id>/karta_ocen', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def ocen_praktyke(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    if request.method == 'POST':
        # Zapisujemy recenzje opisowe
        zapis.ocena_opisowa_uopz = request.form.get('ocena_opisowa_uopz')
        zapis.ocena_opisowa_zopz = request.form.get('ocena_opisowa_zopz')

        # Zapisujemy parametryczne (z konwersją na float/numeric)
        def parse_grade(val):
            try: return float(val.replace(',', '.'))
            except: return None

        zapis.ocena_sprawozdania = parse_grade(request.form.get('ocena_sprawozdania', ''))
        zapis.ocena_uopz = parse_grade(request.form.get('ocena_uopz', ''))
        zapis.ocena_zopz = parse_grade(request.form.get('ocena_zopz', ''))

        zapis.sprawdzian_pytanie_1 = request.form.get('sprawdzian_pytanie_1')
        zapis.sprawdzian_ocena_1 = parse_grade(request.form.get('sprawdzian_ocena_1', ''))
        
        zapis.sprawdzian_pytanie_2 = request.form.get('sprawdzian_pytanie_2')
        zapis.sprawdzian_ocena_2 = parse_grade(request.form.get('sprawdzian_ocena_2', ''))
        
        zapis.sprawdzian_pytanie_3 = request.form.get('sprawdzian_pytanie_3')
        zapis.sprawdzian_ocena_3 = parse_grade(request.form.get('sprawdzian_ocena_3', ''))

        if request.form.get('zakoncz'):
            zapis.status = StatusZapisu.COMPLETED

        db.session.commit()
        flash('Oceny zostały zapisane.', 'success')
        return redirect(url_for('evaluation.ocen_praktyke', id=zapis.id))

    from flask_wtf import FlaskForm
    csrf_form = FlaskForm()
    return render_template('evaluation/karta_ocen.html', practically=zapis, zapis=zapis, csrf_form=csrf_form)

@evaluation_bp.route('/zapis/<uuid:id>/sprawozdanie')
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def podglad_sprawozdania(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    return render_template('evaluation/podglad_sprawozdania.html', zapis=zapis)


@evaluation_bp.route('/zapis/<uuid:id>', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def ocen_zapis(id):
    zapis  = db.session.get(ZapisPraktyki, id) or abort(404)
    efekty = db.session.query(EfektUczenia).order_by(EfektUczenia.id).all()

    istniejace = {
        str(o.learning_outcome_id): o
        for o in db.session.query(OcenaPraktyki).filter_by(enrollment_id=id).all()
    }

    if request.method == 'POST':
        for efekt in efekty:
            wynik_str = request.form.get(f'wynik_{efekt.id}')
            uwagi     = request.form.get(f'uwagi_{efekt.id}', '').strip()

            if not wynik_str:
                continue

            try:
                wynik = WynikOceny[wynik_str]
            except KeyError:
                continue

            ocena = istniejace.get(str(efekt.id))
            if ocena:
                ocena.result          = wynik
                ocena.evaluator_notes = uwagi or None
            else:
                db.session.add(OcenaPraktyki(
                    id                  = uuid.uuid4(),
                    enrollment_id       = zapis.id,
                    learning_outcome_id = efekt.id,
                    result              = wynik,
                    evaluator_notes     = uwagi or None,
                ))

        db.session.commit()
        flash('Oceny zostały zapisane.', 'success')
        return redirect(url_for('evaluation.ocen_zapis', id=id))

    return render_template('evaluation/formularz_ocen.html',
                           zapis=zapis,
                           efekty=efekty,
                           istniejace=istniejace)


@evaluation_bp.route('/zapis/<uuid:id>/zakoncz', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def zakoncz_zapis(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    zapis.status = StatusZapisu.COMPLETED
    db.session.commit()
    flash(f'Praktyka studenta {zapis.student.first_name} {zapis.student.last_name} została zakończona.', 'success')
    return redirect(url_for('evaluation.lista_ocen'))