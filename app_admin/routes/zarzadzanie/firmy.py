import uuid
from flask import (Blueprint, render_template, redirect, url_for, flash, request, abort)
from flask_login import login_required
from flask_wtf import FlaskForm

from core.modele import Company, EnrollmentStatus, UserRole
from core.extensions import db
from core.autoryzacja import wymaga_roli
from core.repozytoria import RepozytoriumFirm

from . import zarzadzanie_bp
from .formularze import CompanyForm

_repo_firm = RepozytoriumFirm()

_AKTYWNE_STATUSY = [
    EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.IN_PROGRESS,
    EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.DIRECTOR_APPROVAL,
]


@zarzadzanie_bp.route('/firmy')
@wymaga_roli(UserRole.ADMIN)
def lista_firm():
    page         = request.args.get('page', 1, type=int)
    search_query = request.args.get('szukaj', '').strip()
    status = request.args.get('status', 'wszystkie')

    companies = _repo_firm.lista_strona(szukaj=search_query, status=status, strona=page)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/firmy/lista.html', firmy=companies, csrf_form=csrf_form)


@zarzadzanie_bp.route('/firmy/dodaj', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def dodaj_firme():
    form = CompanyForm()
    if form.validate_on_submit():
        if _repo_firm.znajdz_po_nazwie_aktywna(form.name.data.strip()):
            flash('Firma o tej nazwie już istnieje w systemie.', 'error')
            return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='dodaj')

        if form.vat_number.data and form.vat_number.data.strip():
            existing_by_vat = _repo_firm.znajdz_po_nip_aktywna(form.vat_number.data.strip())
            if existing_by_vat:
                flash(f'Firma z numerem NIP/KRS "{form.vat_number.data.strip()}" już istnieje ({existing_by_vat.name}).', 'error')
                return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='dodaj')

        firma = Company(
            id      = uuid.uuid4(),
            name    = form.name.data.strip(),
            address = form.address.data.strip()    if form.address.data    else None,
            city    = form.city.data.strip()       if form.city.data       else None,
            tax_id  = form.vat_number.data.strip() if form.vat_number.data else None,
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
    form  = CompanyForm(obj=firma)

    if form.validate_on_submit():
        if _repo_firm.znajdz_po_nazwie_aktywna(form.name.data.strip(), pominij_id=firma.id):
            flash('Firma o tej nazwie już istnieje w systemie.', 'error')
            return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='edytuj', firma=firma)

        if form.vat_number.data and form.vat_number.data.strip():
            existing_by_vat = _repo_firm.znajdz_po_nip_aktywna(form.vat_number.data.strip(), pominij_id=firma.id)
            if existing_by_vat:
                flash(f'Firma z NIP/KRS "{form.vat_number.data.strip()}" już istnieje ({existing_by_vat.name}).', 'error')
                return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='edytuj', firma=firma)

        firma.name    = form.name.data.strip()
        firma.address = form.address.data.strip()    if form.address.data    else None
        firma.city    = form.city.data.strip()       if form.city.data       else None
        firma.tax_id  = form.vat_number.data.strip() if form.vat_number.data else None
        db.session.commit()
        flash('Dane firmy zostały zaktualizowane.', 'success')
        return redirect(url_for('zarzadzanie.lista_firm'))

    return render_template('zarzadzanie/firmy/formularz.html', form=form, tryb='edytuj', firma=firma)


@zarzadzanie_bp.route('/firmy/<uuid:id>/usun', methods=['POST'])
@wymaga_roli(UserRole.ADMIN)
def usun_firme(id):
    firma              = _repo_firm.znajdz_po_id(id) or abort(404)
    total_internships  = _repo_firm.liczba_praktyk(firma.id)
    if total_internships > 0:
        flash(f'Nie można usunąć firmy - ma {total_internships} praktyk w historii.', 'error')
        return redirect(url_for('zarzadzanie.lista_firm'))
    company_name = firma.name
    _repo_firm.usun(firma)
    db.session.commit()
    flash(f'Firma "{company_name}" została trwale usunięta z systemu.', 'success')
    return redirect(url_for('zarzadzanie.lista_firm'))


@zarzadzanie_bp.route('/firmy/<uuid:id>/przelacz-aktywnosc', methods=['POST'])
@wymaga_roli(UserRole.ADMIN)
def przelacz_aktywnosc_firmy(id):
    firma = _repo_firm.znajdz_po_id(id) or abort(404)

    if firma.is_active:
        active_internships = _repo_firm.liczba_aktywnych_praktyk(firma.id, _AKTYWNE_STATUSY)
        if active_internships > 0:
            flash(f'Nie można dezaktywować firmy - ma {active_internships} aktywnych praktyk.', 'error')
            return redirect(url_for('zarzadzanie.lista_firm'))
        firma.is_active = False
        flash('Firma została dezaktywowana.', 'success')
    else:
        firma.is_active = True
        flash('Firma została aktywowana.', 'success')

    db.session.commit()
    return redirect(url_for('zarzadzanie.lista_firm'))
