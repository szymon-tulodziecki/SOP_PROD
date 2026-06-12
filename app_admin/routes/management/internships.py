import uuid
import csv
import io
import datetime
from datetime import timezone as _tz
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError
from werkzeug.security import generate_password_hash

from core.models import (User, Student, Internship, InternshipEnrollment, InternshipSchedule, LearningOutcome,
                    UserRole, InternshipStatus, EnrollmentStatus, InternshipPath, UploadedDocument, Company, EventType)
from core.extensions import db, limiter
from core.i18n import t, lazy_t
from core.services.internships import InternshipService
_serwis_praktyk = InternshipService()
from core.auth import roles_required
from core.presenters import dni_do_usuniecia, enrollment_status_badge, path_label, schedule_summary
from core.services.workflow import IllegalTransitionError
from core.repositories import (InternshipRepository, EnrollmentRepository,
                               UserRepository, OutcomeRepository,
                               StudentDocumentRepository)

_repo_praktyk = InternshipRepository()
_repo_zapisow = EnrollmentRepository()
user_repository   = UserRepository()
_repo_efektow = OutcomeRepository()
_repo_docs    = StudentDocumentRepository()

_ROUTE_LISTA_PRAKTYK  = 'zarzadzanie.lista_praktyk'
_ROUTE_LISTA_ZGLOSZEN = 'zarzadzanie.lista_zgloszen'

from . import zarzadzanie_bp
from .forms import InternshipForm


_DECISION_STATUS_CLASS = {
    'APPROVED':           'status--completed',
    'PARTIALLY_APPROVED': 'status--in-progress',
}
_COMMITTEE_STATUS_LABELS = {
    'APPROVED':           'Opinia pozytywna',
    'PARTIALLY_APPROVED': 'Opinia częściowo pozytywna',
}
_ADMIN_STATUS_LABELS = {
    'APPROVED':           'Zatwierdzone',
    'PARTIALLY_APPROVED': 'Wymagane poprawki',
}


def _actor_info(event) -> tuple[str, str, object]:
    if not event.executed_by:
        return t('Nieznany użytkownik'), '', None
    u = event.executed_by
    return f'{u.first_name} {u.last_name}'.strip(), u.email, u.role


def _stage_info(event, actor_role) -> tuple[str, str, str]:
    if event.event_type == EventType.DIRECTOR_DECISION:
        status = t('Zatwierdzone') if event.decision == 'APPROVED' else t('Odrzucone')
        return t('Decyzja dyrektora'), t('Dyrektor IIS'), status

    if event.event_type == EventType.COMMITTEE_DECISION and actor_role not in (UserRole.ADMIN, UserRole.UOPZ):
        status = t(_COMMITTEE_STATUS_LABELS.get(event.decision, 'Opinia negatywna'))
        return t('Opinia komisji'), t('Komisja ds. praktyk'), status

    is_uopz = actor_role == UserRole.UOPZ
    role_label  = 'UOPZ' if is_uopz else t('Administrator')
    stage_label = t('Weryfikacja UOPZ') if is_uopz else t('Weryfikacja administracyjna')
    status = t(_ADMIN_STATUS_LABELS.get(event.decision, 'Odrzucone'))
    return stage_label, role_label, status


def _decision_history_entries(enrollment):
    entries = []
    for event in enrollment.process_events:
        if not event.decision:
            continue

        actor_name, actor_email, actor_role = _actor_info(event)
        stage_label, role_label, status_label = _stage_info(event, actor_role)
        status_class = _DECISION_STATUS_CLASS.get(event.decision, 'status--odrzucona')
        executed_at = event.executed_at.strftime('%d.%m.%Y, %H:%M') if event.executed_at else t('Brak daty')

        entries.append({
            'stage_label':  stage_label,
            'role_label':   role_label,
            'actor_name':   actor_name,
            'actor_email':  actor_email,
            'executed_at':  executed_at,
            'status_label': status_label,
            'status_class': status_class,
            'comment':      event.comment,
        })
    return entries

# ── Praktyki ──────────────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/praktyki', methods=['GET'])
@roles_required(UserRole.ADMIN)
def lista_praktyk():
    page = request.args.get('strona', 1, type=int)
    praktyki = _repo_praktyk.lista_strona(strona=page)
    teraz = datetime.datetime.utcnow()
    do_usuniecia = []
    for p in _repo_praktyk.do_usuniecia():
        dni = dni_do_usuniecia(p.deleted_at, teraz)
        do_usuniecia.append({'praktyka': p, 'dni_pozostale': dni, 'pilne': dni <= 1})
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/praktyki.html', praktyki=praktyki,
                           do_usuniecia=do_usuniecia, csrf_form=csrf_form)


@zarzadzanie_bp.route('/praktyki/nowa', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN)
def nowa_praktyka():
    form = InternshipForm()
    if form.validate_on_submit():
        academic_year = (form.academic_year.data or '').strip()
        try:
            required_hours = int(form.required_hours.data)
        except (TypeError, ValueError):
            flash(t('Wymiar godzin musi być liczbą całkowitą.'), 'danger')
            return render_template('zarzadzanie/formularz_praktyki.html', form=form)
        p = Internship(
            id             = uuid.uuid4(),
            academic_year  = academic_year,
            semester       = form.semester.data,
            required_hours = required_hours,
            status         = InternshipStatus.INACTIVE,
        )
        _repo_praktyk.zapisz(p)
        db.session.commit()
        flash(t('Praktyka została utworzona.'), 'success')
        return redirect(url_for(_ROUTE_LISTA_PRAKTYK))
    return render_template('zarzadzanie/formularz_praktyki.html', form=form)


@zarzadzanie_bp.route('/praktyki/<uuid:id>/aktywnosc', methods=['POST'])
@roles_required(UserRole.ADMIN)
def przelacz_aktywnosc_praktyki(id):
    p = _repo_praktyk.znajdz_po_id(id) or abort(404)
    p.status = InternshipStatus.INACTIVE if p.status == InternshipStatus.ACTIVE else InternshipStatus.ACTIVE
    db.session.commit()
    stan = t('aktywowana') if p.status == InternshipStatus.ACTIVE else t('dezaktywowana')
    flash(t('Praktyka {rok} ({semestr}) została {stan}.', rok=p.academic_year, semestr=p.semester_label, stan=stan), 'success')
    return redirect(url_for(_ROUTE_LISTA_PRAKTYK))


# ── Zgłoszenia studentów ──────────────────────────────────────────────────────

class FormularzPrzypiszUOPZ(FlaskForm):
    supervisor_id = SelectField(lazy_t('Opiekun uczelniany (UOPZ)'), choices=[], validators=[Optional()])


@zarzadzanie_bp.route('/zgloszenia', methods=['GET'])
@roles_required(UserRole.ADMIN, UserRole.KOMISJA, UserRole.DYREKTOR, UserRole.UOPZ)
def lista_zgloszen():
    page          = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()

    supervisor_id = current_user.id if current_user.role == UserRole.UOPZ else None
    try:
        applications = _repo_zapisow.lista_zgloszen_strona(status_filter=status_filter, strona=page, supervisor_id=supervisor_id)
    except ValueError:
        flash(t('Nieznany status: {status}', status=status_filter), 'warning')
        applications = _repo_zapisow.lista_zgloszen_strona(strona=page, supervisor_id=supervisor_id)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/enrollments/list.html', zgloszenia=applications, csrf_form=csrf_form)


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/przypisz-supervisor', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN)
def przypisz_uopz(id):
    enrollment = _repo_zapisow.znajdz_po_id(id) or abort(404)
    form       = FormularzPrzypiszUOPZ()
    uopz_list  = user_repository.active_uopz()
    form.supervisor_id.choices = [('', t('--- brak ---'))] + [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]

    if form.validate_on_submit():
        if form.supervisor_id.data:
            try:
                _serwis_praktyk.submit_for_approval_with_supervisor(id, form.supervisor_id.data)
                flash(t('Opiekun UOPZ przypisany, zgłoszenie przekazane do zatwierdzenia.'), 'success')
            except IllegalTransitionError as e:
                flash(t(str(e)), 'danger')
        else:
            flash(t('Nie wybrano opiekuna.'), 'warning')
        return redirect(url_for(_ROUTE_LISTA_ZGLOSZEN))

    if request.method == 'GET':
        form.supervisor_id.data = str(enrollment.supervisor_id) if enrollment.supervisor_id else ''

    return render_template('zarzadzanie/enrollments/przypisz_uopz.html', form=form, zapis=enrollment)


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/szczegoly', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ, UserRole.KOMISJA, UserRole.DYREKTOR)
def szczegoly_zgloszenia(id):
    enrollment = _repo_zapisow.znajdz_po_id(id) or abort(404)

    if current_user.role == UserRole.UOPZ and enrollment.supervisor_id != current_user.id:
        abort(403)
    # KOMISJA i DYREKTOR mają wgląd w każde zgłoszenie (read-only flow)

    schedule      = _repo_zapisow.harmonogram_dla_zapisu(id)
    schedule_dict = {h.learning_outcome_id: h for h in schedule}
    outcomes      = _repo_efektow.wszystkie()

    class CommentForm(FlaskForm):
        comment    = TextAreaField(lazy_t('Komentarz do studenta'))
        zatwierdz  = SubmitField(lazy_t('Zatwierdź zgłoszenie'))
        reject     = SubmitField(lazy_t('Wymagane poprawki'))

    form = CommentForm()

    if form.validate_on_submit():
        comment = form.comment.data or ''
        try:
            if form.zatwierdz.data:
                _serwis_praktyk.approve_by_supervisor(id, actor_id=current_user.id, comment=comment)
                flash(t('Zgłoszenie zostało zatwierdzone!'), 'success')
            elif form.reject.data:
                _serwis_praktyk.request_revision(id, actor_id=current_user.id, comment=comment)
                flash(t('Wysłano prośbę o poprawki do studenta.'), 'info')
        except IllegalTransitionError as e:
            flash(t(str(e)), 'danger')
        return redirect(url_for(_ROUTE_LISTA_ZGLOSZEN))

    uploaded_docs = _repo_docs.dla_zapisu_studenta(id, enrollment.student_id)

    status_val = enrollment.status.value
    if status_val in ('PENDING', 'AWAITING_APPROVAL'):
        panel_decyzji = 'formularz'
    elif status_val == 'REVISION_REQUIRED':
        panel_decyzji = 'poprawki'
    else:
        panel_decyzji = 'zatwierdzone'

    return render_template('zarzadzanie/enrollments/szczegoly.html',
                           zapis=enrollment,
                           form=form, uploaded_docs=uploaded_docs,
                           status_odznaka=enrollment_status_badge(status_val),
                           sciezka_label=path_label(enrollment.path_type.value),
                           harmonogram=schedule_summary(outcomes, schedule_dict),
                           panel_decyzji=panel_decyzji,
                           decision_history_entries=_decision_history_entries(enrollment))


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/zatwierdz-zaklad', methods=['POST'])
@roles_required(UserRole.UOPZ, UserRole.ADMIN)
def zatwierdz_zaklad(id):
    try:
        _serwis_praktyk.approve_by_supervisor(id, actor_id=current_user.id)
        flash(t('Zakład zatwierdzony. Praktyka rozpoczęła się.'), 'success')
    except IllegalTransitionError as e:
        flash(t(str(e)), 'danger')
    return redirect(url_for(_ROUTE_LISTA_ZGLOSZEN))


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/potwierdz', methods=['POST'])
@roles_required(UserRole.ADMIN, UserRole.UOPZ)
def potwierdz_zapis(id):
    supervisor_id = current_user.id if current_user.role == UserRole.UOPZ else None
    try:
        _serwis_praktyk.approve_by_supervisor(id, actor_id=current_user.id, supervisor_id=supervisor_id)
        flash(t('Zapis studenta na praktykę został potwierdzony. Zostałeś/aś przypisany/a jako opiekun.'), 'success')
    except IllegalTransitionError as e:
        flash(t(str(e)), 'danger')
    return redirect(request.referrer or url_for('dashboard.index'))


@zarzadzanie_bp.route('/moje-zgloszenia', methods=['GET'])
@roles_required(UserRole.UOPZ)
def moje_zgloszenia():
    """Lista zgłoszeń przypisanych do aktualnego UOPZ."""
    page          = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()

    try:
        applications = _repo_zapisow.dla_uopz_strona(
            current_user.id, status_filter=status_filter, strona=page
        )
    except ValueError:
        flash(t('Nieznany status: {status}', status=status_filter), 'warning')
        applications = _repo_zapisow.dla_uopz_strona(current_user.id, strona=page)

    csrf_form     = FlaskForm()
    return render_template(
        'zarzadzanie/enrollments/list.html',
        zgloszenia=applications,
        csrf_form=csrf_form,
        endpoint_listy='zarzadzanie.moje_zgloszenia',
        tytul_listy='Moje zgłoszenia',
        naglowek_listy='Zgłoszenia moich studentów',
    )


@zarzadzanie_bp.route('/praktyki/<uuid:id>/usun', methods=['POST'])
@roles_required(UserRole.ADMIN)
@limiter.limit("30 per hour")
def usun_praktyke(id):
    from datetime import datetime, timezone
    p    = _repo_praktyk.znajdz_po_id(id) or abort(404)
    opis = f'{p.academic_year} ({p.semester_label})'
    if p.enrollments:
        p.deleted_at = datetime.now(timezone.utc)
        db.session.commit()
        flash(t('Praktyka {opis} została dezaktywowana i zostanie trwale usunięta po 7 dniach. Możesz ją przywrócić.', opis=opis), 'warning')
    else:
        _repo_praktyk.usun(p)
        db.session.commit()
        flash(t('Praktyka {opis} została trwale usunięta (brak zapisanych studentów).', opis=opis), 'success')
    return redirect(url_for(_ROUTE_LISTA_PRAKTYK))


@zarzadzanie_bp.route('/praktyki/<uuid:id>/przywroc', methods=['POST'])
@roles_required(UserRole.ADMIN)
def przywroc_praktyke(id):
    p = _repo_praktyk.znajdz_po_id(id) or abort(404)
    opis = f'{p.academic_year} ({p.semester_label})'
    p.deleted_at = None
    db.session.commit()
    flash(t('Praktyka {opis} została przywrócona.', opis=opis), 'success')
    return redirect(url_for(_ROUTE_LISTA_PRAKTYK))
