import uuid
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_wtf import FlaskForm
from flask_login import login_required, current_user
from app_student.extensions import db
from app_student.models import Praktyka, ZapisPraktyki, StatusPraktyki, StatusZapisu

praktyki_bp = Blueprint('praktyki', __name__)


@praktyki_bp.route('/')
@login_required
def lista():
    dostepne = db.session.query(Praktyka)\
                 .filter_by(status=StatusPraktyki.ACTIVE)\
                 .order_by(Praktyka.rok_uczelniany.desc())\
                 .all()

    zapisane_ids = {
        str(z.internship_id)
        for z in db.session.query(ZapisPraktyki)\
                   .filter_by(student_id=current_user.id).all()
    }

    csrf_form = FlaskForm()
    return render_template('praktyki/lista.html', dostepne=dostepne, zapisane_ids=zapisane_ids, csrf_form=csrf_form)


@praktyki_bp.route('/<uuid:id>/zapisz', methods=['POST'])
@login_required
def zapisz(id):
    praktyka = db.session.get(Praktyka, id)

    if not praktyka or praktyka.status != StatusPraktyki.ACTIVE:
        flash('Ta praktyka nie jest dostępna.', 'danger')
        return redirect(url_for('praktyki.lista'))

    istniejacy = db.session.query(ZapisPraktyki).filter_by(
        internship_id=id,
        student_id=current_user.id
    ).first()

    if istniejacy:
        flash('Jesteś już zapisany do tej praktyki.', 'info')
        return redirect(url_for('praktyki.lista'))

    zapis = ZapisPraktyki(
        id            = uuid.uuid4(),
        internship_id = id,
        student_id    = current_user.id,
        status        = StatusZapisu.PENDING,
    )
    db.session.add(zapis)
    db.session.commit()

    flash(f'Zapisałeś się na praktykę {praktyka.rok_uczelniany} ({praktyka.semestr}).', 'success')
    return redirect(url_for('dashboard.index'))
