"""
app_admin/routes/evaluation.py
Oceny efektów uczenia się — operuje na ZapisPraktyki (enrollment).
"""
import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app_admin.models import (ZapisPraktyki, OcenaPraktyki, EfektUczenia,
                    RolaUzytkownika, StatusZapisu, WynikOceny)
from app_admin.extensions import db
from app_admin.routes.auth import wymaga_roli

evaluation_bp = Blueprint('evaluation', __name__)


@evaluation_bp.route('/')
@login_required
def lista_ocen():
    q = db.session.query(ZapisPraktyki).filter_by(status=StatusZapisu.COMPLETED)

    if current_user.role == RolaUzytkownika.UOPZ:
        q = q.filter_by(uopz_id=current_user.id)

    zapisy = q.order_by(ZapisPraktyki.enrolled_at.desc()).all()
    return render_template('evaluation/lista_ocen.html', zapisy=zapisy)


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