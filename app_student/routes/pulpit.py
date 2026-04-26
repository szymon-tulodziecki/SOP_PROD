from flask import Blueprint, render_template
from flask_login import login_required, current_user
from core.modele import InternshipEnrollment, EnrollmentStatus
from core.repozytoria import RepozytoriumZapisow
from core.extensions import db

dashboard_bp = Blueprint('dashboard', __name__)

_repo_zapisow = RepozytoriumZapisow()


@dashboard_bp.route('/', methods=['GET'])
@login_required
def index():
    zapis = _repo_zapisow.ostatni_dla_studenta(current_user.id)
    komentarz_zwrotny = None
    if zapis and zapis.status == EnrollmentStatus.REVISION_REQUIRED:
        from core.modele.praktyki import ProcessEvent, EventType
        ev = (
            db.session.query(ProcessEvent)
            .filter_by(enrollment_id=zapis.id, event_type=EventType.COMMITTEE_DECISION)
            .filter(ProcessEvent.decision == 'PARTIALLY_APPROVED')
            .order_by(ProcessEvent.executed_at.desc())
            .first()
        )
        komentarz_zwrotny = ev.comment if ev else None
    return render_template('dashboard/index.html', zapis=zapis, komentarz_zwrotny=komentarz_zwrotny)
