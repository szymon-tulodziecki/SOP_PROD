from flask import Blueprint, render_template
from flask_login import login_required, current_user
from core.modele import EnrollmentStatus
from core.modele.praktyki import EventType
from core.repozytoria import EnrollmentRepository

dashboard_bp = Blueprint('dashboard', __name__)

_repo_zapisow = EnrollmentRepository()


@dashboard_bp.route('/', methods=['GET'])
@login_required
def index():
    zapis = _repo_zapisow.ostatni_dla_studenta(current_user.id)
    komentarz_zwrotny = None
    if zapis and zapis.status == EnrollmentStatus.REVISION_REQUIRED:
        ev = _repo_zapisow.ostatnie_zdarzenie(
            zapis.id, event_type=EventType.COMMITTEE_DECISION, decision='PARTIALLY_APPROVED'
        )
        komentarz_zwrotny = ev.comment if ev else None
    return render_template('dashboard/index.html', zapis=zapis, komentarz_zwrotny=komentarz_zwrotny)
