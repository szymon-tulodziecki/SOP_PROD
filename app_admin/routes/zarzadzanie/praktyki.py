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
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError
from werkzeug.security import generate_password_hash

from core.modele import (User, Student, Internship, InternshipEnrollment, InternshipSchedule, LearningOutcome,
                    UserRole, InternshipStatus, EnrollmentStatus, InternshipPath, UploadedDocument, Company)
from core.extensions import db
from core.uslugi import UslugaUzytkownikow as _UslugaUzytkownikow
_serwis_uzytkownikow = _UslugaUzytkownikow()
from core.autoryzacja import wymaga_roli
from core.repozytoria import (RepozytoriumPraktyk, RepozytoriumZapisow,
                               RepozytoriumUzytkownikow, RepozytoriumEfektow,
                               RepozytoriumDokumentowStudenta)

_repo_praktyk = RepozytoriumPraktyk()
_repo_zapisow = RepozytoriumZapisow()
_repo_uzytk   = RepozytoriumUzytkownikow()
_repo_efektow = RepozytoriumEfektow()
_repo_docs    = RepozytoriumDokumentowStudenta()

from . import zarzadzanie_bp
from .formularze import *

# ── Praktyki ──────────────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/praktyki')
@login_required
def lista_praktyk():
    strona = request.args.get('strona', 1, type=int)
    praktyki = _repo_praktyk.lista_strona(strona=strona)
    do_usuniecia = _repo_praktyk.do_usuniecia()
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/praktyki.html', praktyki=praktyki,
                           do_usuniecia=do_usuniecia, csrf_form=csrf_form)


@zarzadzanie_bp.route('/praktyki/nowa', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def nowa_praktyka():
    form = FormularzPraktyki()
    if form.validate_on_submit():
        rok = (form.rok_uczelniany.data or '').strip()
        try:
            wymiar = int(form.wymiar_godzin.data)
        except Exception:
            flash('Wymiar godzin musi być liczbą całkowitą.', 'danger')
            return render_template('zarzadzanie/formularz_praktyki.html', form=form)
        p = Internship(
            id             = uuid.uuid4(),
            academic_year  = rok,
            semester       = form.semestr.data,
            required_hours = wymiar,
            status         = InternshipStatus.INACTIVE,  # noqa: forms use Polish field names deliberately
        )
        db.session.add(p)
        db.session.commit()
        flash('Internship została utworzona.', 'success')
        return redirect(url_for('zarzadzanie.lista_praktyk'))
    return render_template('zarzadzanie/formularz_praktyki.html', form=form)


@zarzadzanie_bp.route('/praktyki/<uuid:id>/aktywnosc', methods=['POST'])
@wymaga_roli(UserRole.ADMIN)
def przelacz_aktywnosc_praktyki(id):
    p = db.session.get(Internship, id) or abort(404)
    p.status = InternshipStatus.INACTIVE if p.status == InternshipStatus.ACTIVE else InternshipStatus.ACTIVE
    db.session.commit()
    stan = 'aktywowana' if p.status == InternshipStatus.ACTIVE else 'dezaktywowana'
    flash(f'Praktyka {p.academic_year} ({p.semester}) została {stan}.', 'success')
    return redirect(url_for('zarzadzanie.lista_praktyk'))


# ── Zgłoszenia studentów ──────────────────────────────────────────────────────

class FormularzPrzypiszUOPZ(FlaskForm):
    uopz_id = SelectField('Opiekun uczelniany (UOPZ)', choices=[], validators=[Optional()])


@zarzadzanie_bp.route('/zgloszenia')
@wymaga_roli(UserRole.ADMIN, UserRole.KOMISJA, UserRole.DYREKTOR, UserRole.UOPZ)
def lista_zgloszen():
    strona        = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()

    uopz_id = current_user.id if current_user.role == UserRole.UOPZ else None
    try:
        zgloszenia = _repo_zapisow.lista_zgloszen_strona(status_filter=status_filter, strona=strona, supervisor_id=uopz_id)
    except ValueError:
        flash(f'Nieznany status: {status_filter}', 'warning')
        zgloszenia = _repo_zapisow.lista_zgloszen_strona(strona=strona, supervisor_id=uopz_id)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/enrollments/list.html', zgloszenia=zgloszenia, csrf_form=csrf_form)


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/przypisz-uopz', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def przypisz_uopz(id):
    zapis     = db.session.get(InternshipEnrollment, id) or abort(404)
    form      = FormularzPrzypiszUOPZ()
    uopz_list = _repo_uzytk.aktywni_uopz()
    form.uopz_id.choices = [('', '--- brak ---')] + [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]

    if form.validate_on_submit():
        if form.uopz_id.data:
            from core.uslugi.workflow import ZapisFSM, IllegalTransitionError
            try:
                with ZapisFSM.lock(id) as fsm:
                    fsm.zapis.supervisor_id = form.uopz_id.data
                    fsm.wyslij_do_akceptacji()
                    db.session.commit()
                flash('Opiekun UOPZ przypisany, zgłoszenie przekazane do zatwierdzenia.', 'success')
            except IllegalTransitionError as e:
                flash(str(e), 'danger')
        else:
            flash('Nie wybrano opiekuna.', 'warning')
        return redirect(url_for('zarzadzanie.lista_zgloszen'))

    if request.method == 'GET':
        form.uopz_id.data = str(zapis.supervisor_id) if zapis.supervisor_id else ''

    return render_template('zarzadzanie/enrollments/przypisz_uopz.html', form=form, zapis=zapis)


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/szczegoly', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ, UserRole.KOMISJA, UserRole.DYREKTOR)
def szczegoly_zgloszenia(id):
    zapis = db.session.get(InternshipEnrollment, id) or abort(404)

    if current_user.role == UserRole.UOPZ and zapis.supervisor_id != current_user.id:
        abort(403)
    # KOMISJA i DYREKTOR mają wgląd w każde zgłoszenie (read-only flow)

    harmonogram      = _repo_zapisow.harmonogram_dla_zapisu(id)
    harmonogram_dict = {h.learning_outcome_id: h for h in harmonogram}
    efekty           = _repo_efektow.wszystkie()

    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SubmitField

    class FormularzKomentarza(FlaskForm):
        komentarz = TextAreaField('Komentarz do studenta')
        zatwierdz = SubmitField('Zatwierdź zgłoszenie')
        odrzuc    = SubmitField('Wymagane poprawki')

    form = FormularzKomentarza()

    if form.validate_on_submit():
        from core.uslugi.workflow import ZapisFSM, IllegalTransitionError

        try:
            with ZapisFSM.lock(id) as fsm:
                komentarz = form.komentarz.data or ''
                if form.zatwierdz.data:
                    fsm.zatwierdz_przez_uopz(actor_id=current_user.id, comment=komentarz)
                    flash('Zgłoszenie zostało zatwierdzone!', 'success')
                elif form.odrzuc.data:
                    fsm.zadaj_poprawki(actor_id=current_user.id, comment=komentarz)
                    flash('Wysłano prośbę o poprawki do studenta.', 'info')
                db.session.commit()
        except IllegalTransitionError as e:
            flash(str(e), 'danger')
        return redirect(url_for('zarzadzanie.lista_zgloszen'))

    uploaded_docs = _repo_docs.dla_zapisu_studenta(id, zapis.student_id)

    return render_template('zarzadzanie/enrollments/szczegoly.html',
                           zapis=zapis, harmonogram_dict=harmonogram_dict,
                           efekty=efekty, form=form, uploaded_docs=uploaded_docs)


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/zatwierdz-zaklad', methods=['POST'])
@wymaga_roli(UserRole.UOPZ, UserRole.ADMIN)
def zatwierdz_zaklad(id):
    from core.uslugi.workflow import ZapisFSM, IllegalTransitionError
    try:
        with ZapisFSM.lock(id) as fsm:
            fsm.zatwierdz_przez_uopz()
            db.session.commit()
        flash('Zakład zatwierdzony. Internship rozpoczęła się.', 'success')
    except IllegalTransitionError as e:
        flash(str(e), 'danger')
    return redirect(url_for('zarzadzanie.lista_zgloszen'))


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/potwierdz', methods=['POST'])
@wymaga_roli(UserRole.ADMIN, UserRole.UOPZ)
def potwierdz_zapis(id):
    from core.uslugi.workflow import ZapisFSM, IllegalTransitionError
    try:
        with ZapisFSM.lock(id) as fsm:
            fsm.zatwierdz_przez_uopz()
            if current_user.role == UserRole.UOPZ:
                fsm.zapis.supervisor_id = current_user.id
            db.session.commit()
        flash('Zapis studenta na praktykę został potwierdzony. Zostałeś/aś przypisany/a jako opiekun.', 'success')
    except IllegalTransitionError as e:
        flash(str(e), 'danger')
    return redirect(request.referrer or url_for('dashboard.index'))


@zarzadzanie_bp.route('/moje-zgloszenia')
@wymaga_roli(UserRole.UOPZ)
def moje_zgloszenia():
    """Lista zgłoszeń przypisanych do aktualnego UOPZ"""
    from app_admin.routes.ocenianie import get_pilne_oceny

    strona        = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()

    try:
        zgloszenia = _repo_zapisow.dla_uopz_strona(
            current_user.id, status_filter=status_filter, strona=strona
        )
    except ValueError:
        flash(f'Nieznany status: {status_filter}', 'warning')
        zgloszenia = _repo_zapisow.dla_uopz_strona(current_user.id, strona=strona)

    liczniki    = _repo_zapisow.liczniki_dla_uopz(current_user.id)
    pilne_oceny = get_pilne_oceny(current_user.id)
    csrf_form   = FlaskForm()
    return render_template('zarzadzanie/enrollments/moje_lista.html',
                           zgloszenia=zgloszenia, liczniki=liczniki,
                           pilne_oceny=pilne_oceny, csrf_form=csrf_form)


@zarzadzanie_bp.route('/praktyki/<uuid:id>/usun', methods=['POST'])
@wymaga_roli(UserRole.ADMIN)
def usun_praktyke(id):
    from datetime import datetime, timezone
    p    = db.session.get(Internship, id) or abort(404)
    opis = f'{p.academic_year} ({p.semester})'
    if p.enrollments:
        p.deleted_at = datetime.now(timezone.utc)
        db.session.commit()
        flash(f'Praktyka {opis} została dezaktywowana i zostanie trwale usunięta po 7 dniach. Możesz ją przywrócić.', 'warning')
    else:
        db.session.delete(p)
        db.session.commit()
        flash(f'Praktyka {opis} została trwale usunięta (brak zapisanych studentów).', 'success')
    return redirect(url_for('zarzadzanie.lista_praktyk'))


@zarzadzanie_bp.route('/praktyki/<uuid:id>/przywroc', methods=['POST'])
@wymaga_roli(UserRole.ADMIN)
def przywroc_praktyke(id):
    p = db.session.get(Internship, id) or abort(404)
    opis = f'{p.academic_year} ({p.semester})'
    p.deleted_at = None
    db.session.commit()
    flash(f'Praktyka {opis} została przywrócona.', 'success')
    return redirect(url_for('zarzadzanie.lista_praktyk'))


