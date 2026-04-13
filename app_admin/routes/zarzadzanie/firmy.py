import uuid
from flask import (Blueprint, render_template, redirect, url_for, flash, request, abort)
from flask_login import login_required
from flask_wtf import FlaskForm

from core.modele import Company, EnrollmentStatus, UserRole
from core.extensions import db
from core.autoryzacja import wymaga_roli
from core.repozytoria import RepozytoriumFirm

from . import zarzadzanie_bp
from .formularze import FormularzFirmy

_repo_firm = RepozytoriumFirm()

_AKTYWNE_STATUSY = [
    EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.IN_PROGRESS,
    EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.DEAN_APPROVAL,
]


@zarzadzanie_bp.route('/firmy')
@wymaga_roli(UserRole.ADMIN)
def lista_firm():
    strona = request.args.get('page', 1, type=int)
    szukaj = request.args.get('szukaj', '').strip()
    status = request.args.get('status', 'wszystkie')

    firmy     = _repo_firm.lista_strona(szukaj=szukaj, status=status, strona=strona)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/firmy/lista.html', firmy=firmy, csrf_form=csrf_form)


@zarzadzanie_bp.route('/firmy/dodaj', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def dodaj_firme():
    form = FormularzFirmy()
    if form.validate_on_submit():
        if _repo_firm.znajdz_po_nazwie_aktywna(form.nazwa.data.strip()):
            flash('Firma o tej nazwie już istnieje w systemie.', 'error')
            return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='dodaj')

        if form.nip_krs.data and form.nip_krs.data.strip():
            istniejaca_nip = _repo_firm.znajdz_po_nip_aktywna(form.nip_krs.data.strip())
            if istniejaca_nip:
                flash(f'Firma z numerem NIP/KRS "{form.nip_krs.data.strip()}" już istnieje ({istniejaca_nip.name}).', 'error')
                return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='dodaj')

        firma = Company(
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
@wymaga_roli(UserRole.ADMIN)
def edytuj_firme(id):
    firma = _repo_firm.znajdz_po_id(id) or abort(404)
    form  = FormularzFirmy(obj=firma)

    if form.validate_on_submit():
        if _repo_firm.znajdz_po_nazwie_aktywna(form.nazwa.data.strip(), pominij_id=firma.id):
            flash('Firma o tej nazwie już istnieje w systemie.', 'error')
            return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='edytuj', firma=firma)

        if form.nip_krs.data and form.nip_krs.data.strip():
            istniejaca_nip = _repo_firm.znajdz_po_nip_aktywna(form.nip_krs.data.strip(), pominij_id=firma.id)
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
@wymaga_roli(UserRole.ADMIN)
def usun_firme(id):
    firma             = _repo_firm.znajdz_po_id(id) or abort(404)
    wszystkie_praktyki = _repo_firm.liczba_praktyk(firma.id)
    if wszystkie_praktyki > 0:
        flash(f'Nie można usunąć firmy - ma {wszystkie_praktyki} praktyk w historii.', 'error')
        return redirect(url_for('zarzadzanie.lista_firm'))
    nazwa_firmy = firma.name
    _repo_firm.usun(firma)
    db.session.commit()
    flash(f'Firma "{nazwa_firmy}" została trwale usunięta z systemu.', 'success')
    return redirect(url_for('zarzadzanie.lista_firm'))


@zarzadzanie_bp.route('/firmy/<uuid:id>/przelacz-aktywnosc', methods=['POST'])
@wymaga_roli(UserRole.ADMIN)
def przelacz_aktywnosc_firmy(id):
    firma = _repo_firm.znajdz_po_id(id) or abort(404)

    if firma.is_active:
        aktywne_praktyki = _repo_firm.liczba_aktywnych_praktyk(firma.id, _AKTYWNE_STATUSY)
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
