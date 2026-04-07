from flask import Blueprint, render_template
from flask_login import login_required, current_user
from core.modele import Praktyka, ZapisPraktyki, Uzytkownik, RolaUzytkownika, StatusPraktyki, StatusZapisu
from core.extensions import db
from flask_wtf import FlaskForm

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    q = db.session.query(ZapisPraktyki)

    if current_user.role == RolaUzytkownika.UOPZ:
        q = q.filter(db.or_(ZapisPraktyki.uopz_id == current_user.id, ZapisPraktyki.status == StatusZapisu.PENDING))

    statystyki = {
        'praktyki_aktywne': q.filter(ZapisPraktyki.status == StatusZapisu.IN_PROGRESS).count(),
        'oczekujace_oceny': q.filter(ZapisPraktyki.status == StatusZapisu.COMPLETED).count(),
        'zakonczone':       db.session.query(Praktyka).filter_by(status=StatusPraktyki.NIEAKTYWNA).count(),
        'liczba_studentow': db.session.query(Uzytkownik).filter_by(
            rola=RolaUzytkownika.STUDENT, aktywny=True).count(),
    }

    ostatnie_zapisy = (q
        .order_by(ZapisPraktyki.enrolled_at.desc())
        .limit(8).all())

    # Dodaj ostrzeżenia o przekroczonych deadline'ach dla UOPZ
    pilne_oceny = []
    if current_user.role == RolaUzytkownika.UOPZ:
        from datetime import date, timedelta

        completed_q = db.session.query(ZapisPraktyki).filter(
            ZapisPraktyki.status == StatusZapisu.COMPLETED,
            ZapisPraktyki.uopz_id == current_user.id
        )

        for zapis in completed_q.all():
            if zapis.termin_do:
                deadline = zapis.termin_do + timedelta(days=7)
                dni_do_deadline = (deadline - date.today()).days
                if dni_do_deadline <= 2:
                    pilne_oceny.append({
                        'zapis': zapis,
                        'deadline': deadline,
                        'dni_do_deadline': dni_do_deadline,
                        'przekroczony': dni_do_deadline < 0
                    })

    csrf_form = FlaskForm()
    return render_template('dashboard/index.html',
                           statystyki=statystyki,
                           ostatnie_zapisy=ostatnie_zapisy,
                           pilne_oceny=pilne_oceny,
                           csrf_form=csrf_form)
