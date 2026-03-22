from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app_student.models import ZapisPraktyki, StatusZapisu
from app_student.extensions import db

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    zapis = db.session.query(ZapisPraktyki)\
              .filter_by(student_id=current_user.id)\
              .order_by(ZapisPraktyki.enrolled_at.desc())\
              .first()

    return render_template('dashboard/index.html', zapis=zapis)
