import uuid

from flask import abort, flash, redirect, render_template, request, url_for
from flask_wtf import FlaskForm

from core.auth import roles_required
from core.extensions import db
from core.models import Company, EnrollmentStatus, UserRole
from core.presenters import active_toggle
from core.repositories import CompanyRepository

from . import zarzadzanie_bp
from .forms import CompanyForm

company_repository = CompanyRepository()

COMPANY_LIST_ROUTE = 'zarzadzanie.lista_firm'
COMPANY_FORM_TEMPLATE = 'zarzadzanie/firmy/formularz.html'

ACTIVE_ENROLLMENT_STATUSES = [
    EnrollmentStatus.AWAITING_APPROVAL,
    EnrollmentStatus.IN_PROGRESS,
    EnrollmentStatus.COMMISSION_REVIEW,
    EnrollmentStatus.DIRECTOR_APPROVAL,
]


def _check_company_uniqueness(form, exclude_id=None) -> str | None:
    company_name = form.name.data.strip()
    if company_repository.find_active_by_name(company_name, exclude_id=exclude_id):
        return 'Firma o tej nazwie już istnieje w systemie.'

    tax_id = form.vat_number.data.strip() if form.vat_number.data else ''
    if tax_id:
        existing_company = company_repository.find_active_by_tax_id(tax_id, exclude_id=exclude_id)
        if existing_company:
            return f'Firma z NIP/KRS "{tax_id}" już istnieje ({existing_company.name}).'
    return None


@zarzadzanie_bp.route('/firmy', methods=['GET'])
@roles_required(UserRole.ADMIN)
def lista_firm():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('szukaj', '').strip()
    status = request.args.get('status', 'wszystkie')

    companies = company_repository.paginated_list(search=search_query, status=status, page=page)
    wiersze = [
        {'company': c, 'aktywnosc': active_toggle(c.is_active, feminine=True)}
        for c in companies.items
    ]
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/firmy/lista.html', firmy=companies,
                           wiersze=wiersze, csrf_form=csrf_form)


@zarzadzanie_bp.route('/firmy/dodaj', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN)
def dodaj_firme():
    form = CompanyForm()
    if form.validate_on_submit():
        error_message = _check_company_uniqueness(form)
        if error_message:
            flash(error_message, 'error')
            return render_template(COMPANY_FORM_TEMPLATE, form=form, tryb='dodaj')

        company = Company(
            id=uuid.uuid4(),
            name=form.name.data.strip(),
            address=form.address.data.strip() if form.address.data else None,
            city=form.city.data.strip() if form.city.data else None,
            tax_id=form.vat_number.data.strip() if form.vat_number.data else None,
        )
        company_repository.save(company)
        db.session.commit()
        flash('Firma została dodana do systemu.', 'success')
        return redirect(url_for(COMPANY_LIST_ROUTE))

    return render_template(COMPANY_FORM_TEMPLATE, form=form, tryb='dodaj')


@zarzadzanie_bp.route('/firmy/<uuid:id>/edytuj', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN)
def edytuj_firme(id):
    company = company_repository.find_by_id(id) or abort(404)
    form = CompanyForm(obj=company)

    if form.validate_on_submit():
        error_message = _check_company_uniqueness(form, exclude_id=company.id)
        if error_message:
            flash(error_message, 'error')
            return render_template(COMPANY_FORM_TEMPLATE, form=form, tryb='edytuj', company=company)

        company.name = form.name.data.strip()
        company.address = form.address.data.strip() if form.address.data else None
        company.city = form.city.data.strip() if form.city.data else None
        company.tax_id = form.vat_number.data.strip() if form.vat_number.data else None
        db.session.commit()
        flash('Dane firmy zostały zaktualizowane.', 'success')
        return redirect(url_for(COMPANY_LIST_ROUTE))

    return render_template(COMPANY_FORM_TEMPLATE, form=form, tryb='edytuj', company=company)


@zarzadzanie_bp.route('/firmy/<uuid:id>/usun', methods=['POST'])
@roles_required(UserRole.ADMIN)
def usun_firme(id):
    company = company_repository.find_by_id(id) or abort(404)
    internship_count = company_repository.count_internships(company.id)
    if internship_count > 0:
        flash(f'Nie można usunąć firmy - ma {internship_count} praktyk w historii.', 'error')
        return redirect(url_for(COMPANY_LIST_ROUTE))

    company_name = company.name
    company_repository.delete(company)
    db.session.commit()
    flash(f'Firma "{company_name}" została trwale usunięta z systemu.', 'success')
    return redirect(url_for(COMPANY_LIST_ROUTE))


@zarzadzanie_bp.route('/firmy/<uuid:id>/przelacz-aktywnosc', methods=['POST'])
@roles_required(UserRole.ADMIN)
def przelacz_aktywnosc_firmy(id):
    company = company_repository.find_by_id(id) or abort(404)

    if company.is_active:
        active_internships = company_repository.count_active_internships(
            company.id,
            ACTIVE_ENROLLMENT_STATUSES,
        )
        if active_internships > 0:
            flash(f'Nie można dezaktywować firmy - ma {active_internships} aktywnych praktyk.', 'error')
            return redirect(url_for(COMPANY_LIST_ROUTE))
        company.is_active = False
        flash('Firma została dezaktywowana.', 'success')
    else:
        company.is_active = True
        flash('Firma została aktywowana.', 'success')

    db.session.commit()
    return redirect(url_for(COMPANY_LIST_ROUTE))
