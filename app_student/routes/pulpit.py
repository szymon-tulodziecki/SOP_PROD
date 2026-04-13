from flask import Blueprint, render_template
from flask_login import login_required, current_user
from core.modele import InternshipEnrollment, EnrollmentStatus
from core.repozytoria import RepozytoriumZapisow

dashboard_bp = Blueprint('dashboard', __name__)

_repo_zapisow = RepozytoriumZapisow()


@dashboard_bp.route('/')
@login_required
def index():
    zapis = _repo_zapisow.ostatni_dla_studenta(current_user.id)
    return render_template('dashboard/index.html', zapis=zapis)
