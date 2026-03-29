import uuid
import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, make_response
from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, DateField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, Optional, Length, Email
from flask_login import login_required, current_user
from app_student.extensions import db
import httpx
from app_student.models import Praktyka, ZapisPraktyki, StatusPraktyki, StatusZapisu, SciezkaPraktyki, Uzytkownik, RolaUzytkownika, EfektUczenia, HarmonogramPraktyki, Firma, IndywidualnyProgram, StatusDokumentu, NumerPisma

praktyki_bp = Blueprint('praktyki', __name__)


# ═══════════════════════════════════════════════════════════
# NOWE FORMULARZE KREATORA
# ═══════════════════════════════════════════════════════════

class FormularzSciezka(FlaskForm):
    """Krok 1: Tylko wybór ścieżki."""
    track_type = SelectField('Ścieżka praktyki', choices=[
        ('STANDARD',     'A — Standardowa praktyka'),
        ('EMPLOYMENT',   'B — Praca etatowa / staż'),
        ('OWN_BUSINESS', 'C — Własna działalność gospodarcza'),
    ], validators=[DataRequired(message='Wybierz ścieżkę.')])


class FormularzDaneFirmy(FlaskForm):
    """Krok 2A: Dane zakładu pracy + ZOPZ + terminy (tylko ścieżka A)."""
    # Terminy i dane podstawowe
    termin_od   = DateField('Data rozpoczęcia', validators=[DataRequired(message='Podaj datę.')])
    termin_do   = DateField('Data zakończenia', validators=[DataRequired(message='Podaj datę.')])
    uopz_id     = SelectField('Opiekun uczelniany (UOPZ)', choices=[], validators=[Optional()])
    ubezpieczenie_nw = BooleanField('Posiadam ubezpieczenie NW na czas trwania praktyki')

    # Tryb znalezienia miejsca
    firma_typ  = SelectField('Jak znalazłeś/-aś miejsce praktyki?', choices=[
        ('database', 'Uczelnia kieruje do zakładu (firma ma umowę z ANS)'),
        ('custom',   'Sam/a znalazłem/-am miejsce (wymaga Zał. 9 i Zał. 1)'),
    ], validators=[DataRequired()])
    firma_id   = SelectField('Wybierz firmę z listy', choices=[], validators=[Optional()])

    firma_nazwa                  = StringField('Nazwa zakładu pracy', validators=[Optional(), Length(max=255)])
    firma_adres                  = StringField('Adres (ulica, nr)', validators=[Optional(), Length(max=255)])
    firma_miasto                 = StringField('Miasto i kod pocztowy', validators=[Optional(), Length(max=100)])
    firma_nip_krs                = StringField('NIP / KRS', validators=[Optional(), Length(max=50)])
    firma_upowazniony_osoba      = StringField('Osoba upoważniona do podpisania porozumienia', validators=[Optional(), Length(max=255)])
    firma_upowazniony_stanowisko = StringField('Stanowisko osoby upoważnionej', validators=[Optional(), Length(max=255)])

    zopz_imie_nazwisko = StringField('Opiekun zakładowy (ZOPZ) — imię i nazwisko', validators=[Optional(), Length(max=255)])
    zopz_stanowisko    = StringField('Stanowisko ZOPZ', validators=[Optional(), Length(max=255)])
    zopz_telefon       = StringField('Telefon ZOPZ', validators=[Optional(), Length(max=50)])
    zopz_email         = StringField('E-mail ZOPZ', validators=[Optional(), Email(message='Nieprawidłowy email.')])


class FormularzWniosek(FlaskForm):
    """Krok 2B/C: Wniosek dla ścieżek B i C."""
    pracodawca_nazwa    = StringField('Nazwa pracodawcy / firmy', validators=[DataRequired(message='Podaj nazwę.'), Length(max=255)])
    pracodawca_adres    = StringField('Adres', validators=[Optional(), Length(max=255)])
    pracodawca_miasto   = StringField('Miasto', validators=[Optional(), Length(max=100)])
    stanowisko          = StringField('Stanowisko / zakres działalności', validators=[DataRequired(message='Podaj stanowisko.'), Length(max=255)])
    uzasadnienie        = TextAreaField('Uzasadnienie wniosku', validators=[DataRequired(message='Napisz uzasadnienie.'), Length(max=2000)])


# ═══════════════════════════════════════════════════════════
# NOWE ROUTE KREATORA
# ═══════════════════════════════════════════════════════════

@praktyki_bp.route('/<uuid:id>/kreator/sciezka', methods=['GET', 'POST'])
@login_required
def kreator_sciezka(id):
    """Krok 1: Wybór ścieżki."""
    praktyka = db.session.get(Praktyka, id)
    if not praktyka:
        flash('Praktyka niedostępna.', 'danger')
        return redirect(url_for('praktyki.lista'))

    istniejacy = db.session.query(ZapisPraktyki).filter_by(
        internship_id=id, student_id=current_user.id
    ).filter(ZapisPraktyki.status == StatusZapisu.PENDING).first()

    form = FormularzSciezka()

    if form.validate_on_submit():
        if istniejacy:
            zapis = istniejacy
        else:
            zapis = ZapisPraktyki(id=uuid.uuid4(), internship_id=id,
                                   student_id=current_user.id, status=StatusZapisu.PENDING)
            db.session.add(zapis)

        zapis.track_type = SciezkaPraktyki[form.track_type.data]
        db.session.commit()

        if form.track_type.data == 'STANDARD':
            return redirect(url_for('praktyki.kreator_firma', zapis_id=zapis.id))
        else:
            return redirect(url_for('praktyki.kreator_wniosek', zapis_id=zapis.id))

    if istniejacy and request.method == 'GET':
        form.track_type.data = istniejacy.track_type.value if istniejacy.track_type else 'STANDARD'

    return render_template('kreator/krok1_sciezka.html', form=form, praktyka=praktyka, istniejacy=istniejacy)


@praktyki_bp.route('/zgloszenie/<uuid:zapis_id>/kreator/firma', methods=['GET', 'POST'])
@login_required
def kreator_firma(zapis_id):
    """Krok 2A: Dane zakładu + ZOPZ (ścieżka A)."""
    zapis = db.session.get(ZapisPraktyki, zapis_id)
    if not zapis or zapis.student_id != current_user.id or zapis.track_type != SciezkaPraktyki.STANDARD:
        abort(404)

    form = FormularzDaneFirmy()
    firmy_list = db.session.query(Firma).filter_by(is_active=True).order_by(Firma.nazwa).all()
    form.firma_id.choices = [('', '--- Wybierz firmę ---')] + [(str(f.id), f.nazwa) for f in firmy_list]
    uopz_list = db.session.query(Uzytkownik).filter_by(role=RolaUzytkownika.UOPZ, is_active=True).order_by(Uzytkownik.last_name).all()
    form.uopz_id.choices = [('', '--- Wybierz ---')] + [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]

    if form.validate_on_submit():
        if not form.ubezpieczenie_nw.data:
            flash('Ubezpieczenie NW jest wymagane.', 'danger')
            return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)

        zapis.termin_od  = form.termin_od.data
        zapis.termin_do  = form.termin_do.data
        zapis.uopz_id    = form.uopz_id.data if form.uopz_id.data else None
        zapis.ubezpieczenie_nw = True
        zapis.specjalnosc = getattr(current_user, 'specjalnosc', '') or ''

        if form.firma_typ.data == 'database':
            if not form.firma_id.data:
                flash('Wybierz firmę z listy.', 'danger')
                return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)
            zapis.firma_id = form.firma_id.data
            zapis.firma_nazwa = zapis.firma_adres = zapis.firma_miasto = None
            zapis.firma_nip_krs = zapis.firma_upowazniony_osoba = zapis.firma_upowazniony_stanowisko = None
        else:
            if not form.firma_nazwa.data or not form.firma_adres.data or not form.firma_miasto.data:
                flash('Podaj nazwę, adres i miasto firmy.', 'danger')
                return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)
            zapis.firma_id = None
            zapis.firma_nazwa                  = form.firma_nazwa.data
            zapis.firma_adres                  = form.firma_adres.data
            zapis.firma_miasto                 = form.firma_miasto.data
            zapis.firma_nip_krs                = form.firma_nip_krs.data
            zapis.firma_upowazniony_osoba      = form.firma_upowazniony_osoba.data
            zapis.firma_upowazniony_stanowisko = form.firma_upowazniony_stanowisko.data

        if not form.zopz_imie_nazwisko.data or not form.zopz_email.data:
            flash('Podaj imię/nazwisko i email opiekuna zakładowego (ZOPZ).', 'danger')
            return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)

        zapis.zopz_imie_nazwisko = form.zopz_imie_nazwisko.data
        zapis.zopz_stanowisko    = form.zopz_stanowisko.data
        zapis.zopz_telefon       = form.zopz_telefon.data
        zapis.zopz_email         = form.zopz_email.data
        db.session.commit()
        return redirect(url_for('praktyki.zapisz_krok2', id=zapis.id))

    if request.method == 'GET':
        form.termin_od.data = zapis.termin_od
        form.termin_do.data = zapis.termin_do
        form.uopz_id.data   = str(zapis.uopz_id) if zapis.uopz_id else ''
        form.ubezpieczenie_nw.data = zapis.ubezpieczenie_nw
        form.firma_typ.data = 'database' if zapis.firma_id else 'custom'
        form.firma_id.data  = str(zapis.firma_id) if zapis.firma_id else ''
        form.firma_nazwa.data = zapis.firma_nazwa
        form.firma_adres.data = zapis.firma_adres
        form.firma_miasto.data = zapis.firma_miasto
        form.firma_nip_krs.data = zapis.firma_nip_krs
        form.firma_upowazniony_osoba.data = zapis.firma_upowazniony_osoba
        form.firma_upowazniony_stanowisko.data = zapis.firma_upowazniony_stanowisko
        form.zopz_imie_nazwisko.data = zapis.zopz_imie_nazwisko
        form.zopz_stanowisko.data = zapis.zopz_stanowisko
        form.zopz_telefon.data = zapis.zopz_telefon
        form.zopz_email.data = zapis.zopz_email

    return render_template('kreator/krok2a_firma.html', form=form, zapis=zapis, firmy_list=firmy_list)


@praktyki_bp.route('/zgloszenie/<uuid:zapis_id>/kreator/wniosek', methods=['GET', 'POST'])
@login_required
def kreator_wniosek(zapis_id):
    """Krok 2B/C: Wniosek dla ścieżek B i C."""
    zapis = db.session.get(ZapisPraktyki, zapis_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.track_type == SciezkaPraktyki.STANDARD:
        return redirect(url_for('praktyki.kreator_firma', zapis_id=zapis_id))

    form = FormularzWniosek()

    if form.validate_on_submit():
        zapis.firma_nazwa  = form.pracodawca_nazwa.data
        zapis.firma_adres  = form.pracodawca_adres.data
        zapis.firma_miasto = form.pracodawca_miasto.data
        zapis.zopz_stanowisko = form.stanowisko.data
        zapis.uzasadnienie_sciezki = form.uzasadnienie.data
        zapis.status = StatusZapisu.COMMISSION_REVIEW
        db.session.commit()
        flash('Wniosek złożony. Oczekujesz na decyzję komisji.', 'success')
        return redirect(url_for('praktyki.szczegoly_zgloszenia', id=zapis.id))

    if request.method == 'GET':
        form.pracodawca_nazwa.data  = zapis.firma_nazwa
        form.pracodawca_adres.data  = zapis.firma_adres
        form.pracodawca_miasto.data = zapis.firma_miasto
        form.stanowisko.data        = zapis.zopz_stanowisko
        form.uzasadnienie.data      = zapis.uzasadnienie_sciezki

    return render_template('kreator/krok2bc_wniosek.html', form=form, zapis=zapis)


# ═══════════════════════════════════════════════════════════
# STARE FORMULARZE (zachowane dla zgodności)
# ═══════════════════════════════════════════════════════════

class FormularzZapisuKrok1(FlaskForm):
    track_type = SelectField('Ścieżka praktyki', choices=[
        ('STANDARD', 'Standardowa'),
        ('EMPLOYMENT', 'Praca etatowa'),
        ('OWN_BUSINESS', 'Własna działalność gospodarcza')
    ], validators=[DataRequired(message='To pole jest wymagane.')])

    termin_od = DateField('Data rozpoczęcia', validators=[DataRequired(message='To pole jest wymagane.')])
    termin_do = DateField('Data zakończenia', validators=[DataRequired(message='To pole jest wymagane.')])
    specjalnosc = StringField('Specjalność', validators=[DataRequired(message='To pole jest wymagane.')])
    ubezpieczenie_nw = BooleanField('Posiadam ubezpieczenie NW (wymagane)')

    # Wybór typu firmy
    firma_typ = SelectField('Typ firmy', choices=[
        ('database', 'Wybierz firmę z bazy (ma stałą umowę z uczelnią)'),
        ('custom', 'Podaj własną firmę (wymagane Załącznik 3)')
    ], validators=[DataRequired(message='To pole jest wymagane.')])

    # Firma z bazy
    firma_id = SelectField('Firma z bazy', choices=[], validators=[Optional()])

    # Firma własna (walidacja manualna — pola Optional, bo zależą od firma_typ)
    firma_nazwa = StringField('Nazwa zakładu pracy', validators=[Optional()])
    firma_adres = StringField('Adres (ulica, nr)', validators=[Optional()])
    firma_miasto = StringField('Miasto i kod pocztowy', validators=[Optional()])
    firma_nip_krs = StringField('NIP / KRS', validators=[Optional()])
    firma_upowazniony_osoba = StringField('Osoba upoważniona do podpisania Porozumienia (Imię i nazwisko)', validators=[Optional()])
    firma_upowazniony_stanowisko = StringField('Stanowisko osoby upoważnionej', validators=[Optional()])

    # ZOPZ (Optional — walidacja manualna, bo widoczność zależy od firma_typ)
    zopz_imie_nazwisko = StringField('Opiekun Zakładowy (ZOPZ) - Imię i nazwisko', validators=[Optional()])
    zopz_stanowisko = StringField('Stanowisko ZOPZ', validators=[Optional()])
    zopz_telefon = StringField('Telefon ZOPZ', validators=[Optional()])
    zopz_email = StringField('E-mail ZOPZ', validators=[Optional(), Email(message='Nieprawidłowy adres email.')])

    # UOPZ
    uopz_id = SelectField('Wybierz Opiekuna Uczelnianego (UOPZ)', choices=[], validators=[Optional()])


@praktyki_bp.route('/')
@login_required
def lista():
    dostepne = db.session.query(Praktyka)\
                 .order_by(Praktyka.rok_uczelniany.desc())\
                 .all()

    zapisy_data = {
        str(z.internship_id): {'id': str(z.id), 'status': z.status.value}
        for z in db.session.query(ZapisPraktyki)\
                   .filter_by(student_id=current_user.id).all()
    }

    csrf_form = FlaskForm()
    return render_template('praktyki/lista.html', dostepne=dostepne, zapisy_data=zapisy_data, csrf_form=csrf_form)


@praktyki_bp.route('/zgloszenie/<uuid:id>/zakoncz', methods=['POST'])
@login_required
def zakoncz_praktyke(id):
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
    if zapis.status != StatusZapisu.IN_PROGRESS:
        flash('Praktykę można zakończyć tylko gdy jest w trakcie realizacji.', 'warning')
        return redirect(url_for('praktyki.lista'))
    zapis.status = StatusZapisu.COMPLETED
    db.session.commit()
    flash('Praktyka została oznaczona jako zakończona. Dokumenty końcowe są teraz dostępne w zakładce Moje Dokumenty.', 'success')
    return redirect(url_for('praktyki.lista'))


@praktyki_bp.route('/<uuid:id>/zapisz/krok1', methods=['GET', 'POST'])
@login_required
def zapisz_krok1(id):
    praktyka = db.session.get(Praktyka, id)
    if not praktyka:
        flash('Ta praktyka nie jest dostępna.', 'danger')
        return redirect(url_for('praktyki.lista'))

    # Sprawdź czy istnieje aktualny zapis w statusie edytowalnym
    istniejacy = db.session.query(ZapisPraktyki).filter_by(
        internship_id=id,
        student_id=current_user.id
    ).filter(
        ZapisPraktyki.status.in_([StatusZapisu.PENDING, StatusZapisu.AWAITING_APPROVAL])
    ).first()

    if istniejacy:
        if istniejacy.status == StatusZapisu.PENDING:
            # Zawsze pozwól edytować krok 1 gdy status PENDING (nowe lub zwrócone do poprawy)
            form = FormularzZapisuKrok1(obj=istniejacy)
        else:
            # AWAITING_APPROVAL lub wyższy — tylko szczegóły
            flash('Zgłoszenie zostało wysłane i oczekuje na zatwierdzenie. Nie można edytować.', 'info')
            return redirect(url_for('praktyki.szczegoly_zgloszenia', id=istniejacy.id))
    else:
        form = FormularzZapisuKrok1()

    uopz_list = db.session.query(Uzytkownik).filter_by(role=RolaUzytkownika.UOPZ, is_active=True).order_by(Uzytkownik.last_name).all()
    form.uopz_id.choices = [('', '--- Wybierz UOPZ ---')] + [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]

    # Pobierz firmy z bazy (te które mają stałą umowę)
    firmy_list = db.session.query(Firma).filter_by(has_standing_agreement=True, is_active=True).order_by(Firma.nazwa).all()
    form.firma_id.choices = [('', '--- Wybierz firmę ---')] + [(str(f.id), f.nazwa) for f in firmy_list]

    if form.validate_on_submit():
        if not form.ubezpieczenie_nw.data:
            flash('Ubezpieczenie NW jest wymagane przed startem.', 'danger')
            return render_template('praktyki/krok1.html', form=form, praktyka=praktyka)

        # Walidacja wyboru firmy
        if form.firma_typ.data == 'database':
            if not form.firma_id.data:
                flash('Musisz wybrać firmę z bazy danych.', 'danger')
                return render_template('praktyki/krok1.html', form=form, praktyka=praktyka)
        elif form.firma_typ.data == 'custom':
            if not form.firma_nazwa.data or not form.firma_adres.data or not form.firma_miasto.data:
                flash('Musisz podać dane własnej firmy (nazwa, adres, miasto).', 'danger')
                return render_template('praktyki/krok1.html', form=form, praktyka=praktyka)
            if not form.zopz_imie_nazwisko.data or not form.zopz_email.data:
                flash('Musisz podać dane opiekuna zakładowego (ZOPZ) - przynajmniej imię/nazwisko i email.', 'danger')
                return render_template('praktyki/krok1.html', form=form, praktyka=praktyka)

        if istniejacy and istniejacy.status == StatusZapisu.PENDING:
            # Aktualizuj istniejący zapis (powrót do edycji lub poprawa po komentarzu admina)
            zapis = istniejacy
            zapis.track_type = SciezkaPraktyki[form.track_type.data]
            zapis.termin_od = form.termin_od.data
            zapis.termin_do = form.termin_do.data
            zapis.specjalnosc = form.specjalnosc.data
            zapis.ubezpieczenie_nw = form.ubezpieczenie_nw.data

            # Ustaw firmę na podstawie wyboru
            if form.firma_typ.data == 'database':
                zapis.firma_id = form.firma_id.data
                # Wyczyść pola custom firmy
                zapis.firma_nazwa = None
                zapis.firma_adres = None
                zapis.firma_miasto = None
                zapis.firma_nip_krs = None
                zapis.firma_upowazniony_osoba = None
                zapis.firma_upowazniony_stanowisko = None
            else:
                zapis.firma_id = None
                zapis.firma_nazwa = form.firma_nazwa.data
                zapis.firma_adres = form.firma_adres.data
                zapis.firma_miasto = form.firma_miasto.data
                zapis.firma_nip_krs = form.firma_nip_krs.data
                zapis.firma_upowazniony_osoba = form.firma_upowazniony_osoba.data
                zapis.firma_upowazniony_stanowisko = form.firma_upowazniony_stanowisko.data
            zapis.zopz_imie_nazwisko = form.zopz_imie_nazwisko.data
            zapis.zopz_stanowisko = form.zopz_stanowisko.data
            zapis.zopz_telefon = form.zopz_telefon.data
            zapis.zopz_email = form.zopz_email.data
            zapis.uopz_id = form.uopz_id.data if form.uopz_id.data else None
            # Wyczyść komentarze admina po poprawie
            zapis.admin_comments = None
            # Sprawdź czy istnieją dane harmonogramu - jeśli tak, nie zmieniaj statusu jeszcze
            harmonogramy_count = db.session.query(HarmonogramPraktyki).filter_by(enrollment_id=zapis.id).count()
            if harmonogramy_count > 0:
                # Są dane harmonogramu, pozwól na dalszą edycję bez zmiany statusu
                flash('Poprawiono dane podstawowe. Możesz przejść do dalszych kroków lub wysłać zgłoszenie.', 'success')
            else:
                # Brak harmonogramu, wymaga przejścia przez kolejne kroki
                flash('Poprawiono dane podstawowe. Przejdź do planowania harmonogramu.', 'success')
        else:
            # Stwórz nowy zapis
            zapis = ZapisPraktyki(
                id            = uuid.uuid4(),
                internship_id = id,
                student_id    = current_user.id,
                status        = StatusZapisu.PENDING,
                track_type    = SciezkaPraktyki[form.track_type.data],
                termin_od     = form.termin_od.data,
                termin_do     = form.termin_do.data,
                specjalnosc   = form.specjalnosc.data,
                ubezpieczenie_nw = form.ubezpieczenie_nw.data,
                zopz_imie_nazwisko = form.zopz_imie_nazwisko.data,
                zopz_stanowisko = form.zopz_stanowisko.data,
                zopz_telefon = form.zopz_telefon.data,
                zopz_email = form.zopz_email.data,
                uopz_id = form.uopz_id.data if form.uopz_id.data else None
            )

            # Ustaw firmę na podstawie wyboru
            if form.firma_typ.data == 'database':
                zapis.firma_id = form.firma_id.data
            else:
                zapis.firma_nazwa = form.firma_nazwa.data
                zapis.firma_adres = form.firma_adres.data
                zapis.firma_miasto = form.firma_miasto.data
                zapis.firma_nip_krs = form.firma_nip_krs.data
                zapis.firma_upowazniony_osoba = form.firma_upowazniony_osoba.data
                zapis.firma_upowazniony_stanowisko = form.firma_upowazniony_stanowisko.data
            db.session.add(zapis)
            flash(f'Zapisano wstępne dane. Przejdź do planowania harmonogramu.', 'success')

        db.session.commit()
        return redirect(url_for('praktyki.zapisz_krok2', id=zapis.id))

    return render_template('praktyki/krok1.html', form=form, praktyka=praktyka)


@praktyki_bp.route('/zgloszenie/<uuid:id>/krok2', methods=['GET', 'POST'])
@login_required
def zapisz_krok2(id):
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
        
    efekty = db.session.query(EfektUczenia).order_by(EfektUczenia.id).all()
        
    if request.method == 'POST':
        # Czyszczenie starego jeśli student wraca z jakiegoś powodu
        db.session.query(HarmonogramPraktyki).filter_by(enrollment_id=zapis.id).delete()
        
        suma_dni = 0
        nowe_wiersze = []
        for e in efekty:
            dz = request.form.get(f'dzial_{e.id}', '')
            pr = request.form.get(f'prace_{e.id}', '')
            dni_str = request.form.get(f'dni_{e.id}', '0')
            try:
                dni = int(dni_str)
            except Exception:
                dni = 0
                
            if dz.strip() and pr.strip():
                nowe_wiersze.append(HarmonogramPraktyki(
                    id=uuid.uuid4(),
                    enrollment_id=zapis.id,
                    learning_outcome_id=e.id,
                    nazwa_dzialu=dz,
                    przykladowe_prace=pr,
                    liczba_dni=dni
                ))
                suma_dni += dni
                
        db.session.add_all(nowe_wiersze)
        db.session.commit()
        
        if zapis.track_type.value != 'STANDARD':
            flash('Harmonogram zapisany. Przejdź do uzasadnienia ścieżki zawodowej.', 'success')
            return redirect(url_for('praktyki.zapisz_krok3', id=zapis.id))
        else:
            flash('Wniosek został w pełni zapisany. Oczekuje teraz na akceptację UOPZ.', 'success')
            return redirect(url_for('dashboard.index'))
    else:
        # GET request - pobranie istniejących danych harmonogramu
        istniejace_harmonogramy = {}
        harmonogramy = db.session.query(HarmonogramPraktyki).filter_by(enrollment_id=zapis.id).all()
        for h in harmonogramy:
            istniejace_harmonogramy[str(h.learning_outcome_id)] = {
                'dzial': h.nazwa_dzialu,
                'prace': h.przykladowe_prace,
                'dni': h.liczba_dni
            }

    csrf_form = FlaskForm()

    return render_template('praktyki/krok2.html',
                         zapis=zapis,
                         efekty=efekty,
                         csrf_form=csrf_form,
                         istniejace_harmonogramy=istniejace_harmonogramy)


class FormularzZapisuKrok3(FlaskForm):
    uzasadnienie = TextAreaField('Uzasadnienie wniosku', validators=[DataRequired()])
    zalaczniki = StringField('Załączane dokumenty (wymień)', validators=[DataRequired()])

@praktyki_bp.route('/zgloszenie/<uuid:id>/krok3', methods=['GET', 'POST'])
@login_required
def zapisz_krok3(id):
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)
        
    if zapis.track_type.value == 'STANDARD':
        return redirect(url_for('dashboard.index'))
        
    form = FormularzZapisuKrok3()

    # Wypełnij formularz istniejącymi danymi jeśli są
    if request.method == 'GET' and zapis.uzasadnienie_sciezki:
        form.uzasadnienie.data = zapis.uzasadnienie_sciezki
    if request.method == 'GET' and zapis.zalaczniki_sciezki:
        form.zalaczniki.data = zapis.zalaczniki_sciezki

    if form.validate_on_submit():
        zapis.uzasadnienie_sciezki = form.uzasadnienie.data
        zapis.zalaczniki_sciezki = form.zalaczniki.data
        db.session.commit()

        flash('Wniosek zapisany. Przejdź do załączania dokumentów.', 'success')
        return redirect(url_for('praktyki.zapisz_krok4', id=zapis.id))

    return render_template('praktyki/krok3.html', form=form, zapis=zapis)


@praktyki_bp.route('/zgloszenie/<uuid:id>/krok4', methods=['GET', 'POST'])
@login_required
def zapisz_krok4(id):
    """Krok 4: Upload dokumentów dla ścieżek B i C"""
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    if zapis.track_type.value == 'STANDARD':
        return redirect(url_for('dashboard.index'))

    # Sprawdź czy poprzednie kroki zostały ukończone
    if not zapis.uzasadnienie_sciezki:
        flash('Najpierw uzupełnij uzasadnienie w kroku 3.', 'warning')
        return redirect(url_for('praktyki.zapisz_krok3', id=id))

    # Zdefiniuj wymagane typy dokumentów dla każdej ścieżki
    required_docs = {
        'EMPLOYMENT': [
            ('umowa_pracy', 'Umowa o pracę lub zaświadczenie o zatrudnieniu'),
            ('opis_stanowiska', 'Opis stanowiska pracy / karta stanowiskowa'),
            ('zakres_obowiazkow', 'Zakres obowiązków i realizowanych zadań')
        ],
        'OWN_BUSINESS': [
            ('ceidg_krs', 'Aktualny wpis do CEIDG lub KRS'),
            ('opis_dzialalnosci', 'Opis profilu działalności gospodarczej'),
            ('projekty_komercyjne', 'Dokumenty potwierdzające realizowane projekty')
        ]
    }

    docs_for_track = required_docs.get(zapis.track_type.value, [])

    if request.method == 'POST':
        if request.form.get('action') == 'finalize':
            # Sprawdź czy wszystkie wymagane dokumenty zostały uploadowane
            from sqlalchemy import text
            uploaded_types_query = text("""
                SELECT DISTINCT document_type
                FROM uploaded_documents
                WHERE enrollment_id = :enrollment_id
            """)
            uploaded_types = {row[0] for row in db.session.execute(uploaded_types_query, {'enrollment_id': str(id)})}

            required_types = {doc_type for doc_type, _ in docs_for_track}
            missing_docs = required_types - uploaded_types

            if missing_docs:
                flash(f'Brakuje dokumentów: {", ".join(missing_docs)}', 'warning')
            else:
                # Zmień status na COMMISSION_REVIEW
                zapis.status = StatusZapisu.COMMISSION_REVIEW
                db.session.commit()
                flash('Wniosek został przesłany do weryfikacji przez komisję!', 'success')
                return redirect(url_for('dashboard.index'))

    return render_template('praktyki/krok4.html', zapis=zapis, required_docs=docs_for_track)


@praktyki_bp.route('/zgloszenie/<uuid:id>/szczegoly')
@login_required
def szczegoly_zgloszenia(id):
    """Szczegóły zgłoszenia studenta wraz z komentarzami UOPZ"""
    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    # Pobierz uploadowane dokumenty (raw SQL — model jest w app_admin)
    from sqlalchemy import text as _text
    rows = db.session.execute(
        _text("SELECT id, original_filename, document_type, uploaded_at FROM uploaded_documents WHERE enrollment_id=:eid ORDER BY uploaded_at DESC"),
        {'eid': str(id)}
    ).fetchall()
    uploaded_docs = [{'id': r[0], 'original_filename': r[1], 'document_type': r[2], 'uploaded_at': r[3]} for r in rows]

    return render_template('praktyki/szczegoly_zgloszenia.html', zapis=zapis, uploaded_docs=uploaded_docs)


def get_next_document_number():
    """Generuje kolejny numer pisma wychodzącego"""
    current_year = datetime.datetime.now().year

    # Znajdź ostatni numer w tym roku
    last_number = db.session.query(NumerPisma)\
        .filter(NumerPisma.numer.like(f'ANS/PZ/{current_year}/%'))\
        .order_by(NumerPisma.numer.desc())\
        .first()

    if last_number:
        # Wyciągnij numer i zwiększ o 1
        parts = last_number.numer.split('/')
        last_num = int(parts[-1])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"ANS/PZ/{current_year}/{next_num:03d}"


@praktyki_bp.route('/zgloszenie/<uuid:id>/dokument/<doc_type>')
@login_required
def generuj_dokument_praktyki(id, doc_type):
    """Generuje konkretny dokument PDF dla praktyki"""

    zapis = db.session.get(ZapisPraktyki, id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    # Sprawdź czy można generować dokumenty - tylko dla zatwierdzonych praktyk
    if zapis.status not in [StatusZapisu.IN_PROGRESS, StatusZapisu.COMPLETED]:
        flash('Dokumenty można generować tylko dla zatwierdzonych praktyk.', 'error')
        return redirect(url_for('praktyki.szczegoly_zgloszenia', id=id))

    # Sprawdź czy harmonogram jest wypełniony
    harmonogram_count = db.session.query(HarmonogramPraktyki)\
        .filter_by(enrollment_id=zapis.id)\
        .count()

    if harmonogram_count == 0:
        flash('Najpierw uzupełnij harmonogram praktyki.', 'error')
        return redirect(url_for('praktyki.zapisz_krok2', id=zapis.id))

    # Dla załącznika 3 sprawdź czy firma nie ma stałej umowy
    if doc_type == 'ZALACZNIK_3':
        if zapis.firma and zapis.firma.has_standing_agreement:
            flash('Załącznik 3 nie jest wymagany - firma ma stałą umowę z uczelnią.', 'error')
            return redirect(url_for('praktyki.szczegoly_zgloszenia', id=id))

    # Dla załącznika 4 wystarczy że harmonogram jest wypełniony (sprawdzono wyżej)

    # Generuj numer pisma dla załącznika 2
    numer_pisma = None
    if doc_type == 'ZALACZNIK_2':
        existing_number = db.session.query(NumerPisma)\
            .filter_by(enrollment_id=zapis.id, document_type='ZALACZNIK_2')\
            .first()

        if not existing_number:
            numer_pisma = get_next_document_number()
            new_number = NumerPisma(
                id=uuid.uuid4(),
                enrollment_id=zapis.id,
                document_type='ZALACZNIK_2',
                numer=numer_pisma
            )
            db.session.add(new_number)
            db.session.commit()
        else:
            numer_pisma = existing_number.numer

    # Przygotuj dane do generacji PDF
    data = {
        'student': {
            'imie': zapis.student.first_name,
            'nazwisko': zapis.student.last_name,
            'nr_albumu': zapis.student.album_number,
            'plec': getattr(zapis.student, 'plec', '') or '',
        },
        'praktyka': {
            'rok_uczelniany': zapis.praktyka.rok_uczelniany,
            'semestr': zapis.praktyka.semestr,
            'wymiar_godzin': zapis.praktyka.wymiar_godzin
        },
        'firma': {
            'nazwa': (zapis.firma.nazwa if zapis.firma else None) or zapis.firma_nazwa or '',
            'adres': (zapis.firma.adres if zapis.firma else None) or zapis.firma_adres or '',
            'miasto': (zapis.firma.miasto if zapis.firma else None) or zapis.firma_miasto or '',
            'nip_krs': (zapis.firma.nip_krs if zapis.firma else None) or zapis.firma_nip_krs or '',
        },
        'firma_upowazniony': zapis.firma_upowazniony_osoba or '',
        'specjalnosc': zapis.specjalnosc or '',
        'terminy': {
            'od': zapis.termin_od.strftime('%d.%m.%Y') if zapis.termin_od else '',
            'do': zapis.termin_do.strftime('%d.%m.%Y') if zapis.termin_do else ''
        },
        'numer_pisma': numer_pisma,
        'zopz': {
            'imie_nazwisko': zapis.zopz_imie_nazwisko,
            'stanowisko': zapis.zopz_stanowisko,
            'telefon': zapis.zopz_telefon,
            'email': zapis.zopz_email
        },
        'uopz': {
            'imie_nazwisko': f"{zapis.uopz.first_name} {zapis.uopz.last_name}" if zapis.uopz else '',
        }
    }

    # Dodaj harmonogram dla załącznika 4
    if doc_type == 'ZALACZNIK_4':
        harmonogram = db.session.query(HarmonogramPraktyki)\
            .filter_by(enrollment_id=zapis.id)\
            .all()

        data['harmonogram'] = [{
            'efekt_kod': h.efekt.kod,
            'efekt_opis': h.efekt.opis,
            'dzial': h.nazwa_dzialu,
            'prace': h.przykladowe_prace,
            'dni': h.liczba_dni
        } for h in harmonogram]

    # Mapowanie typów dokumentów na szablony (poprawne numery załączników)
    SZABLONY_MAP = {
        'ZALACZNIK_3': 'zal1_porozumienie.tex.j2',  # Porozumienie = Zał. 1
        'ZALACZNIK_4': 'zal2a_program.tex.j2',      # Indywidualny Program = Zał. 2a
    }
    template_name = SZABLONY_MAP.get(doc_type, f'{doc_type.lower()}.tex.j2')

    try:
        # Wywołaj tex-service
        response = httpx.post(
            'http://tex-service:5002/generuj',
            json={
                'template': template_name,
                'context': data,
                'filename': f"{template_name.replace('.tex.j2', '')}_{zapis.student.last_name}.pdf"
            },
            timeout=30
        )

        if response.status_code == 200:
            import unicodedata
            safe_name = unicodedata.normalize('NFKD', zapis.student.last_name).encode('ascii', 'ignore').decode('ascii') or 'student'
            pdf_name = template_name.replace('.tex.j2', '')
            pdf_response = make_response(response.content)
            pdf_response.headers['Content-Type'] = 'application/pdf'
            pdf_response.headers['Content-Disposition'] = f'attachment; filename="{pdf_name}_{safe_name}.pdf"'
            return pdf_response
        else:
            flash(f'Błąd generowania dokumentu: {response.text}', 'error')

    except Exception as e:
        flash(f'Błąd połączenia z serwisem PDF: {str(e)}', 'error')

    return redirect(url_for('praktyki.szczegoly_zgloszenia', id=id))