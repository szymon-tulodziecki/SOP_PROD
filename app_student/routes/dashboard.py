from flask import Blueprint, render_template
from flask_login import login_required, current_user
from core.models import EnrollmentStatus
from core.models.internships import EventType
from core.repositories import EnrollmentRepository

dashboard_bp = Blueprint('dashboard', __name__)

_repo_zapisow = EnrollmentRepository()


@dashboard_bp.route('/', methods=['GET'])
@login_required
def index():
    enrollment = _repo_zapisow.ostatni_dla_studenta(current_user.id)
    feedback_comment = None
    if enrollment and enrollment.status == EnrollmentStatus.REVISION_REQUIRED:
        ev = _repo_zapisow.ostatnie_zdarzenie(
            enrollment.id, event_type=EventType.COMMITTEE_DECISION, decision='PARTIALLY_APPROVED'
        )
        feedback_comment = ev.comment if ev else None
    return render_template(
        'dashboard/index.html',
        enrollment=enrollment,
        feedback_comment=feedback_comment,
    )
