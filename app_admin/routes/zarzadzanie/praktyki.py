import uuid
import csv
import io
import datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError
from werkzeug.security import generate_password_hash

from core.modele import (Uzytkownik, Student, Praktyka, ZapisPraktyki, HarmonogramPraktyki, EfektUczenia,
                    RolaUzytkownika, StatusPraktyki, StatusZapisu, UploadedDocument, Firma)
from core.extensions import db
from core.uslugi import UslugaUzytkownikow as _UslugaUzytkownikow
_serwis_uzytkownikow = _UslugaUzytkownikow()
from core.auth import wymaga_roli

from . import zarzadzanie_bp
from .formularze import *

# ── Praktyki ──────────────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/praktyki')
@login_required
def lista_praktyk():
    strona = request.args.get('strona', 1, type=int)
    praktyki = db.session.query(Praktyka)\
                 .order_by(Praktyka.rok_uczelniany.desc(), Praktyka.semestr)\
                 .paginate(page=strona, per_page=25, error_out=False)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/praktyki.html', praktyki=praktyki, csrf_form=csrf_form)


@zarzadzanie_bp.route('/praktyki/nowa', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def nowa_praktyka():
    form = FormularzPraktyki()
    if form.validate_on_submit():
        rok = (form.rok_uczelniany.data or '').strip()
        try:
            wymiar = int(form.wymiar_godzin.data)
        except Exception:
            flash('Wymiar godzin musi być liczbą całkowitą.', 'danger')
            return render_template('zarzadzanie/formularz_praktyki.html', form=form)
        p = Praktyka(
            id             = uuid.uuid4(),
            rok_uczelniany = rok,
            semestr        = form.semestr.data,
            wymiar_godzin  = wymiar,
            status         = StatusPraktyki.INACTIVE,
        )
        db.session.add(p)
        db.session.commit()
        flash('Praktyka została utworzona.', 'success')
        return redirect(url_for('zarzadzanie.lista_praktyk'))
    return render_template('zarzadzanie/formularz_praktyki.html', form=form)


@zarzadzanie_bp.route('/praktyki/<uuid:id>/aktywnosc', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def przelacz_aktywnosc_praktyki(id):
    p = db.session.get(Praktyka, id) or abort(404)
    p.status = StatusPraktyki.INACTIVE if p.status == StatusPraktyki.ACTIVE else StatusPraktyki.ACTIVE
    db.session.commit()
    stan = 'aktywowana' if p.status == StatusPraktyki.ACTIVE else 'dezaktywowana'
    flash(f'Praktyka {p.rok_uczelniany} ({p.semestr}) została {stan}.', 'success')
    return redirect(url_for('zarzadzanie.lista_praktyk'))


# ── Zgłoszenia studentów ──────────────────────────────────────────────────────

class FormularzPrzypiszUOPZ(FlaskForm):
    uopz_id = SelectField('Opiekun uczelniany (UOPZ)', choices=[], validators=[Optional()])


@zarzadzanie_bp.route('/zgloszenia')
@wymaga_roli(RolaUzytkownika.ADMIN)
def lista_zgloszen():
    strona        = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()

    q = db.session.query(ZapisPraktyki).join(Uzytkownik, ZapisPraktyki.student_id == Uzytkownik.id)
    q = q.filter(ZapisPraktyki.track_type == 'STANDARD')

    if status_filter:
        try:
            q = q.filter(ZapisPraktyki.status == StatusZapisu[status_filter])
        except KeyError:
            flash(f'Nieznany status: {status_filter}', 'warning')

    zgloszenia = q.order_by(ZapisPraktyki.enrolled_at.desc()).paginate(page=strona, per_page=25, error_out=False)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/enrollments/list.html', zgloszenia=zgloszenia, csrf_form=csrf_form)


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/przypisz-uopz', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def przypisz_uopz(id):
    zapis     = db.session.get(ZapisPraktyki, id) or abort(404)
    form      = FormularzPrzypiszUOPZ()
    uopz_list = db.session.query(Uzytkownik).filter_by(rola=RolaUzytkownika.UOPZ, aktywny=True)\
                  .order_by(Uzytkownik.nazwisko, Uzytkownik.imie).all()
    form.uopz_id.choices = [('', '--- brak ---')] + [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]

    if form.validate_on_submit():
        if form.uopz_id.data:
            zapis.uopz_id = form.uopz_id.data
            zapis.status  = StatusZapisu.AWAITING_APPROVAL
            db.session.commit()
            flash('Opiekun UOPZ przypisany, zgłoszenie przekazane do zatwierdzenia.', 'success')
        else:
            flash('Nie wybrano opiekuna.', 'warning')
        return redirect(url_for('zarzadzanie.lista_zgloszen'))

    if request.method == 'GET':
        form.uopz_id.data = str(zapis.uopz_id) if zapis.uopz_id else ''

    return render_template('zarzadzanie/enrollments/przypisz_uopz.html', form=form, zapis=zapis)


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/szczegoly', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def szczegoly_zgloszenia(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)

    if current_user.role == RolaUzytkownika.UOPZ and zapis.uopz_id != current_user.id:
        abort(403)

    harmonogram      = db.session.query(HarmonogramPraktyki).filter_by(enrollment_id=id).all()
    harmonogram_dict = {h.learning_outcome_id: h for h in harmonogram}
    efekty           = db.session.query(EfektUczenia).order_by(EfektUczenia.id).all()

    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SubmitField

    class FormularzKomentarza(FlaskForm):
        komentarz = TextAreaField('Komentarz do studenta')
        zatwierdz = SubmitField('Zatwierdź zgłoszenie')
        odrzuc    = SubmitField('Wymagane poprawki')

    form = FormularzKomentarza()

    if form.validate_on_submit():
        if current_user.role == RolaUzytkownika.ADMIN:
            zapis.komentarze_admina = form.komentarz.data
        else:
            zapis.komentarze_uopz = form.komentarz.data

        if form.zatwierdz.data:
            zapis.status = StatusZapisu.IN_PROGRESS
            flash('Zgłoszenie zostało zatwierdzone!', 'success')
        elif form.odrzuc.data:
            zapis.status                 = StatusZapisu.PENDING
            zapis.powiadomiono_studenta_o = db.func.now()
            flash('Wysłano prośbę o poprawki do studenta.', 'info')

        db.session.commit()
        return redirect(url_for('zarzadzanie.lista_zgloszen') if current_user.role == RolaUzytkownika.ADMIN
                        else url_for('zarzadzanie.moje_zgloszenia'))

    uploaded_docs = db.session.query(UploadedDocument)\
        .filter_by(enrollment_id=id)\
        .order_by(UploadedDocument.uploaded_at.desc())\
        .all()

    return render_template('zarzadzanie/enrollments/szczegoly.html',
                           zapis=zapis, harmonogram_dict=harmonogram_dict,
                           efekty=efekty, form=form, uploaded_docs=uploaded_docs)


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/zatwierdz-zaklad', methods=['POST'])
@wymaga_roli(RolaUzytkownika.UOPZ, RolaUzytkownika.ADMIN)
def zatwierdz_zaklad(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    if zapis.zaklad:
        try:
            zapis.zaklad.zatwierdzone = True
        except Exception:
            pass
    zapis.status = StatusZapisu.IN_PROGRESS
    db.session.commit()
    flash('Zakład zatwierdzony. Praktyka rozpoczęła się.', 'success')
    return redirect(url_for('zarzadzanie.lista_zgloszen'))


@zarzadzanie_bp.route('/zgloszenia/<uuid:id>/potwierdz', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def potwierdz_zapis(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    zapis.status = StatusZapisu.IN_PROGRESS
    if current_user.role == RolaUzytkownika.UOPZ:
        zapis.uopz_id = current_user.id
    db.session.commit()
    flash('Zapis studenta na praktykę został potwierdzony. Zostałeś/aś przypisany/a jako opiekun.', 'success')
    return redirect(request.referrer or url_for('dashboard.index'))


@zarzadzanie_bp.route('/moje-zgloszenia')
@wymaga_roli(RolaUzytkownika.UOPZ)
def moje_zgloszenia():
    """Lista zgłoszeń przypisanych do aktualnego UOPZ"""
    from app_admin.routes.ocenianie import get_pilne_oceny

    strona        = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()

    q = db.session.query(ZapisPraktyki).filter(ZapisPraktyki.uopz_id == current_user.id)

    if status_filter:
        try:
            q = q.filter(ZapisPraktyki.status == StatusZapisu[status_filter])
        except KeyError:
            flash(f'Nieznany status: {status_filter}', 'warning')

    base_query = db.session.query(ZapisPraktyki).filter(ZapisPraktyki.uopz_id == current_user.id)
    liczniki = {
        'wszystkie':   base_query.count(),
        'oczekujace':  base_query.filter(ZapisPraktyki.status == StatusZapisu.AWAITING_APPROVAL).count(),
        'zatwierdzone': base_query.filter(ZapisPraktyki.status == StatusZapisu.IN_PROGRESS).count(),
    }

    pilne_oceny = get_pilne_oceny(current_user.id)
    zgloszenia  = q.order_by(ZapisPraktyki.enrolled_at.desc()).paginate(page=strona, per_page=25, error_out=False)
    csrf_form   = FlaskForm()
    return render_template('zarzadzanie/enrollments/moje_lista.html',
                           zgloszenia=zgloszenia, liczniki=liczniki,
                           pilne_oceny=pilne_oceny, csrf_form=csrf_form)


@zarzadzanie_bp.route('/praktyki/<uuid:id>/usun', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def usun_praktyke(id):
    p   = db.session.get(Praktyka, id) or abort(404)
    opis = f'{p.rok_uczelniany} ({p.semestr})'
    from sqlalchemy import text as _text
    db.session.execute(_text("""
        DELETE FROM uploaded_documents
        WHERE enrollment_id IN (
            SELECT id FROM internship_enrollments WHERE internship_id = :pid
        )
    """), {'pid': str(id)})
    db.session.delete(p)
    db.session.commit()
    flash(f'Praktyka {opis} została usunięta.', 'success')
    return redirect(url_for('zarzadzanie.lista_praktyk'))


