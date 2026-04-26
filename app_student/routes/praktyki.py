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
from core.modele import (Internship, InternshipEnrollment, InternshipStatus, EnrollmentStatus,
                         InternshipPath, LearningOutcome, InternshipSchedule, Company,
                         IndividualProgram, DocumentStatus, UploadedDocument,
                         WorkplaceDetails, PathJustification)
from core.modele.praktyki import EventType
from core.uslugi.workflow import ZapisFSM, IllegalTransitionError
from core.uslugi.praktyki import UslugaPraktyk
from core.repozytoria import (InternshipRepository, EnrollmentRepository,
                               OutcomeRepository, CompanyRepository,
                               StudentDocumentRepository)

_repo_praktyk = InternshipRepository()
_repo_zapisow = EnrollmentRepository()
_repo_efektow = OutcomeRepository()
_repo_firm    = CompanyRepository()
_repo_docs    = StudentDocumentRepository()

praktyki_bp = Blueprint('praktyki', __name__)


# ═══════════════════════════════════════════════════════════
# NOWE FORMULARZE KREATORA
# ═══════════════════════════════════════════════════════════

class FormularzSciezka(FlaskForm):
    """Krok 1: Tylko wybór ścieżki."""
    track_type = SelectField('Ścieżka praktyki', choices=[
        ('STANDARD',   'A — Standardowa praktyka'),
        ('EMPLOYMENT', 'B — Uznanie efektów z pracy zawodowej'),
    ], validators=[DataRequired(message='Wybierz ścieżkę.')])


class FormularzDaneFirmy(FlaskForm):
    """Krok 2A: Dane zakładu pracy + ZOPZ + terminy (tylko ścieżka A)."""
    # Terminy i dane podstawowe
    termin_od        = DateField('Data rozpoczęcia', validators=[DataRequired(message='Podaj datę.')])
    termin_do        = DateField('Data zakończenia', validators=[DataRequired(message='Podaj datę.')])
    ubezpieczenie_nw = BooleanField('Posiadam ubezpieczenie NW na czas trwania praktyki')

    # Tryb znalezienia miejsca
    firma_typ  = SelectField('Jak znalazłeś/-aś miejsce praktyki?', choices=[
        ('database', 'Uczelnia kieruje do zakładu (firma ma umowę z ANS)'),
        ('custom',   'Sam/a znalazłem/-am miejsce (wymaga Zał. 9 i Zał. 1)'),
    ], validators=[DataRequired()])
    firma_id   = SelectField('Wybierz firmę z listy', choices=[], validators=[Optional()])

    firma_nazwa                  = StringField('Nazwa zakładu pracy', validators=[Optional(), Length(max=255)])
    firma_adres                  = StringField('Adres (ulica, nr)', validators=[Optional(), Length(max=255)])
    firma_kod_pocztowy           = StringField('Kod pocztowy', validators=[Optional(), Length(max=10)])
    firma_miasto                 = StringField('Miasto', validators=[Optional(), Length(max=100)])
    firma_nip_krs                = StringField('NIP / KRS', validators=[Optional(), Length(max=50)])
    firma_upowazniony_osoba      = StringField('Osoba upoważniona do podpisania porozumienia', validators=[Optional(), Length(max=255)])
    firma_upowazniony_stanowisko = StringField('Stanowisko osoby upoważnionej', validators=[Optional(), Length(max=255)])

    zopz_imie_nazwisko = StringField('Opiekun zakładowy (ZOPZ) — imię i nazwisko', validators=[Optional(), Length(max=255)])
    zopz_stanowisko    = StringField('Stanowisko ZOPZ', validators=[Optional(), Length(max=255)])
    zopz_telefon       = StringField('Telefon ZOPZ', validators=[Optional(), Length(max=50)])
    zopz_email         = StringField('E-mail ZOPZ', validators=[Optional(), Email(message='Nieprawidłowy email.')])

    def validate_firma_kod_pocztowy(self, field):
        if not field.data:
            return
        if not re.fullmatch(r'\d{2}-\d{3}', field.data.strip()):
            raise ValidationError('Podaj kod pocztowy w formacie XX-XXX (np. 82-300).')

    def validate_zopz_imie_nazwisko(self, field):
        if not field.data:
            return
        parts = field.data.strip().split()
        if len(parts) < 2:
            raise ValidationError('Podaj imię i nazwisko (co najmniej dwa wyrazy).')
        if any(char.isdigit() for char in field.data):
            raise ValidationError('Imię i nazwisko nie może zawierać cyfr.')

    def validate_firma_upowazniony_osoba(self, field):
        if not field.data:
            return
        parts = field.data.strip().split()
        if len(parts) < 2:
            raise ValidationError('Podaj imię i nazwisko osoby upoważnionej (co najmniej dwa wyrazy).')
        if any(char.isdigit() for char in field.data):
            raise ValidationError('Imię i nazwisko nie może zawierać cyfr.')


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
    uzasadnienie        = TextAreaField('Uzasadnienie wniosku', validators=[DataRequired(message='Napisz uzasadnienie.'), Length(min=500, max=2000, message='Uzasadnienie musi mieć od 500 do 2000 znaków.')])


# ═══════════════════════════════════════════════════════════
# NOWE ROUTE KREATORA
# ═══════════════════════════════════════════════════════════

@praktyki_bp.route('/<uuid:id>/kreator/sciezka', methods=['GET', 'POST'])
@login_required
def kreator_sciezka(id):
    """Krok 1: Wybór ścieżki."""
    praktyka = _repo_praktyk.znajdz_po_id(id)
    if not praktyka:
        flash('Praktyka niedostępna.', 'danger')
        return redirect(url_for('praktyki.lista'))

    istniejacy = _repo_zapisow.pending_dla_studenta_i_praktyki(current_user.id, id)

    # Jeśli jedyny istniejący zapis to REJECTED, traktujemy go jak nowy (reset)
    odrzucony = None
    if not istniejacy:
        odrzucony = _repo_zapisow.znajdz_odrzucony(current_user.id, id)

    form = FormularzSciezka()

    if form.validate_on_submit():
        if istniejacy:
            zapis = istniejacy
        elif odrzucony:
            zapis = odrzucony
            zapis.status = EnrollmentStatus.PENDING
            _repo_zapisow.usun_zdarzenia_zapisu(zapis.id)
        else:
            zapis = InternshipEnrollment(id=uuid.uuid4(), internship_id=id,
                                   student_id=current_user.id, status=EnrollmentStatus.PENDING,
                                   supervisor_id=getattr(current_user, 'supervisor_id', None))
            _repo_zapisow.zapisz(zapis)

        zapis.track_type = InternshipPath(form.track_type.data)

        if form.track_type.data != 'STANDARD':
            employment_subtype = request.form.get('employment_subtype', '')
            if employment_subtype in ('WORK', 'INTERNSHIP'):
                uz = zapis.path_justification or PathJustification(enrollment_id=zapis.id)
                if uz not in db.session:
                    db.session.add(uz)
                uz.employment_subtype = employment_subtype

        db.session.commit()

        if form.track_type.data == 'STANDARD':
            return redirect(url_for('praktyki.kreator_firma', zapis_id=zapis.id))
        else:
            return redirect(url_for('praktyki.kreator_wniosek', zapis_id=zapis.id))

    if istniejacy and request.method == 'GET':
        form.track_type.data = istniejacy.track_type.value if istniejacy.track_type else 'STANDARD'

    return render_template('kreator/krok1_sciezka.html', form=form, praktyka=praktyka, istniejacy=istniejacy)


@praktyki_bp.route('/zgloszenie/<uuid:zapis_id>/kreator/firma', methods=['GET', 'POST'])
@login_required
def kreator_firma(zapis_id):
    """Krok 2A: Dane zakładu + ZOPZ (ścieżka A)."""
    zapis = _repo_zapisow.znajdz_po_id(zapis_id)
    if not zapis or zapis.student_id != current_user.id or zapis.track_type != InternshipPath.STANDARD:
        abort(404)

    form = FormularzDaneFirmy()
    firmy_list = _repo_firm.aktywne()
    form.firma_id.choices = [('', '--- Wybierz firmę ---')] + [(str(f.id), f.name) for f in firmy_list]

    if form.validate_on_submit():
        if not form.ubezpieczenie_nw.data:
            flash('Ubezpieczenie NW jest wymagane.', 'danger')
            return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)

        zapis.start_date         = form.termin_od.data
        zapis.end_date           = form.termin_do.data
        zapis.accident_insurance = True
        zapis.specialization     = getattr(current_user, 'specialization', '') or ''

        dm = zapis.workplace_details or WorkplaceDetails(enrollment_id=zapis.id)
        if dm not in db.session:
            db.session.add(dm)

        if form.firma_typ.data == 'database':
            if not form.firma_id.data:
                flash('Wybierz firmę z listy.', 'danger')
                return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)
            zapis.company_id = form.firma_id.data
            dm.company_name = dm.company_address = dm.company_city = None
            dm.company_tax_id = dm.authorized_person = dm.authorized_person_position = None
        else:
            if not form.firma_nazwa.data or not form.firma_adres.data or not form.firma_miasto.data:
                flash('Podaj nazwę, adres i miasto firmy.', 'danger')
                return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)
            zapis.company_id = None
            dm.company_name                  = form.firma_nazwa.data
            dm.company_address               = form.firma_adres.data
            dm.company_zip                   = form.firma_kod_pocztowy.data or None
            dm.company_city                  = form.firma_miasto.data
            dm.company_tax_id                = form.firma_nip_krs.data
            dm.authorized_person             = form.firma_upowazniony_osoba.data
            dm.authorized_person_position    = form.firma_upowazniony_stanowisko.data

        if not form.zopz_imie_nazwisko.data or not form.zopz_email.data:
            flash('Podaj imię/nazwisko i email opiekuna zakładowego (ZOPZ).', 'danger')
            return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)

        dm.workplace_mentor_name     = form.zopz_imie_nazwisko.data
        dm.workplace_mentor_position = form.zopz_stanowisko.data
        dm.workplace_mentor_phone    = form.zopz_telefon.data
        dm.workplace_mentor_email    = form.zopz_email.data
        byl_status = zapis.status
        db.session.commit()
        if byl_status == EnrollmentStatus.AWAITING_APPROVAL:
            ZapisFSM(zapis).wyslij_do_komisji()
            db.session.commit()
            flash('Dane zaktualizowane i zgłoszenie odesłane do komisji.', 'success')
            return redirect(url_for('praktyki.szczegoly_zgloszenia', id=zapis.id))
        # PENDING i REVISION_REQUIRED → harmonogram → wyślij
        return redirect(url_for('praktyki.zapisz_krok2', id=zapis.id))

    if request.method == 'GET':
        dm = zapis.workplace_details
        form.termin_od.data        = zapis.start_date
        form.termin_do.data        = zapis.end_date
        form.ubezpieczenie_nw.data = zapis.accident_insurance
        form.firma_typ.data = 'database' if zapis.company_id else 'custom'
        form.firma_id.data  = str(zapis.company_id) if zapis.company_id else ''
        form.firma_nazwa.data                  = dm.company_name                  if dm else None
        form.firma_adres.data                  = dm.company_address               if dm else None
        form.firma_kod_pocztowy.data           = dm.company_zip                   if dm else None
        form.firma_miasto.data                 = dm.company_city                  if dm else None
        form.firma_nip_krs.data                = dm.company_tax_id                if dm else None
        form.firma_upowazniony_osoba.data      = dm.authorized_person             if dm else None
        form.firma_upowazniony_stanowisko.data = dm.authorized_person_position    if dm else None
        form.zopz_imie_nazwisko.data = dm.workplace_mentor_name     if dm else None
        form.zopz_stanowisko.data    = dm.workplace_mentor_position  if dm else None
        form.zopz_telefon.data       = dm.workplace_mentor_phone     if dm else None
        form.zopz_email.data         = dm.workplace_mentor_email     if dm else None

    return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)


@praktyki_bp.route('/zgloszenie/<uuid:zapis_id>/kreator/wniosek', methods=['GET', 'POST'])
@login_required
def kreator_wniosek(zapis_id):
    """Krok 2B/C: Wniosek dla ścieżek B i C."""
    zapis = _repo_zapisow.znajdz_po_id(zapis_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.track_type == InternshipPath.STANDARD:
        return redirect(url_for('praktyki.kreator_firma', zapis_id=zapis_id))

    form = FormularzWniosek()

    if form.validate_on_submit():
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
        uz.justification      = form.uzasadnienie.data
        uz.employment_subtype = form.employment_subtype.data

        db.session.commit()
        return redirect(url_for('praktyki.potwierdz_wyslanie', id=zapis.id))

    if request.method == 'GET':
        dm = zapis.workplace_details
        uz = zapis.path_justification
        form.pracodawca_nazwa.data     = dm.company_name              if dm else None
        form.pracodawca_adres.data     = dm.company_address           if dm else None
        form.pracodawca_miasto.data    = dm.company_city              if dm else None
        form.stanowisko.data           = dm.workplace_mentor_position if dm else None
        form.uzasadnienie.data         = uz.justification             if uz else None
        form.employment_subtype.data   = uz.employment_subtype        if uz else 'WORK'

    return render_template('kreator/krok2bc_wniosek.html', form=form, zapis=zapis)




@praktyki_bp.route('/', methods=['GET'])
@login_required
def lista():
    available  = _repo_praktyk.aktywne()
    status_map = {
        str(z.internship_id): UslugaPraktyk.status_dla_studenta(z)
        for z in _repo_zapisow.dla_studenta(current_user.id)
    }

    csrf_form = FlaskForm()
    return render_template('praktyki/lista.html', dostepne=available, zapisy_data=status_map, csrf_form=csrf_form)


@praktyki_bp.route('/zgloszenie/<uuid:id>/zakoncz', methods=['POST'])
@login_required
def zakoncz_praktyke(id):
    zapis = _repo_zapisow.znajdz_po_id(id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status != EnrollmentStatus.IN_PROGRESS:
        flash('Praktykę można zakończyć tylko gdy jest w trakcie realizacji.', 'warning')
        return redirect(url_for('praktyki.lista'))

    path_val = zapis.path_type.value if hasattr(zapis.path_type, 'value') else str(zapis.path_type)
    if path_val == 'STANDARD':
        ok, msg = UslugaPraktyk.waliduj_mozliwosc_zakonczenia(zapis)
        if not ok:
            flash(msg, 'danger')
            return redirect(url_for('praktyki.lista'))

    ZapisFSM(zapis).zakoncz()
    db.session.commit()
    flash('Praktyka została zakończona. Dokumenty końcowe są dostępne w zakładce Moje Dokumenty.', 'success')
    return redirect(url_for('praktyki.lista'))


@praktyki_bp.route('/<uuid:id>/zapisz/krok1', methods=['GET'])
@login_required
def zapisz_krok1(id):
    """Stara trasa — przekierowanie do nowego kreatora."""
    return redirect(url_for('praktyki.kreator_sciezka', id=id))



@praktyki_bp.route('/zgloszenie/<uuid:id>/krok2', methods=['GET', 'POST'])
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
            except Exception:
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

        return redirect(url_for('praktyki.potwierdz_wyslanie', id=zapis.id))
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


@praktyki_bp.route('/zgloszenie/<uuid:id>/potwierdz-wyslanie', methods=['GET'])
@login_required
def potwierdz_wyslanie(id):
    zapis = _repo_zapisow.znajdz_po_id(id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status not in (EnrollmentStatus.PENDING, EnrollmentStatus.REVISION_REQUIRED):
        return redirect(url_for('praktyki.szczegoly_zgloszenia', id=id))
    from flask_wtf import FlaskForm
    csrf_form = FlaskForm()
    return render_template('kreator/potwierdz_wyslanie.html', zapis=zapis, csrf_form=csrf_form)


@praktyki_bp.route('/zgloszenie/<uuid:id>/wyslij', methods=['POST'])
@login_required
def wyslij_do_zatwierdzenia(id):
    zapis = _repo_zapisow.znajdz_po_id(id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status not in (EnrollmentStatus.PENDING, EnrollmentStatus.REVISION_REQUIRED):
        flash('Zgłoszenie zostało już wysłane.', 'info')
        return redirect(url_for('praktyki.szczegoly_zgloszenia', id=id))
    from core.uslugi.workflow import ZapisFSM
    fsm = ZapisFSM(zapis)
    if zapis.path_type and zapis.path_type.value in ('EMPLOYMENT', 'OWN_BUSINESS'):
        fsm.wyslij_do_komisji()
    else:
        fsm.wyslij_do_akceptacji()
    db.session.commit()
    flash('Zgłoszenie zostało przesłane.', 'success')
    return redirect(url_for('praktyki.lista'))


@praktyki_bp.route('/zgloszenie/<uuid:id>/szczegoly', methods=['GET'])
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

    harmonogram = _repo_zapisow.harmonogram_dla_zapisu(id)
    efekty = _repo_efektow.wszystkie()
    harmonogram_dict = {str(h.learning_outcome_id): h for h in harmonogram}

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


@praktyki_bp.route('/zgloszenie/<uuid:id>/resubmit', methods=['POST'])
@login_required
def resubmit_zgloszenia(id):
    """Student ponownie wysyła zgłoszenie po poprawkach."""
    zapis = _repo_zapisow.znajdz_po_id(id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status not in (EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.REVISION_REQUIRED):
        flash('Zgłoszenie nie może być ponownie wysłane w tym statusie.', 'warning')
        return redirect(url_for('praktyki.szczegoly_zgloszenia', id=id))
    try:
        with ZapisFSM.lock(id) as fsm:
            if zapis.status == EnrollmentStatus.REVISION_REQUIRED:
                fsm.wyslij_ponownie_po_poprawkach()
            else:
                fsm.wyslij_do_komisji()
            db.session.commit()
    except IllegalTransitionError as e:
        flash(str(e), 'danger')
        return redirect(url_for('praktyki.szczegoly_zgloszenia', id=id))
    flash('Zgłoszenie zostało ponownie wysłane do weryfikacji komisji.', 'success')
    return redirect(url_for('praktyki.szczegoly_zgloszenia', id=id))


