from flask import Blueprint, render_template
from flask_login import login_required, current_user
from core.modele import UserRole, EnrollmentStatus
from core.repozytoria import EnrollmentRepository, InternshipRepository, UserRepository
from core.uslugi import SerwisOceniania
from flask_wtf import FlaskForm

dashboard_bp = Blueprint('dashboard', __name__)

_repo_zapisow    = EnrollmentRepository()
_repo_praktyk    = InternshipRepository()
_repo_uzytk      = UserRepository()


@dashboard_bp.route('/', methods=['GET'])
@login_required
def index():
    uopz_id = current_user.id if current_user.role == UserRole.UOPZ else None

    stats_zapisow = _repo_zapisow.statystyki_pulpit(supervisor_id=uopz_id)
    statystyki = {
        **stats_zapisow,
        'zakonczone':       _repo_praktyk.liczba_nieaktywnych(),
        'liczba_studentow': _repo_uzytk.liczba_aktywnych_studentow(),
    }

    ostatnie_zapisy = _repo_zapisow.ostatnie(supervisor_id=uopz_id, limit=8)

    pilne_oceny = SerwisOceniania.get_pilne_oceny(current_user.id) if current_user.role == UserRole.UOPZ else []

    csrf_form = FlaskForm()
    return render_template('dashboard/index.html',
                           statystyki=statystyki,
                           ostatnie_zapisy=ostatnie_zapisy,
                           pilne_oceny=pilne_oceny,
                           csrf_form=csrf_form)
