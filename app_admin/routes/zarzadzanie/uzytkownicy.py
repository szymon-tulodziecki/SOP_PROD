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

# ── Użytkownicy ───────────────────────────────────────────────────────────────

@zarzadzanie_bp.route('/uzytkownicy')
@login_required
def lista_uzytkownikow():
    strona     = request.args.get('strona', 1, type=int)
    szukaj     = request.args.get('szukaj', '').strip()
    filtr_rola = request.args.get('rola', '').strip()

    q = db.session.query(Uzytkownik).outerjoin(Student, Uzytkownik.id == Student.id)
    if szukaj:
        q = q.filter(db.or_(
            Uzytkownik.imie.ilike(f'%{szukaj}%'),
            Uzytkownik.nazwisko.ilike(f'%{szukaj}%'),
            Uzytkownik.email.ilike(f'%{szukaj}%'),
            Student.numer_albumu.ilike(f'%{szukaj}%'),
        ))

    if filtr_rola:
        try:
            q = q.filter_by(rola=RolaUzytkownika[filtr_rola])
        except KeyError:
            pass

    uzytkownicy = q.order_by(Uzytkownik.nazwisko, Uzytkownik.imie)\
                   .paginate(page=strona, per_page=25, error_out=False)
    csrf_form = FlaskForm()
    return render_template('zarzadzanie/uzytkownicy.html',
                           uzytkownicy=uzytkownicy,
                           csrf_form=csrf_form)


@zarzadzanie_bp.route('/uzytkownicy/nowy-student', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def nowy_student():
    form = FormularzStudenta()
    uopz_list = db.session.query(Uzytkownik).filter_by(rola=RolaUzytkownika.UOPZ, aktywny=True)\
                  .order_by(Uzytkownik.nazwisko, Uzytkownik.imie).all()
    form.uopz_id.choices = [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]
    if form.validate_on_submit():
        u = _serwis_uzytkownikow.utworz_studenta(
            email         = form.email.data,
            haslo         = form.numer_albumu.data,
            imie          = form.imie.data,
            nazwisko      = form.nazwisko.data,
            numer_albumu  = form.numer_albumu.data,
            plec          = form.plec.data          or None,
            kierunek      = form.kierunek.data      or None,
            specjalnosc   = form.specjalnosc.data   or None,
            tryb_studiow  = form.tryb_studiow.data  or None,
            wymagana_zmiana_hasla=True,
        )
        flash(
            f'Konto studenta {u.imie} {u.nazwisko} (nr alb. {u.numer_albumu}) '
            f'zostało utworzone. Hasło tymczasowe: {u.numer_albumu}',
            'success'
        )
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    return render_template('zarzadzanie/formularz_studenta.html', form=form, uzytkownik=None)


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/edytuj-student', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def edytuj_studenta(id):
    u    = db.session.get(Uzytkownik, id) or abort(404)
    form = FormularzEdycjiStudenta(uzytkownik_id=id, obj=u)
    uopz_list = db.session.query(Uzytkownik).filter_by(rola=RolaUzytkownika.UOPZ, aktywny=True)\
                  .order_by(Uzytkownik.nazwisko, Uzytkownik.imie).all()
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
        u.plec         = form.plec.data or None
        u.kierunek     = form.kierunek.data or None
        u.specjalnosc  = form.specjalnosc.data or None
        u.tryb_studiow = form.tryb_studiow.data or None
        db.session.commit()
        flash('Dane studenta zostały zaktualizowane.', 'success')
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    return render_template('zarzadzanie/formularz_studenta.html', form=form, uzytkownik=u)


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/reset-hasla', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def reset_hasla(id):
    u = db.session.get(Uzytkownik, id) or abort(404)
    if u.role != RolaUzytkownika.STUDENT or not u.album_number:
        flash('Reset hasła dostępny tylko dla studentów z nr albumu.', 'danger')
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    u.password_hash         = generate_password_hash(u.album_number)
    u.wymagana_zmiana_hasla = True
    db.session.commit()
    flash(
        f'Hasło {u.first_name} {u.last_name} zresetowane do nr albumu ({u.album_number}).',
        'success'
    )
    return redirect(url_for('zarzadzanie.lista_uzytkownikow'))


@zarzadzanie_bp.route('/uzytkownicy/nowy-pracownik', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def nowy_pracownik():
    form = FormularzPracownika()
    if form.validate_on_submit():
        haslo_tymczasowe = form.email.data.lower().strip().split('@')[0]
        u = Uzytkownik(
            id                    = uuid.uuid4(),
            first_name            = form.imie.data.strip(),
            last_name             = form.nazwisko.data.strip(),
            email                 = form.email.data.lower().strip(),
            role                  = RolaUzytkownika[form.rola.data],
            password_hash         = generate_password_hash(haslo_tymczasowe),
            wymagana_zmiana_hasla = True,
            is_active             = True,
        )
        db.session.add(u)
        db.session.commit()
        flash(
            f'Konto {u.first_name} {u.last_name} [{u.role.value}] utworzone. '
            f'Hasło tymczasowe: {haslo_tymczasowe}',
            'success'
        )
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    return render_template('zarzadzanie/formularz_pracownika.html', form=form, uzytkownik=None)


@zarzadzanie_bp.route('/uzytkownicy/import-csv', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def import_csv():
    form      = FormularzImportuCSV()
    uopz_list = db.session.query(Uzytkownik).filter_by(rola=RolaUzytkownika.UOPZ, aktywny=True)\
                  .order_by(Uzytkownik.nazwisko, Uzytkownik.imie).all()
    form.uopz_id         = type('X', (), {})()
    form.uopz_id.choices = [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]
    wyniki = None

    if form.validate_on_submit():
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

            if not all([imie, nazwisko, email, nr_albumu]):
                bledy.append(f'Wiersz {nr_wiersza}: brakujące dane (imie, nazwisko, email, numer_albumu)')
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

            existing = db.session.query(
                Uzytkownik.email, Student.numer_albumu
            ).outerjoin(Student, Uzytkownik.id == Student.id).filter(
                db.or_(
                    Uzytkownik.email.in_(all_emails),
                    Student.numer_albumu.in_(all_albums)
                )
            ).all()

            existing_emails = {row.email for row in existing}
            existing_albums = {row.numer_albumu for row in existing if row.numer_albumu}

            for w in wiersze_csv:
                if w['email'] in existing_emails or w['nr_albumu'] in existing_albums:
                    bledy.append(f"Wiersz {w['nr']}: {w['email']} lub nr {w['nr_albumu']} już istnieje")
                    pominieto += 1
                    continue
                try:
                    _serwis_uzytkownikow.utworz_studenta(
                        email        = w['email'],
                        haslo        = w['nr_albumu'],
                        imie         = w['imie'],
                        nazwisko     = w['nazwisko'],
                        numer_albumu = w['nr_albumu'],
                        plec         = w['plec'],
                        kierunek     = w['kierunek'],
                        specjalnosc  = w['specjalnosc'],
                        tryb_studiow = w['tryb_studiow'],
                        wymagana_zmiana_hasla=True,
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
@wymaga_roli(RolaUzytkownika.ADMIN)
def przelacz_aktywnosc(id):
    u = db.session.get(Uzytkownik, id) or abort(404)
    if str(u.id) == str(current_user.id):
        flash('Nie możesz dezaktywować własnego konta.', 'danger')
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    u.is_active = not u.is_active
    db.session.commit()
    stan = 'aktywowane' if u.is_active else 'dezaktywowane'
    flash(f'Konto {u.first_name} {u.last_name} zostało {stan}.', 'success')
    return redirect(url_for('zarzadzanie.lista_uzytkownikow'))


@zarzadzanie_bp.route('/uzytkownicy/<uuid:id>/usun', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def usun_uzytkownika(id):
    u = db.session.get(Uzytkownik, id) or abort(404)
    if str(u.id) == str(current_user.id):
        flash('Nie możesz usunąć własnego konta.', 'danger')
        return redirect(url_for('zarzadzanie.lista_uzytkownikow'))
    imie_nazwisko = f'{u.first_name} {u.last_name}'
    db.session.delete(u)
    db.session.commit()
    flash(f'Konto {imie_nazwisko} zostało trwale usunięte.', 'success')
    return redirect(url_for('zarzadzanie.lista_uzytkownikow'))


