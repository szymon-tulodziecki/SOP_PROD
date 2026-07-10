from flask import Blueprint, render_template
from flask_login import login_required, current_user
from core.models import UserRole
from core.repositories import EnrollmentRepository, InternshipRepository, UserRepository
from core.services import AssessmentService
from flask_wtf import FlaskForm

dashboard_bp = Blueprint("dashboard", __name__)

enrollment_repository = EnrollmentRepository()
internship_repository = InternshipRepository()
user_repository = UserRepository()


@dashboard_bp.route("/", methods=["GET"])
@login_required
def index():
    supervisor_id = current_user.id if current_user.role == UserRole.UOPZ else None

    enrollment_stats = enrollment_repository.dashboard_stats(supervisor_id=supervisor_id)
    statistics = {
        **enrollment_stats,
        "zakonczone": internship_repository.inactive_count(),
        "liczba_studentow": user_repository.count_active_students(),
    }

    recent_enrollments = enrollment_repository.recent(supervisor_id=supervisor_id, limit=8)

    urgent_assessments = (
        AssessmentService.get_urgent_assessments(current_user.id)
        if current_user.role == UserRole.UOPZ
        else []
    )

    csrf_form = FlaskForm()
    return render_template(
        "dashboard/index.html",
        statystyki=statistics,
        ostatnie_zapisy=recent_enrollments,
        pilne_oceny=urgent_assessments,
        csrf_form=csrf_form,
    )
