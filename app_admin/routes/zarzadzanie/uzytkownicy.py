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
from .formularze import *

# ── Użytkownicy ───────────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/uzytkownicy')
@login_required
def lista_uzytkownikow():
    strona     = request.args.get('strona', 1, type=int)
    szukaj     = request.args.get('szukaj', '').strip()
    filtr_rola = request.args.get('rola', '').strip()

    uzytkownicy = _repo_uzytk.szukaj_strona(szukaj=szukaj, filtr_rola=filtr_rola, strona=strona)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/uzytkownicy.html',
                           uzytkownicy=uzytkownicy,
                           csrf_form=csrf_form)


@zarzadzanie_bp.route('/uzytkownicy/nowy-student', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def nowy_student():
    form = FormularzStudenta()
    uopz_list = _repo_uzytk.aktywni_uopz()
    form.uopz_id.choices = [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]
    if form.validate_on_submit():
        u = _serwis_uzytkownikow.utworz_studenta(
            email          = form.email.data.lower().strip(),
            haslo          = '',
            imie           = form.imie.data,
            nazwisko       = form.nazwisko.data,
            numer_albumu   = form.numer_albumu.data,
            gender         = form.plec.data          or None,
            field_of_study = form.kierunek.data      or None,
            specialization = form.specjalnosc.data   or None,
            study_mode     = form.tryb_studiow.data  or None,
            supervisor_id  = form.uopz_id.data       or None,
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
    form = FormularzEdycjiStudenta(uzytkownik_id=id, obj=u)
    uopz_list = _repo_uzytk.aktywni_uopz()
    form.uopz_id.choices = [(str(x.id), f"{x.first_name} {x.last_name}") for x in uopz_list]

    if request.method == 'GET':
        form.imie.data         = u.first_name
        form.nazwisko.data     = u.last_name
        form.email.data        = u.email
        form.numer_albumu.data = u.album_number

    if form.validate_on_submit():
        u.first_name   = form.imie.data.strip()
        u.last_name    = form.nazwisko.data.strip()
        u.email        = form.email.data.lower().strip()
        u.album_number = form.numer_albumu.data.strip()
        u.gender         = form.plec.data or None
        u.field_of_study = form.kierunek.data or None
        u.specialization = form.specjalnosc.data or None
        u.study_mode     = form.tryb_studiow.data or None
        db.session.commit()
        flash('Dane studenta zostały zaktualizowane.', 'success')
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    return render_template('zarzadzanie/formularz_studenta.html', form=form, uzytkownik=u)




@zarzadzanie_bp.route('/uzytkownicy/nowy-pracownik', methods=['GET', 'POST'])
@wymaga_roli(UserRole.ADMIN)
def nowy_pracownik():
    form = FormularzPracownika()
    if form.validate_on_submit():
        u = User(
            id                      = uuid.uuid4(),
            first_name              = form.imie.data.strip(),
            last_name               = form.nazwisko.data.strip(),
            email                   = form.email.data.lower().strip(),
            role                    = UserRole[form.rola.data],
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
    form      = FormularzImportuCSV()
    uopz_list = _repo_uzytk.aktywni_uopz()
    form.uopz_id.choices = [('', '— wybierz —')] + [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]
    wyniki = None

    if form.validate_on_submit():
        uopz_id   = form.uopz_id.data or None
        plik      = form.plik.data
        zawartosc = plik.read().decode('utf-8-sig')
        czytnik   = csv.DictReader(io.StringIO(zawartosc))

        utworzono, pominieto, bledy = 0, 0, []

        wiersze_csv = []
        for nr_wiersza, wiersz in enumerate(czytnik, start=2):
            imie         = (wiersz.get('imie')         or wiersz.get('Imię')        or '').strip()
            nazwisko     = (wiersz.get('nazwisko')      or wiersz.get('Nazwisko')    or '').strip()
            email        = (wiersz.get('email')         or wiersz.get('Email')       or '').strip().lower()
            nr_albumu    = (wiersz.get('numer_albumu')  or wiersz.get('Nr albumu')   or '').strip()
            plec         = (wiersz.get('plec')          or wiersz.get('Płeć')        or '').strip().upper() or None
            kierunek     = (wiersz.get('kierunek')      or wiersz.get('Kierunek')    or '').strip() or None
            specjalnosc  = (wiersz.get('specjalnosc')   or wiersz.get('Specjalność') or '').strip() or None
            tryb_studiow = (wiersz.get('tryb_studiow')  or wiersz.get('Tryb')        or '').strip().lower() or None

            if not all([imie, nazwisko, email, nr_albumu, plec, kierunek, tryb_studiow]):
                bledy.append(f'Wiersz {nr_wiersza}: brakujące dane (wymagane: imie, nazwisko, email, numer_albumu, plec, kierunek, tryb_studiow)')
                pominieto += 1
                continue

            wiersze_csv.append({
                'nr': nr_wiersza, 'imie': imie, 'nazwisko': nazwisko,
                'email': email, 'nr_albumu': nr_albumu, 'plec': plec,
                'kierunek': kierunek, 'specjalnosc': specjalnosc,
                'tryb_studiow': tryb_studiow,
            })

        if wiersze_csv:
            all_emails = [w['email'] for w in wiersze_csv]
            all_albums = [w['nr_albumu'] for w in wiersze_csv]

            existing = _repo_uzytk.znajdz_istniejace_po_email_lub_albumie(
                all_emails, all_albums
            )

            existing_emails = {row.email for row in existing}
            existing_albums = {row.album_number for row in existing if row.album_number}

            for w in wiersze_csv:
                if w['email'] in existing_emails or w['nr_albumu'] in existing_albums:
                    bledy.append(f"Wiersz {w['nr']}: {w['email']} lub nr {w['nr_albumu']} już istnieje")
                    pominieto += 1
                    continue
                try:
                    _serwis_uzytkownikow.utworz_studenta(
                        email                   = w['email'].lower().strip(),
                        haslo                   = '',
                        imie                    = w['imie'],
                        nazwisko                = w['nazwisko'],
                        numer_albumu            = w['nr_albumu'],
                        gender                  = w['plec'],
                        field_of_study          = w['kierunek'],
                        specialization          = w['specjalnosc'],
                        study_mode              = w['tryb_studiow'],
                        supervisor_id           = uuid.UUID(uopz_id) if uopz_id else None,
                        require_password_change = False,
                        commit                  = False,
                    )
                    existing_emails.add(w['email'])
                    existing_albums.add(w['nr_albumu'])
                    utworzono += 1
                except Exception as e:
                    bledy.append(f"Wiersz {w['nr']}: {str(e)}")
                    pominieto += 1

            db.session.commit()

        wyniki = {'utworzono': utworzono, 'pominieto': pominieto, 'bledy': bledy}
        if utworzono:
            flash(f'Import zakończony: {utworzono} kont utworzonych.', 'success')

    return render_template('zarzadzanie/import_csv.html', form=form, wyniki=wyniki)


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/aktywnosc', methods=['POST'])
@wymaga_roli(UserRole.ADMIN)
def przelacz_aktywnosc(id):
    u = db.session.get(User, id) or abort(404)
    if str(u.id) == str(current_user.id):
        flash('Nie możesz dezaktywować własnego konta.', 'danger')
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    u.is_active = not u.is_active
    db.session.commit()
    stan = 'aktywowane' if u.is_active else 'dezaktywowane'
    flash(f'Konto {u.first_name} {u.last_name} zostało {stan}.', 'success')
    return redirect(url_for('zarzadzanie.lista_uzytkownikow'))


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/usun', methods=['POST'])
@wymaga_roli(UserRole.ADMIN)
def usun_uzytkownika(id):
    u = db.session.get(User, id) or abort(404)
    if str(u.id) == str(current_user.id):
        flash('Nie możesz usunąć własnego konta.', 'danger')
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    imie_nazwisko = f'{u.first_name} {u.last_name}'
    db.session.delete(u)
    db.session.commit()
    flash(f'Konto {imie_nazwisko} zostało trwale usunięte.', 'success')
    return redirect(url_for('zarzadzanie.lista_uzytkownikow'))


