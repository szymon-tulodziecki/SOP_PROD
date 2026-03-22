from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app_admin.models import Praktyka, ZapisPraktyki, Uzytkownik, RolaUzytkownika, StatusPraktyki, StatusZapisu
from app_admin.extensions import db

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def index():
    q = db.session.query(ZapisPraktyki)

    if current_user.role == RolaUzytkownika.UOPZ:
        q = q.filter_by(uopz_id=current_user.id)

    statystyki = {
        'praktyki_aktywne': q.filter(ZapisPraktyki.status == StatusZapisu.IN_PROGRESS).count(),
        'oczekujace_oceny': q.filter(ZapisPraktyki.status == StatusZapisu.COMPLETED).count(),
        'zakonczone':       db.session.query(Praktyka).filter_by(status=StatusPraktyki.INACTIVE).count(),
        'liczba_studentow': db.session.query(Uzytkownik).filter_by(
            role=RolaUzytkownika.STUDENT, is_active=True).count(),
    }

    ostatnie_zapisy = (q
        .filter(ZapisPraktyki.status == StatusZapisu.IN_PROGRESS)
        .order_by(ZapisPraktyki.enrolled_at.desc())
        .limit(8).all())

    return render_template('dashboard/index.html',
                           statystyki=statystyki,
                           ostatnie_zapisy=ostatnie_zapisy)