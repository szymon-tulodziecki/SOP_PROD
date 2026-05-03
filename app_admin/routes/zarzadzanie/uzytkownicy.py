import uuid

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm

from core.autoryzacja import roles_required
from core.extensions import db, limiter
from core.modele import User, UserRole
from core.repozytoria import UserRepository
from core.uslugi import UserService

from . import zarzadzanie_bp
from .formularze import CsvImportForm, StaffForm, StudentEditForm, StudentForm

user_service = UserService()
user_repository = UserRepository()

USER_LIST_ENDPOINT = 'zarzadzanie.lista_uzytkownikow'


@zarzadzanie_bp.route('/uzytkownicy', methods=['GET'])
@login_required
def lista_uzytkownikow():
    page = request.args.get('strona', 1, type=int)
    search_query = request.args.get('szukaj', '').strip()
    role_filter = request.args.get('rola', '').strip()

    users = user_repository.search_page(search=search_query, role_filter=role_filter, page=page)
    csrf_form = FlaskForm()
    return render_template(
        'zarzadzanie/uzytkownicy.html',
        uzytkownicy=users,
        csrf_form=csrf_form,
    )


@zarzadzanie_bp.route('/uzytkownicy/nowy-student', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN)
def nowy_student():
    form = StudentForm()
    supervisors = user_repository.active_uopz()
    form.uopz_id.choices = [(str(user.id), f"{user.first_name} {user.last_name}") for user in supervisors]

    if form.validate_on_submit():
        student = user_service.create_student(
            email=form.email.data.lower().strip(),
            password='',
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            album_number=form.album_number.data,
            gender=form.gender.data or None,
            field_of_study=form.field_of_study.data or None,
            specialization=form.specialization.data or None,
            study_mode=form.study_mode.data or None,
            supervisor_id=form.uopz_id.data or None,
            require_password_change=False,
        )
        flash(
            f'Konto studenta {student.first_name} {student.last_name} (nr alb. {student.album_number}) '
            f'zostało utworzone. Student może się teraz zalogować przez Microsoft ({student.email}).',
            'success',
        )
        return redirect(url_for(USER_LIST_ENDPOINT))

    return render_template('zarzadzanie/formularz_studenta.html', form=form, uzytkownik=None)


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/edytuj-student', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN)
def edytuj_studenta(id):
    student = user_repository.find_by_id(id) or abort(404)
    form = StudentEditForm(user_id=id, obj=student)
    supervisors = user_repository.active_uopz()
    form.uopz_id.choices = [(str(user.id), f"{user.first_name} {user.last_name}") for user in supervisors]

    if request.method == 'GET':
        form.first_name.data = student.first_name
        form.last_name.data = student.last_name
        form.email.data = student.email
        form.album_number.data = student.album_number

    if form.validate_on_submit():
        student.first_name = form.first_name.data.strip()
        student.last_name = form.last_name.data.strip()
        student.email = form.email.data.lower().strip()
        student.album_number = form.album_number.data.strip()
        student.gender = form.gender.data or None
        student.field_of_study = form.field_of_study.data or None
        student.specialization = form.specialization.data or None
        student.study_mode = form.study_mode.data or None
        db.session.commit()
        flash('Dane studenta zostały zaktualizowane.', 'success')
        return redirect(url_for(USER_LIST_ENDPOINT))

    return render_template('zarzadzanie/formularz_studenta.html', form=form, uzytkownik=student)


@zarzadzanie_bp.route('/uzytkownicy/nowy-pracownik', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN)
def nowy_pracownik():
    form = StaffForm()

    if form.validate_on_submit():
        user = User(
            id=uuid.uuid4(),
            first_name=form.first_name.data.strip(),
            last_name=form.last_name.data.strip(),
            email=form.email.data.lower().strip(),
            role=UserRole[form.role.data],
            password_hash='',
            require_password_change=False,
            is_active=True,
        )
        user_repository.save(user)
        db.session.commit()
        flash(
            f'Konto {user.first_name} {user.last_name} [{user.role.value}] utworzone. '
            f'Użytkownik może się zalogować przez Microsoft ({user.email}).',
            'success',
        )
        return redirect(url_for(USER_LIST_ENDPOINT))

    return render_template('zarzadzanie/formularz_pracownika.html', form=form, uzytkownik=None)


@zarzadzanie_bp.route('/uzytkownicy/import-csv', methods=['GET', 'POST'])
@roles_required(UserRole.ADMIN)
@limiter.limit("10 per hour", methods=['POST'])
def import_csv():
    form = CsvImportForm()
    supervisors = user_repository.active_uopz()
    form.uopz_id.choices = [('', '— wybierz —')] + [
        (str(user.id), f"{user.first_name} {user.last_name}") for user in supervisors
    ]
    results = None

    if form.validate_on_submit():
        content = form.file.data.read().decode('utf-8-sig')
        supervisor_id = form.uopz_id.data or None
        results = user_service.import_from_csv(content, supervisor_id)
        if results['created']:
            flash(f'Import zakończony: {results["created"]} kont utworzonych.', 'success')

    return render_template('zarzadzanie/import_csv.html', form=form, results=results)


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/aktywnosc', methods=['POST'])
@roles_required(UserRole.ADMIN)
def przelacz_aktywnosc(id):
    user = user_repository.find_by_id(id) or abort(404)
    if str(user.id) == str(current_user.id):
        flash('Nie możesz dezaktywować własnego konta.', 'danger')
        return redirect(url_for(USER_LIST_ENDPOINT))

    user.is_active = not user.is_active
    db.session.commit()
    status_label = 'aktywowane' if user.is_active else 'dezaktywowane'
    flash(f'Konto {user.first_name} {user.last_name} zostało {status_label}.', 'success')
    return redirect(url_for(USER_LIST_ENDPOINT))


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/usun', methods=['POST'])
@roles_required(UserRole.ADMIN)
@limiter.limit("30 per hour")
def usun_uzytkownika(id):
    user = user_repository.find_by_id(id) or abort(404)
    if str(user.id) == str(current_user.id):
        flash('Nie możesz usunąć własnego konta.', 'danger')
        return redirect(url_for(USER_LIST_ENDPOINT))

    full_name = f'{user.first_name} {user.last_name}'
    user_repository.delete(user)
    db.session.commit()
    flash(f'Konto {full_name} zostało trwale usunięte.', 'success')
    return redirect(url_for(USER_LIST_ENDPOINT))
