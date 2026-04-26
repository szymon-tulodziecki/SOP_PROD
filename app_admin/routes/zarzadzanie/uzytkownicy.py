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

from core.modele import (User, Student, Internship, InternshipEnrollment, InternshipSchedule, LearningOutcome,
                    UserRole, InternshipStatus, EnrollmentStatus, UploadedDocument, Company)
from core.extensions import db
from core.uslugi import UslugaUzytkownikow as _UslugaUzytkownikow
_serwis_uzytkownikow = _UslugaUzytkownikow()
from core.autoryzacja import wymaga_roli
from core.repozytoria import RepozytoriumUzytkownikow

_repo_uzytk = RepozytoriumUzytkownikow()

from . import zarzadzanie_bp
from .formularze import (StudentForm, StudentEditForm, StaffForm,
                          CsvImportForm, CompanyForm, InternshipForm)

# ── Użytkownicy ───────────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/uzytkownicy')
@login_required
def lista_uzytkownikow():
    page        = request.args.get('strona', 1, type=int)
    search_query = request.args.get('szukaj', '').strip()
    role_filter  = request.args.get('rola', '').strip()

    users     = _repo_uzytk.szukaj_strona(szukaj=search_query, filtr_rola=role_filter, strona=page)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/uzytkownicy.html',
                           uzytkownicy=users,
                           csrf_form=csrf_form)


@zarzadzanie_bp.route('/uzytkownicy/nowy-student', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def nowy_student():
    form      = StudentForm()
    uopz_list = _repo_uzytk.aktywni_uopz()
    form.uopz_id.choices = [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]
    if form.validate_on_submit():
        u = _serwis_uzytkownikow.utworz_studenta(
            email          = form.email.data.lower().strip(),
            haslo          = '',
            imie           = form.first_name.data,
            nazwisko       = form.last_name.data,
            numer_albumu   = form.album_number.data,
            gender         = form.gender.data          or None,
            field_of_study = form.field_of_study.data  or None,
            specialization = form.specialization.data  or None,
            study_mode     = form.study_mode.data      or None,
            supervisor_id  = form.uopz_id.data         or None,
            require_password_change=False,
        )
        flash(
            f'Konto studenta {u.imie} {u.nazwisko} (nr alb. {u.numer_albumu}) '
            f'zostało utworzone. Student może się teraz zalogować przez Microsoft ({u.email}).',
            'success'
        )
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    return render_template('zarzadzanie/formularz_studenta.html', form=form, uzytkownik=None)


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/edytuj-student', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def edytuj_studenta(id):
    u    = db.session.get(User, id) or abort(404)
    form = StudentEditForm(user_id=id, obj=u)
    uopz_list = _repo_uzytk.aktywni_uopz()
    form.uopz_id.choices = [(str(x.id), f"{x.first_name} {x.last_name}") for x in uopz_list]

    if request.method == 'GET':
        form.first_name.data   = u.first_name
        form.last_name.data    = u.last_name
        form.email.data        = u.email
        form.album_number.data = u.album_number

    if form.validate_on_submit():
        u.first_name     = form.first_name.data.strip()
        u.last_name      = form.last_name.data.strip()
        u.email          = form.email.data.lower().strip()
        u.album_number   = form.album_number.data.strip()
        u.gender         = form.gender.data         or None
        u.field_of_study = form.field_of_study.data or None
        u.specialization = form.specialization.data or None
        u.study_mode     = form.study_mode.data     or None
        db.session.commit()
        flash('Dane studenta zostały zaktualizowane.', 'success')
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    return render_template('zarzadzanie/formularz_studenta.html', form=form, uzytkownik=u)


@zarzadzanie_bp.route('/uzytkownicy/nowy-pracownik', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def nowy_pracownik():
    form = StaffForm()
    if form.validate_on_submit():
        u = User(
            id                      = uuid.uuid4(),
            first_name              = form.first_name.data.strip(),
            last_name               = form.last_name.data.strip(),
            email                   = form.email.data.lower().strip(),
            role                    = UserRole[form.role.data],
            password_hash           = '',
            require_password_change = False,
            is_active               = True,
        )
        db.session.add(u)
        db.session.commit()
        flash(
            f'Konto {u.first_name} {u.last_name} [{u.role.value}] utworzone. '
            f'Użytkownik może się zalogować przez Microsoft ({u.email}).',
            'success'
        )
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    return render_template('zarzadzanie/formularz_pracownika.html', form=form, uzytkownik=None)


@zarzadzanie_bp.route('/uzytkownicy/import-csv', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def import_csv():
    form      = CsvImportForm()
    uopz_list = _repo_uzytk.aktywni_uopz()
    form.uopz_id.choices = [('', '— wybierz —')] + [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]
    results = None

    if form.validate_on_submit():
        uopz_id = form.uopz_id.data or None
        content = form.file.data.read().decode('utf-8-sig')
        reader  = csv.DictReader(io.StringIO(content))

        created, skipped, errors = 0, 0, []

        csv_rows = []
        for row_number, row in enumerate(reader, start=2):
            first_name    = (row.get('imie')         or row.get('Imię')        or '').strip()
            last_name     = (row.get('nazwisko')      or row.get('Nazwisko')    or '').strip()
            email         = (row.get('email')         or row.get('Email')       or '').strip().lower()
            album_number  = (row.get('numer_albumu')  or row.get('Nr albumu')   or '').strip()
            gender        = (row.get('plec')          or row.get('Płeć')        or '').strip().upper() or None
            field_of_study = (row.get('kierunek')     or row.get('Kierunek')    or '').strip() or None
            specialization = (row.get('specjalnosc')  or row.get('Specjalność') or '').strip() or None
            study_mode    = (row.get('tryb_studiow')  or row.get('Tryb')        or '').strip().lower() or None

            if not all([first_name, last_name, email, album_number, gender, field_of_study, study_mode]):
                errors.append(f'Wiersz {row_number}: brakujące dane (wymagane: imie, nazwisko, email, numer_albumu, plec, kierunek, tryb_studiow)')
                skipped += 1
                continue

            csv_rows.append({
                'row_number': row_number,
                'first_name': first_name, 'last_name': last_name,
                'email': email, 'album_number': album_number, 'gender': gender,
                'field_of_study': field_of_study, 'specialization': specialization,
                'study_mode': study_mode,
            })

        if csv_rows:
            all_emails = [r['email'] for r in csv_rows]
            all_albums = [r['album_number'] for r in csv_rows]

            existing = _repo_uzytk.znajdz_istniejace_po_email_lub_albumie(
                all_emails, all_albums
            )

            existing_emails = {row.email for row in existing}
            existing_albums = {row.album_number for row in existing if row.album_number}

            for r in csv_rows:
                if r['email'] in existing_emails or r['album_number'] in existing_albums:
                    errors.append(f"Wiersz {r['row_number']}: {r['email']} lub nr {r['album_number']} już istnieje")
                    skipped += 1
                    continue
                try:
                    _serwis_uzytkownikow.utworz_studenta(
                        email                   = r['email'].lower().strip(),
                        haslo                   = '',
                        imie                    = r['first_name'],
                        nazwisko                = r['last_name'],
                        numer_albumu            = r['album_number'],
                        gender                  = r['gender'],
                        field_of_study          = r['field_of_study'],
                        specialization          = r['specialization'],
                        study_mode              = r['study_mode'],
                        supervisor_id           = uuid.UUID(uopz_id) if uopz_id else None,
                        require_password_change = False,
                        commit                  = False,
                    )
                    existing_emails.add(r['email'])
                    existing_albums.add(r['album_number'])
                    created += 1
                except Exception as e:
                    errors.append(f"Wiersz {r['row_number']}: {str(e)}")
                    skipped += 1

            db.session.commit()

        results = {'created': created, 'skipped': skipped, 'errors': errors}
        if created:
            flash(f'Import zakończony: {created} kont utworzonych.', 'success')

    return render_template('zarzadzanie/import_csv.html', form=form, results=results)


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/aktywnosc', methods=['POST'])
@wymaga_roli(UserRole.ADMIN)
def przelacz_aktywnosc(id):
    u = db.session.get(User, id) or abort(404)
    if str(u.id) == str(current_user.id):
        flash('Nie możesz dezaktywować własnego konta.', 'danger')
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    u.is_active = not u.is_active
    db.session.commit()
    status_label = 'aktywowane' if u.is_active else 'dezaktywowane'
    flash(f'Konto {u.first_name} {u.last_name} zostało {status_label}.', 'success')
    return redirect(url_for('zarzadzanie.lista_uzytkownikow'))


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/usun', methods=['POST'])
@wymaga_roli(UserRole.ADMIN)
def usun_uzytkownika(id):
    u = db.session.get(User, id) or abort(404)
    if str(u.id) == str(current_user.id):
        flash('Nie możesz usunąć własnego konta.', 'danger')
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    full_name = f'{u.first_name} {u.last_name}'
    db.session.delete(u)
    db.session.commit()
    flash(f'Konto {full_name} zostało trwale usunięte.', 'success')
    return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
