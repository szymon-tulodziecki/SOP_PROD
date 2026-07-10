"""Widoki dokumentów studentów dla ról ADMIN i UOPZ."""

import logging

from flask import abort, render_template, request
from flask_login import current_user, login_required

from core.models import EnrollmentStatus, UserRole
from core.presenters import document_status_badge, path_label, study_mode_label
from core.repositories import EnrollmentRepository, UserRepository
from core.services.documents import DOC_CONFIG, STATIC_TEMPLATES, build_context, resolve_documents
from core.services.tex_client import TexServiceError, dyspozycja_pdf, generuj_pdf, odpowiedz_pdf

from . import zarzadzanie_bp

logger = logging.getLogger(__name__)

user_repository = UserRepository()
enrollment_repository = EnrollmentRepository()


def _track_name(enrollment) -> str:
    return enrollment.path_type.value if enrollment.path_type else "STANDARD"


@zarzadzanie_bp.route("/dokumenty", methods=["GET"])
@login_required
def dokumenty_studentow():
    page = request.args.get("strona", 1, type=int)
    search_query = request.args.get("szukaj", "").strip()
    supervisor_id = current_user.id if current_user.role == UserRole.UOPZ else None

    students_page = user_repository.students_page(
        search=search_query,
        supervisor_id=supervisor_id,
        page=page,
    )

    active_statuses = [
        EnrollmentStatus.AWAITING_APPROVAL,
        EnrollmentStatus.COMMISSION_REVIEW,
        EnrollmentStatus.DIRECTOR_APPROVAL,
        EnrollmentStatus.IN_PROGRESS,
        EnrollmentStatus.COMPLETED,
    ]
    student_ids = [student.id for student in students_page.items]
    active_counts = enrollment_repository.liczba_aktywnych_dla_studentow(
        student_ids,
        active_statuses,
    )

    supervisor_cache: dict = {}
    student_infos = []
    for student in students_page.items:
        supervisor = None
        if student.supervisor_id:
            if student.supervisor_id not in supervisor_cache:
                supervisor_cache[student.supervisor_id] = user_repository.find_by_id(
                    student.supervisor_id
                )
            supervisor = supervisor_cache[student.supervisor_id]
        student_infos.append(
            {
                "student": student,
                "supervisor": supervisor,
                "aktywne": active_counts.get(student.id, 0),
            }
        )

    return render_template(
        "zarzadzanie/dokumenty_studentow.html",
        studenci=students_page,
        studenci_info=student_infos,
        szukaj=search_query,
    )


@zarzadzanie_bp.route("/dokumenty/student/<uuid:student_id>", methods=["GET"])
@login_required
def dokumenty_studenta(student_id):
    student = user_repository.find_by_id(student_id) or abort(404)

    active_statuses = [
        EnrollmentStatus.AWAITING_APPROVAL,
        EnrollmentStatus.COMMISSION_REVIEW,
        EnrollmentStatus.DIRECTOR_APPROVAL,
        EnrollmentStatus.IN_PROGRESS,
        EnrollmentStatus.COMPLETED,
    ]
    enrollments = enrollment_repository.aktywne_dla_studenta(student_id, active_statuses)

    if current_user.role == UserRole.UOPZ:
        is_student_supervisor = student.supervisor_id == current_user.id
        is_enrollment_supervisor = any(
            enrollment.supervisor_id == current_user.id for enrollment in enrollments
        )
        if not (is_student_supervisor or is_enrollment_supervisor):
            abort(403)

    supervisor = (
        user_repository.find_by_id(student.supervisor_id) if student.supervisor_id else None
    )
    document_items = []
    for enrollment in enrollments:
        firma_nazwa = (
            enrollment.company.name if enrollment.company else enrollment.company_display_name
        )
        document_items.append(
            {
                "zapis": enrollment,
                "docs": resolve_documents(enrollment),
                "path": _track_name(enrollment),
                "sciezka_label": path_label(_track_name(enrollment)),
                "status_odznaka": document_status_badge(enrollment.status.value),
                "firma_nazwa": firma_nazwa,
            }
        )

    return render_template(
        "zarzadzanie/dokumenty_studenta.html",
        student=student,
        supervisor=supervisor,
        dokumenty_list=document_items,
        tryb_studiow=study_mode_label(student.study_mode),
    )


@zarzadzanie_bp.route("/dokumenty/pobierz/<uuid:enrollment_id>/<event_type>", methods=["GET"])
@login_required
def dokumenty_pobierz(enrollment_id, event_type):
    if event_type not in DOC_CONFIG:
        abort(404)

    enrollment = enrollment_repository.znajdz_po_id(enrollment_id) or abort(404)
    if current_user.role == UserRole.UOPZ and enrollment.supervisor_id != current_user.id:
        abort(403)

    template_name, filename = DOC_CONFIG[event_type]
    context = build_context(enrollment, event_type)
    try:
        pdf = generuj_pdf(template_name, context, filename, timeout=60)
    except TexServiceError as exc:
        if exc.status_code:
            abort(500)
        logger.error("tex-service unreachable for %s/%s: %s", event_type, enrollment_id, exc)
        abort(503)

    pdf_name = template_name.replace(".tex.j2", "")
    return odpowiedz_pdf(pdf, dyspozycja_pdf(pdf_name, enrollment.student.last_name or "student"))


@zarzadzanie_bp.route("/dokumenty/staly/<klucz>", methods=["GET"])
@login_required
def dokumenty_pobierz_staly(klucz):
    if klucz not in STATIC_TEMPLATES:
        abort(404)

    template_name, filename = STATIC_TEMPLATES[klucz]
    try:
        pdf = generuj_pdf(template_name, {}, filename, timeout=30)
    except TexServiceError as exc:
        if exc.status_code:
            abort(500)
        logger.error("tex-service unreachable for static doc %s: %s", klucz, exc)
        abort(503)

    return odpowiedz_pdf(pdf, dyspozycja_pdf(filename))
