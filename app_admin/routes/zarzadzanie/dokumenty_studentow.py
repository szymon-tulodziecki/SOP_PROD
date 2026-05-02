"""Student document views for ADMIN and UOPZ roles."""

import logging
import unicodedata
from urllib.parse import quote

import httpx
from flask import abort, current_app, make_response, render_template, request
from flask_login import current_user, login_required

from core.modele import EnrollmentStatus, UserRole
from core.repozytoria import EnrollmentRepository, UserRepository
from core.uslugi.documents import DOC_CONFIG, STATIC_TEMPLATES, build_context, rozwiaz_dokumenty

from . import zarzadzanie_bp

logger = logging.getLogger(__name__)

user_repository = UserRepository()
enrollment_repository = EnrollmentRepository()


def _get_tex_url() -> str:
    return current_app.config['TEX_SERVICE_URL']


def _track_name(enrollment) -> str:
    return enrollment.track_type.value if enrollment.track_type else 'STANDARD'


def _pdf_content_disposition(base_name: str, last_name: str) -> str:
    """Builds RFC 6266/RFC 5987 compatible Content-Disposition for PDFs."""
    full_name = f"{base_name}_{last_name}.pdf"
    ascii_fallback = (
        unicodedata.normalize('NFKD', full_name)
        .encode('ascii', 'ignore').decode('ascii')
        .strip() or 'dokument.pdf'
    )
    utf8_encoded = quote(full_name, safe='')
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_encoded}"


@zarzadzanie_bp.route('/dokumenty', methods=['GET'])
@login_required
def dokumenty_studentow():
    page = request.args.get('strona', 1, type=int)
    search_query = request.args.get('szukaj', '').strip()
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
                supervisor_cache[student.supervisor_id] = user_repository.find_by_id(student.supervisor_id)
            supervisor = supervisor_cache[student.supervisor_id]
        student_infos.append({
            'student': student,
            'uopz': supervisor,
            'aktywne': active_counts.get(student.id, 0),
        })

    return render_template(
        'zarzadzanie/dokumenty_studentow.html',
        studenci=students_page,
        studenci_info=student_infos,
        szukaj=search_query,
    )


@zarzadzanie_bp.route('/dokumenty/student/<uuid:student_id>', methods=['GET'])
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
        is_enrollment_supervisor = any(enrollment.supervisor_id == current_user.id for enrollment in enrollments)
        if not (is_student_supervisor or is_enrollment_supervisor):
            abort(403)

    supervisor = user_repository.find_by_id(student.supervisor_id) if student.supervisor_id else None
    document_items = [
        {
            'zapis': enrollment,
            'docs': rozwiaz_dokumenty(enrollment),
            'sciezka': _track_name(enrollment),
        }
        for enrollment in enrollments
    ]

    return render_template(
        'zarzadzanie/dokumenty_studenta.html',
        student=student,
        uopz=supervisor,
        dokumenty_list=document_items,
    )


@zarzadzanie_bp.route('/dokumenty/pobierz/<uuid:zapis_id>/<typ>', methods=['GET'])
@login_required
def dokumenty_pobierz(zapis_id, typ):
    if typ not in DOC_CONFIG:
        abort(404)

    enrollment = enrollment_repository.znajdz_po_id(zapis_id) or abort(404)
    if current_user.role == UserRole.UOPZ and enrollment.supervisor_id != current_user.id:
        abort(403)

    template_name, filename = DOC_CONFIG[typ]
    context = build_context(enrollment, typ)
    try:
        response = httpx.post(
            f"{_get_tex_url()}/generuj",
            json={'template': template_name, 'context': context, 'filename': filename},
            timeout=60,
        )
        if response.status_code != 200:
            abort(500)

        pdf_name = template_name.replace('.tex.j2', '')
        pdf_response = make_response(response.content)
        pdf_response.headers['Content-Type'] = 'application/pdf'
        pdf_response.headers['Content-Disposition'] = _pdf_content_disposition(
            pdf_name,
            enrollment.student.last_name or 'student',
        )
        return pdf_response
    except Exception:
        logger.exception("Błąd generowania %s dla %s", typ, zapis_id)
        abort(500)


@zarzadzanie_bp.route('/dokumenty/staly/<klucz>', methods=['GET'])
@login_required
def dokumenty_pobierz_staly(klucz):
    if klucz not in STATIC_TEMPLATES:
        abort(404)

    template_name, filename = STATIC_TEMPLATES[klucz]
    try:
        response = httpx.post(
            f"{_get_tex_url()}/generuj",
            json={'template': template_name, 'context': {}, 'filename': filename},
            timeout=30,
        )
        if response.status_code != 200:
            abort(500)

        pdf_response = make_response(response.content)
        pdf_response.headers['Content-Type'] = 'application/pdf'
        pdf_response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return pdf_response
    except Exception:
        logger.exception("Błąd pobierania stałego dokumentu %s", klucz)
        abort(500)
