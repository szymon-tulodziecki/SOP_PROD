import uuid
import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, make_response
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DateField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, Optional, Length, Email, ValidationError
import re
from flask_login import login_required, current_user
from core.extensions import db
import httpx
from core.models import (Internship, InternshipEnrollment, InternshipStatus, EnrollmentStatus,
                         InternshipPath, InternshipSchedule,
                         WorkplaceDetails, PathJustification)
from core.models.internships import EventType
from core.services.workflow import EnrollmentStateMachine, IllegalTransitionError
from core.services.internships import InternshipService
from core.repositories import (InternshipRepository, EnrollmentRepository,
                               OutcomeRepository, CompanyRepository,
                               StudentDocumentRepository)

_repo_praktyk = InternshipRepository()
_repo_zapisow = EnrollmentRepository()
_repo_efektow = OutcomeRepository()
company_repository    = CompanyRepository()
_repo_docs    = StudentDocumentRepository()

internships_bp = Blueprint('internships', __name__)

_ROUTE_LISTA        = 'internships.lista'
_ROUTE_SZCZEGOLY    = 'internships.szczegoly_zgloszenia'
_TPL_KR2A           = 'kreator/krok2a_firma.html'


# ═══════════════════════════════════════════════════════════
# NOWE FORMULARZE KREATORA
# ═══════════════════════════════════════════════════════════

class FormularzSciezka(FlaskForm):
    """Krok 1: Tylko wybór ścieżki."""
    track_type = SelectField('Ścieżka praktyki', choices=[
        ('STANDARD',   'A — Standardowa praktyka zawodowa'),
        ('EMPLOYMENT', 'B — Uznanie efektów uczenia się z pracy zawodowej'),
    ], validators=[DataRequired(message='Wybierz ścieżkę.')])


class CompanyDataForm(FlaskForm):
    """Krok 2A: Dane zakładu pracy + ZOPZ + terminy (tylko ścieżka A)."""
    # Terminy i dane podstawowe
    termin_od        = DateField('Data rozpoczęcia', validators=[DataRequired(message='Podaj datę.')])
    termin_do        = DateField('Data zakończenia', validators=[DataRequired(message='Podaj datę.')])
    ubezpieczenie_nw = BooleanField('Posiadam ubezpieczenie NW na czas trwania praktyki')

    # Tryb znalezienia miejsca
    firma_typ  = SelectField('Jak znalazłeś/-aś miejsce praktyki?', choices=[
        ('database', 'Uczelnia kieruje do zakładu (company ma umowę z ANS)'),
        ('custom',   'Sam/a znalazłem/-am miejsce (wymaga Zał. 9 i Zał. 1)'),
    ], validators=[DataRequired()])
    company_id   = SelectField('Wybierz firmę z listy', choices=[], validators=[Optional()])

    company_name                  = StringField('Nazwa zakładu pracy', validators=[Optional(), Length(max=255)])
    company_address                  = StringField('Adres (ulica, nr)', validators=[Optional(), Length(max=255)])
    company_zip           = StringField('Kod pocztowy', validators=[Optional(), Length(max=10)])
    company_city                 = StringField('Miasto', validators=[Optional(), Length(max=100)])
    tax_id                = StringField('NIP / KRS', validators=[Optional(), Length(max=50)])
    authorized_person      = StringField('Osoba upoważniona do podpisania porozumienia', validators=[Optional(), Length(max=255)])
    authorized_person_position = StringField('Stanowisko osoby upoważnionej', validators=[Optional(), Length(max=255)])

    workplace_mentor_name = StringField('Opiekun zakładowy (ZOPZ) — imię i nazwisko', validators=[Optional(), Length(max=255)])
    workplace_mentor_position    = StringField('Stanowisko ZOPZ', validators=[Optional(), Length(max=255)])
    workplace_mentor_phone       = StringField('Telefon ZOPZ', validators=[Optional(), Length(max=50)])
    workplace_mentor_email         = StringField('E-mail ZOPZ', validators=[Optional(), Email(message='Nieprawidłowy email.')])

    def validate_company_zip(self, field):
        if not field.data:
            return
        if not re.fullmatch(r'\d{2}-\d{3}', field.data.strip()):
            raise ValidationError('Podaj kod pocztowy w formacie XX-XXX (np. 82-300).')

    def validate_workplace_mentor_name(self, field):
        if not field.data:
            return
        parts = field.data.strip().split()
        if len(parts) < 2:
            raise ValidationError('Podaj imię i nazwisko (co najmniej dwa wyrazy).')
        if any(char.isdigit() for char in field.data):
            raise ValidationError('Imię i nazwisko nie może zawierać cyfr.')

    def validate_authorized_person(self, field):
        if not field.data:
            return
        parts = field.data.strip().split()
        if len(parts) < 2:
            raise ValidationError('Podaj imię i nazwisko osoby upoważnionej (co najmniej dwa wyrazy).')
        if any(char.isdigit() for char in field.data):
            raise ValidationError('Imię i nazwisko nie może zawierać cyfr.')

    def populate_to_model(self, model_instance):
        model_instance.company_name = self.company_name.data
        model_instance.company_address = self.company_address.data
        model_instance.company_zip = self.company_zip.data or None
        model_instance.company_city = self.company_city.data
        model_instance.company_tax_id = self.tax_id.data
        model_instance.authorized_person = self.authorized_person.data
        model_instance.authorized_person_position = self.authorized_person_position.data
        model_instance.workplace_mentor_name = self.workplace_mentor_name.data
        model_instance.workplace_mentor_position = self.workplace_mentor_position.data
        model_instance.workplace_mentor_phone = self.workplace_mentor_phone.data
        model_instance.workplace_mentor_email = self.workplace_mentor_email.data
        return model_instance


class FormularzWniosek(FlaskForm):
    """Krok 2B/C: Wniosek dla ścieżek B i C."""
    employment_subtype  = SelectField('Rodzaj zatrudnienia', choices=[
        ('WORK',        'B.2 — Praca zawodowa (umowa o pracę / umowa zlecenie)'),
        ('INTERNSHIP',  'B.1 — Staż'),
    ], validators=[Optional()])
    pracodawca_nazwa    = StringField('Nazwa pracodawcy / firmy', validators=[DataRequired(message='Podaj nazwę.'), Length(max=255)])
    pracodawca_adres    = StringField('Adres', validators=[Optional(), Length(max=255)])
    pracodawca_miasto   = StringField('Miasto', validators=[Optional(), Length(max=100)])
    stanowisko          = StringField('Stanowisko / zakres działalności', validators=[DataRequired(message='Podaj stanowisko.'), Length(max=255)])
    justification        = TextAreaField('Uzasadnienie wniosku', validators=[DataRequired(message='Napisz uzasadnienie.'), Length(min=500, max=2000, message='Uzasadnienie musi mieć od 500 do 2000 znaków.')])


# ═══════════════════════════════════════════════════════════
# NOWE ROUTE KREATORA
# ═══════════════════════════════════════════════════════════

def _get_or_create_zapis(internship_id, istniejacy, odrzucony):
    if istniejacy:
        return istniejacy
    if odrzucony:
        odrzucony.status = EnrollmentStatus.PENDING
        _repo_zapisow.usun_zdarzenia_zapisu(odrzucony.id)
        return odrzucony
    zapis = InternshipEnrollment(
        id=uuid.uuid4(), internship_id=internship_id,
        student_id=current_user.id, status=EnrollmentStatus.PENDING,
        supervisor_id=getattr(current_user, 'supervisor_id', None),
    )
    _repo_zapisow.zapisz(zapis)
    return zapis


def _set_employment_subtype(zapis):
    employment_subtype = request.form.get('employment_subtype', '')
    if employment_subtype not in ('WORK', 'INTERNSHIP'):
        return
    uz = zapis.path_justification or PathJustification(enrollment_id=zapis.id)
    if uz not in db.session:
        db.session.add(uz)
    uz.employment_subtype = employment_subtype


@internships_bp.route('/<uuid:id>/kreator/path', methods=['GET', 'POST'])
@login_required
def kreator_sciezka(id):
    """Krok 1: Wybór ścieżki."""
    internship = _repo_praktyk.znajdz_po_id(id)
    if not internship:
        flash('Praktyka niedostępna.', 'danger')
        return redirect(url_for(_ROUTE_LISTA))

    istniejacy = _repo_zapisow.pending_dla_studenta_i_praktyki(current_user.id, id)

    # Jeśli jedyny istniejący zapis to REJECTED, traktujemy go jak nowy (reset)
    odrzucony = None
    if not istniejacy:
        odrzucony = _repo_zapisow.znajdz_odrzucony(current_user.id, id)

    form = FormularzSciezka()

    if form.validate_on_submit():
        zapis = _get_or_create_zapis(id, istniejacy, odrzucony)
        zapis.path_type = InternshipPath(form.track_type.data)

        if form.track_type.data != 'STANDARD':
            _set_employment_subtype(zapis)

        db.session.commit()

        if form.track_type.data == 'STANDARD':
            return redirect(url_for('internships.kreator_firma', enrollment_id=zapis.id))
        return redirect(url_for('internships.kreator_wniosek', enrollment_id=zapis.id))

    if istniejacy and request.method == 'GET':
        form.track_type.data = istniejacy.path_type.value if istniejacy.path_type else 'STANDARD'

    return render_template('kreator/krok1_sciezka.html', form=form, internship=internship, istniejacy=istniejacy)


def _save_company_from_form(form, zapis, dm) -> str | None:
    """Saves company data from form to zapis and dm. Returns error string or None."""
    if not form.ubezpieczenie_nw.data:
        return 'Ubezpieczenie NW jest wymagane.'
    if form.firma_typ.data == 'database':
        if not form.company_id.data:
            return 'Wybierz firmę z listy.'
        zapis.company_id = form.company_id.data
        dm.company_name = dm.company_address = dm.company_city = None
        dm.company_tax_id = dm.authorized_person = dm.authorized_person_position = None
    else:
        if not form.company_name.data or not form.company_address.data or not form.company_city.data:
            return 'Podaj nazwę, adres i miasto firmy.'
        zapis.company_id = None
        form.populate_to_model(dm)
    if not form.workplace_mentor_name.data or not form.workplace_mentor_email.data:
        return 'Podaj imię/nazwisko i email opiekuna zakładowego (ZOPZ).'
    if form.firma_typ.data == 'database':
        dm.workplace_mentor_name = form.workplace_mentor_name.data
        dm.workplace_mentor_position = form.workplace_mentor_position.data
        dm.workplace_mentor_phone = form.workplace_mentor_phone.data
        dm.workplace_mentor_email = form.workplace_mentor_email.data
    return None


def _populate_firma_form_from_zapis(form, zapis, dm) -> None:
    form.termin_od.data        = zapis.start_date
    form.termin_do.data        = zapis.end_date
    form.ubezpieczenie_nw.data = zapis.accident_insurance
    form.firma_typ.data = 'database' if zapis.company_id else 'custom'
    form.company_id.data  = str(zapis.company_id) if zapis.company_id else ''
    form.company_name.data                  = dm.company_name                  if dm else None
    form.company_address.data                  = dm.company_address               if dm else None
    form.company_zip.data           = dm.company_zip                   if dm else None
    form.company_city.data                 = dm.company_city                  if dm else None
    form.tax_id.data                = dm.company_tax_id                if dm else None
    form.authorized_person.data      = dm.authorized_person             if dm else None
    form.authorized_person_position.data = dm.authorized_person_position    if dm else None
    form.workplace_mentor_name.data = dm.workplace_mentor_name     if dm else None
    form.workplace_mentor_position.data    = dm.workplace_mentor_position  if dm else None
    form.workplace_mentor_phone.data       = dm.workplace_mentor_phone     if dm else None
    form.workplace_mentor_email.data         = dm.workplace_mentor_email     if dm else None


def _serialize_companies(companies):
    return {
        str(company.id): {
            'name': company.name,
            'address': company.address or '',
            'city': company.city or '',
            'tax_id': company.tax_id or '',
        }
        for company in companies
    }


@internships_bp.route('/zgloszenie/<uuid:enrollment_id>/kreator/company', methods=['GET', 'POST'])
@login_required
def kreator_firma(enrollment_id):
    """Krok 2A: Dane zakładu + ZOPZ (ścieżka A)."""
    zapis = _repo_zapisow.znajdz_po_id(enrollment_id)
    if not zapis or zapis.student_id != current_user.id or zapis.path_type != InternshipPath.STANDARD:
        abort(404)

    form = CompanyDataForm()
    firmy_list = company_repository.active()
    companies_data = _serialize_companies(firmy_list)
    form.company_id.choices = [('', '--- Wybierz firmę ---')] + [(str(f.id), f.name) for f in firmy_list]

    if form.validate_on_submit():
        zapis.start_date         = form.termin_od.data
        zapis.end_date           = form.termin_do.data
        zapis.accident_insurance = True
        zapis.specialization     = getattr(current_user, 'specialization', '') or ''

        dm = zapis.workplace_details or WorkplaceDetails(enrollment_id=zapis.id)
        if dm not in db.session:
            db.session.add(dm)

        err = _save_company_from_form(form, zapis, dm)
        if err:
            flash(err, 'danger')
            return render_template(
                _TPL_KR2A,
                form=form,
                zapis=zapis,
                firmy_list=firmy_list,
                companies_data=companies_data,
            )

        byl_status = zapis.status
        db.session.commit()
        if byl_status == EnrollmentStatus.AWAITING_APPROVAL:
            EnrollmentStateMachine(zapis).submit_to_committee()
            db.session.commit()
            flash('Dane zaktualizowane i zgłoszenie odesłane do komisji.', 'success')
            return redirect(url_for(_ROUTE_SZCZEGOLY, id=zapis.id))
        return redirect(url_for('internships.zapisz_krok2', id=zapis.id))

    if request.method == 'GET':
        _populate_firma_form_from_zapis(form, zapis, zapis.workplace_details)

    return render_template(
        _TPL_KR2A,
        form=form,
        zapis=zapis,
        firmy_list=firmy_list,
        companies_data=companies_data,
    )


def _populate_wniosek_form(form, zapis) -> None:
    dm = zapis.workplace_details
    uz = zapis.path_justification
    form.pracodawca_nazwa.data   = dm.company_name              if dm else None
    form.pracodawca_adres.data   = dm.company_address           if dm else None
    form.pracodawca_miasto.data  = dm.company_city              if dm else None
    form.stanowisko.data         = dm.workplace_mentor_position if dm else None
    form.justification.data       = uz.justification             if uz else None
    form.employment_subtype.data = uz.employment_subtype        if uz else 'WORK'


def _save_wniosek_post(form, zapis) -> None:
    dm = zapis.workplace_details or WorkplaceDetails(enrollment_id=zapis.id)
    if dm not in db.session:
        db.session.add(dm)
    dm.company_name              = form.pracodawca_nazwa.data
    dm.company_address           = form.pracodawca_adres.data
    dm.company_city              = form.pracodawca_miasto.data
    dm.workplace_mentor_position = form.stanowisko.data

    uz = zapis.path_justification or PathJustification(enrollment_id=zapis.id)
    if uz not in db.session:
        db.session.add(uz)
    uz.justification      = form.justification.data
    uz.employment_subtype = form.employment_subtype.data


@internships_bp.route('/zgloszenie/<uuid:enrollment_id>/kreator/wniosek', methods=['GET', 'POST'])
@login_required
def kreator_wniosek(enrollment_id):
    """Krok 2B/C: Wniosek dla ścieżek B i C."""
    zapis = _repo_zapisow.znajdz_po_id(enrollment_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.path_type == InternshipPath.STANDARD:
        return redirect(url_for('internships.kreator_firma', enrollment_id=enrollment_id))

    form = FormularzWniosek()

    if form.validate_on_submit():
        _save_wniosek_post(form, zapis)
        db.session.commit()
        return redirect(url_for('internships.potwierdz_wyslanie', id=zapis.id))

    if request.method == 'GET':
        _populate_wniosek_form(form, zapis)

    return render_template('kreator/krok2bc_wniosek.html', form=form, zapis=zapis)




def _kreator_url(info: dict, internship_id) -> str:
    """Adres kroku kreatora, do którego wraca student przy edycji/kontynuacji."""
    if info['is_standard']:
        return url_for('internships.kreator_firma', enrollment_id=info['id'])
    if info['path'] in ('EMPLOYMENT', 'OWN_BUSINESS'):
        return url_for('internships.kreator_wniosek', enrollment_id=info['id'])
    return url_for('internships.kreator_sciezka', id=internship_id)


@internships_bp.route('/', methods=['GET'])
@login_required
def lista():
    available  = _repo_praktyk.active()
    status_map = {}
    for z in _repo_zapisow.dla_studenta(current_user.id):
        info = InternshipService.student_status(z)
        info['kreator_url'] = _kreator_url(info, z.internship_id)
        status_map[str(z.internship_id)] = info

    csrf_form = FlaskForm()
    return render_template('praktyki/lista.html', dostepne=available, zapisy_data=status_map, csrf_form=csrf_form)


@internships_bp.route('/zgloszenie/<uuid:id>/complete', methods=['POST'])
@login_required
def zakoncz_praktyke(id):
    zapis = _repo_zapisow.znajdz_po_id(id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status != EnrollmentStatus.IN_PROGRESS:
        flash('Praktykę można zakończyć tylko gdy jest w trakcie realizacji.', 'warning')
        return redirect(url_for(_ROUTE_LISTA))

    path_val = zapis.path_type.value if hasattr(zapis.path_type, 'value') else str(zapis.path_type)
    if path_val == 'STANDARD':
        ok, msg = InternshipService.validate_completion_allowed(zapis)
        if not ok:
            flash(msg, 'danger')
            return redirect(url_for(_ROUTE_LISTA))

    EnrollmentStateMachine(zapis).complete()
    db.session.commit()
    flash('Praktyka została zakończona. Dokumenty końcowe są dostępne w zakładce Moje Dokumenty.', 'success')
    return redirect(url_for(_ROUTE_LISTA))


@internships_bp.route('/<uuid:id>/zapisz/krok1', methods=['GET'])
@login_required
def zapisz_krok1(id):
    """Stara trasa — przekierowanie do nowego kreatora."""
    return redirect(url_for('internships.kreator_sciezka', id=id))



@internships_bp.route('/zgloszenie/<uuid:id>/krok2', methods=['GET', 'POST'])
@login_required
def zapisz_krok2(id):
    zapis = _repo_zapisow.znajdz_po_id(id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
        
    efekty = _repo_efektow.wszystkie()

    if request.method == 'POST':
        # Czyszczenie starego jeśli student wraca z jakiegoś powodu
        _repo_zapisow.usun_harmonogram(zapis.id)
        
        nowe_wiersze = []
        for e in efekty:
            dz = request.form.get(f'dzial_{e.id}', '')
            pr = request.form.get(f'prace_{e.id}', '')
            dni_str = request.form.get(f'dni_{e.id}', '0')
            try:
                dni = int(dni_str)
            except (TypeError, ValueError):
                dni = 0

            if dz.strip() and pr.strip():
                nowe_wiersze.append(InternshipSchedule(
                    id=uuid.uuid4(),
                    enrollment_id=zapis.id,
                    learning_outcome_id=e.id,
                    department_name=dz,
                    example_tasks=pr,
                    days_count=dni
                ))
                
        _repo_zapisow.zapisz_harmonogram(nowe_wiersze)
        db.session.commit()

        return redirect(url_for('internships.potwierdz_wyslanie', id=zapis.id))
    else:
        # GET request - pobranie istniejących danych harmonogramu
        istniejace_harmonogramy = {}
        harmonogramy = _repo_zapisow.harmonogram_dla_zapisu(zapis.id)
        for h in harmonogramy:
            istniejace_harmonogramy[str(h.learning_outcome_id)] = {
                'dzial': h.department_name,
                'prace': h.example_tasks,
                'dni': h.days_count
            }

    csrf_form = FlaskForm()

    return render_template('kreator/krok3_harmonogram.html',
                         zapis=zapis,
                         efekty=efekty,
                         csrf_form=csrf_form,
                         istniejace_harmonogramy=istniejace_harmonogramy)


@internships_bp.route('/zgloszenie/<uuid:id>/potwierdz-wyslanie', methods=['GET'])
@login_required
def potwierdz_wyslanie(id):
    zapis = _repo_zapisow.znajdz_po_id(id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status not in (EnrollmentStatus.PENDING, EnrollmentStatus.REVISION_REQUIRED):
        return redirect(url_for(_ROUTE_SZCZEGOLY, id=id))
    from flask_wtf import FlaskForm
    csrf_form = FlaskForm()
    return render_template('kreator/potwierdz_wyslanie.html', zapis=zapis, csrf_form=csrf_form)


@internships_bp.route('/zgloszenie/<uuid:id>/wyslij', methods=['POST'])
@login_required
def wyslij_do_zatwierdzenia(id):
    zapis = _repo_zapisow.znajdz_po_id(id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status not in (EnrollmentStatus.PENDING, EnrollmentStatus.REVISION_REQUIRED):
        flash('Zgłoszenie zostało już wysłane.', 'info')
        return redirect(url_for(_ROUTE_SZCZEGOLY, id=id))
    from core.services.workflow import EnrollmentStateMachine
    fsm = EnrollmentStateMachine(zapis)
    if zapis.path_type and zapis.path_type.value in ('EMPLOYMENT', 'OWN_BUSINESS'):
        fsm.submit_to_committee()
    else:
        fsm.submit_for_approval()
    db.session.commit()
    flash('Zgłoszenie zostało przesłane.', 'success')
    return redirect(url_for(_ROUTE_LISTA))


@internships_bp.route('/zgloszenie/<uuid:id>/szczegoly', methods=['GET'])
@login_required
def szczegoly_zgloszenia(id):
    """Szczegóły zgłoszenia studenta wraz z komentarzami UOPZ"""
    zapis = _repo_zapisow.znajdz_po_id(id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    rows = _repo_docs.dla_zapisu_studenta(id, current_user.id)
    uploaded_docs = [
        {
            'id': str(d.id),
            'original_filename': d.original_filename,
            'document_type': d.document_type,
            'uploaded_at': d.uploaded_at,
        }
        for d in rows
    ]

    schedule = _repo_zapisow.harmonogram_dla_zapisu(id)
    efekty = _repo_efektow.wszystkie()
    harmonogram_dict = {str(h.learning_outcome_id): h for h in schedule}

    from flask_wtf import FlaskForm
    komentarz_komisji = None
    if zapis.status == EnrollmentStatus.REVISION_REQUIRED:
        ev = _repo_zapisow.ostatnie_zdarzenie(
            id, event_type=EventType.COMMITTEE_DECISION, decision='PARTIALLY_APPROVED'
        )
        komentarz_komisji = ev.comment if ev else None

    csrf_form = FlaskForm()
    return render_template('praktyki/szczegoly_zgloszenia.html', zapis=zapis,
                           uploaded_docs=uploaded_docs, csrf_form=csrf_form,
                           komentarz_komisji=komentarz_komisji,
                           harmonogram_dict=harmonogram_dict, efekty=efekty)


@internships_bp.route('/zgloszenie/<uuid:id>/resubmit', methods=['POST'])
@login_required
def resubmit_zgloszenia(id):
    """Student ponownie wysyła zgłoszenie po poprawkach."""
    zapis = _repo_zapisow.znajdz_po_id(id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status not in (EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.REVISION_REQUIRED):
        flash('Zgłoszenie nie może być ponownie wysłane w tym statusie.', 'warning')
        return redirect(url_for(_ROUTE_SZCZEGOLY, id=id))
    try:
        with EnrollmentStateMachine.lock(id) as fsm:
            if zapis.status == EnrollmentStatus.REVISION_REQUIRED:
                fsm.resubmit_after_revision()
            else:
                fsm.submit_to_committee()
            db.session.commit()
    except IllegalTransitionError as e:
        flash(str(e), 'danger')
        return redirect(url_for(_ROUTE_SZCZEGOLY, id=id))
    flash('Zgłoszenie zostało ponownie wysłane do weryfikacji komisji.', 'success')
    return redirect(url_for(_ROUTE_SZCZEGOLY, id=id))
