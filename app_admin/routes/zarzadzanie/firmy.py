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
from core.autoryzacja import wymaga_roli

from . import zarzadzanie_bp
from .formularze import *

# ── Zakłady ───────────────────────────────────────────────────────────────────

class _EmptyPagination:
    def __init__(self):
        self.items = []
        self.page  = 1
        self.pages = 1
    def iter_pages(self):
        return [1]


@zarzadzanie_bp.route('/zaklady')
@login_required
def lista_zakladow():
    zaklady   = _EmptyPagination()
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/zaklady.html', zaklady=zaklady, csrf_form=csrf_form)


@zarzadzanie_bp.route('/zaklady/nowy', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def nowy_zaklad():
    flash('Funkcja dodawania zakładu jeszcze niezaimplementowana.', 'warning')
    return redirect(url_for('zarzadzanie.lista_zakladow'))


@zarzadzanie_bp.route('/zaklady/<uuid:id>/edytuj', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def edytuj_zaklad(id):
    flash('Edycja zakładu jeszcze niezaimplementowana.', 'warning')
    return redirect(url_for('zarzadzanie.lista_zakladow'))


# ── Firmy ─────────────────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/firmy')
@wymaga_roli(RolaUzytkownika.ADMIN)
def lista_firm():
    strona = request.args.get('page', 1, type=int)
    szukaj = request.args.get('szukaj', '').strip()
    status = request.args.get('status', 'wszystkie')

    q = db.session.query(Firma)
    if status == 'aktywne':
        q = q.filter_by(is_active=True)
    elif status == 'nieaktywne':
        q = q.filter_by(is_active=False)

    if szukaj:
        q = q.filter(db.or_(
            Firma.name.ilike(f'%{szukaj}%'),
            Firma.address.ilike(f'%{szukaj}%'),
            Firma.city.ilike(f'%{szukaj}%'),
            Firma.tax_id.ilike(f'%{szukaj}%'),
        ))

    firmy     = q.order_by(Firma.name).paginate(page=strona, per_page=25, error_out=False)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/firmy/lista.html', firmy=firmy, csrf_form=csrf_form)


@zarzadzanie_bp.route('/firmy/dodaj', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def dodaj_firme():
    form = FormularzFirmy()
    if form.validate_on_submit():
        istniejaca = db.session.query(Firma).filter_by(name=form.nazwa.data.strip(), is_active=True).first()
        if istniejaca:
            flash('Firma o tej nazwie już istnieje w systemie.', 'error')
            return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='dodaj')

        if form.nip_krs.data and form.nip_krs.data.strip():
            istniejaca_nip = db.session.query(Firma).filter_by(tax_id=form.nip_krs.data.strip(), is_active=True).first()
            if istniejaca_nip:
                flash(f'Firma z numerem NIP/KRS "{form.nip_krs.data.strip()}" już istnieje ({istniejaca_nip.name}).', 'error')
                return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='dodaj')

        firma = Firma(
            id      = uuid.uuid4(),
            name    = form.nazwa.data.strip(),
            address = form.adres.data.strip()   if form.adres.data   else None,
            city    = form.miasto.data.strip()  if form.miasto.data  else None,
            tax_id  = form.nip_krs.data.strip() if form.nip_krs.data else None,
        )
        db.session.add(firma)
        db.session.commit()
        flash('Firma została dodana do systemu.', 'success')
        return redirect(url_for('zarzadzanie.lista_firm'))

    return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='dodaj')


@zarzadzanie_bp.route('/firmy/<uuid:id>/edytuj', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def edytuj_firme(id):
    firma = db.session.get(Firma, id) or abort(404)
    form  = FormularzFirmy(obj=firma)

    if form.validate_on_submit():
        istniejaca = db.session.query(Firma)\
            .filter(Firma.name == form.nazwa.data.strip(), Firma.id != firma.id, Firma.is_active == True).first()
        if istniejaca:
            flash('Firma o tej nazwie już istnieje w systemie.', 'error')
            return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='edytuj', firma=firma)

        if form.nip_krs.data and form.nip_krs.data.strip():
            istniejaca_nip = db.session.query(Firma)\
                .filter(Firma.tax_id == form.nip_krs.data.strip(), Firma.id != firma.id, Firma.is_active == True).first()
            if istniejaca_nip:
                flash(f'Firma z NIP/KRS "{form.nip_krs.data.strip()}" już istnieje ({istniejaca_nip.name}).', 'error')
                return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='edytuj', firma=firma)

        firma.name    = form.nazwa.data.strip()
        firma.address = form.adres.data.strip()   if form.adres.data   else None
        firma.city    = form.miasto.data.strip()  if form.miasto.data  else None
        firma.tax_id  = form.nip_krs.data.strip() if form.nip_krs.data else None
        db.session.commit()
        flash('Dane firmy zostały zaktualizowane.', 'success')
        return redirect(url_for('zarzadzanie.lista_firm'))

    return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='edytuj', firma=firma)


@zarzadzanie_bp.route('/firmy/<uuid:id>/usun', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def usun_firme(id):
    firma             = db.session.get(Firma, id) or abort(404)
    wszystkie_praktyki = db.session.query(ZapisPraktyki).filter_by(company_id=firma.id).count()
    if wszystkie_praktyki > 0:
        flash(f'Nie można usunąć firmy - ma {wszystkie_praktyki} praktyk w historii.', 'error')
        return redirect(url_for('zarzadzanie.lista_firm'))
    nazwa_firmy = firma.name
    db.session.delete(firma)
    db.session.commit()
    flash(f'Firma "{nazwa_firmy}" została trwale usunięta z systemu.', 'success')
    return redirect(url_for('zarzadzanie.lista_firm'))


@zarzadzanie_bp.route('/firmy/<uuid:id>/przelacz-aktywnosc', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def przelacz_aktywnosc_firmy(id):
    firma = db.session.get(Firma, id) or abort(404)

    if firma.is_active:
        aktywne_praktyki = db.session.query(ZapisPraktyki)\
            .filter_by(company_id=firma.id)\
            .filter(ZapisPraktyki.status.in_([
                StatusZapisu.AWAITING_APPROVAL, StatusZapisu.IN_PROGRESS,
                StatusZapisu.COMMISSION_REVIEW, StatusZapisu.DEAN_APPROVAL,
            ])).count()
        if aktywne_praktyki > 0:
            flash(f'Nie można dezaktywować firmy - ma {aktywne_praktyki} aktywnych praktyk.', 'error')
            return redirect(url_for('zarzadzanie.lista_firm'))
        firma.is_active = False
        flash('Firma została dezaktywowana.', 'success')
    else:
        firma.is_active = True
        flash('Firma została aktywowana.', 'success')

    db.session.commit()
    return redirect(url_for('zarzadzanie.lista_firm'))
