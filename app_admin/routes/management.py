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

from app_admin.models import (Uzytkownik, Praktyka, ZapisPraktyki, HarmonogramPraktyki, EfektUczenia,
                    RolaUzytkownika, StatusPraktyki, StatusZapisu, UploadedDocument, Firma)
from app_admin.extensions import db
from app_admin.routes.auth import wymaga_roli

management_bp = Blueprint('management', __name__)


# ── Formularze ────────────────────────────────────────────────────────────────

class FormularzStudenta(FlaskForm):
    imie         = StringField('Imię',      validators=[DataRequired(), Length(max=100)])
    nazwisko     = StringField('Nazwisko',  validators=[DataRequired(), Length(max=100)])
    email        = StringField('E-mail',    validators=[DataRequired(), Email(), Length(max=255)])
    numer_albumu = StringField('Nr albumu', validators=[DataRequired(), Length(max=20)])
    plec         = SelectField('Płeć', choices=[('', '--- Wybierz ---'), ('M', 'Mężczyzna'), ('K', 'Kobieta')], validators=[Optional()])
    kierunek     = StringField('Kierunek studiów', validators=[Optional(), Length(max=100)])
    specjalnosc  = StringField('Specjalność', validators=[Optional(), Length(max=100)])
    tryb_studiow = SelectField('Tryb studiów', choices=[('', '--- Wybierz ---'), ('stacjonarne', 'Stacjonarne'), ('niestacjonarne', 'Niestacjonarne')], validators=[Optional()])
    uopz_id      = SelectField('Opiekun uczelniany (UOPZ)', choices=[], validators=[Optional()])

    def validate_email(self, pole):
        q = db.session.query(Uzytkownik).filter_by(email=pole.data.lower().strip()).first()
        if q:
            raise ValidationError('Konto z tym e-mailem już istnieje.')

    def validate_numer_albumu(self, pole):
        q = db.session.query(Uzytkownik).filter_by(album_number=pole.data.strip()).first()
        if q:
            raise ValidationError('Student z tym nr albumu już istnieje.')


class FormularzEdycjiStudenta(FormularzStudenta):
    def __init__(self, uzytkownik_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._uid = uzytkownik_id

    def validate_email(self, pole):
        q = db.session.query(Uzytkownik).filter_by(email=pole.data.lower().strip()).first()
        if q and str(q.id) != str(self._uid):
            raise ValidationError('Konto z tym e-mailem już istnieje.')

    def validate_numer_albumu(self, pole):
        q = db.session.query(Uzytkownik).filter_by(album_number=pole.data.strip()).first()
        if q and str(q.id) != str(self._uid):
            raise ValidationError('Student z tym nr albumu już istnieje.')


class FormularzPracownika(FlaskForm):
    imie     = StringField('Imię',     validators=[DataRequired(), Length(max=100)])
    nazwisko = StringField('Nazwisko', validators=[DataRequired(), Length(max=100)])
    email    = StringField('E-mail',   validators=[DataRequired(), Email(), Length(max=255)])
    rola     = SelectField('Rola', choices=[
        ('UOPZ',  'Opiekun uczelniany (UOPZ)'),
        ('ADMIN', 'Administrator'),
    ], validators=[DataRequired()])

    def validate_email(self, pole):
        q = db.session.query(Uzytkownik).filter_by(email=pole.data.lower().strip()).first()
        if q:
            raise ValidationError('Konto z tym e-mailem już istnieje.')


class FormularzImportuCSV(FlaskForm):
    plik = FileField('Plik CSV', validators=[
        DataRequired(),
        FileAllowed(['csv'], 'Tylko pliki CSV.')
    ])


class FormularzFirmy(FlaskForm):
    nazwa = StringField('Nazwa firmy', validators=[DataRequired(), Length(max=255)])
    adres = StringField('Adres', validators=[Optional(), Length(max=255)])
    miasto = StringField('Miasto', validators=[Optional(), Length(max=100)])
    nip_krs = StringField('NIP/KRS', validators=[Optional(), Length(max=50)])


class FormularzPraktyki(FlaskForm):
    rok_uczelniany = StringField('Rok uczelniany', validators=[DataRequired(), Length(max=9)])
    semestr = SelectField('Semestr', choices=[
        ('zimowy', 'Zimowy'),
        ('letni',  'Letni'),
    ], validators=[DataRequired()])
    wymiar_godzin = StringField('Wymiar godzin (h)', validators=[DataRequired()])


# ── Pomocniki ─────────────────────────────────────────────────────────────────

def _utworz_studenta(imie, nazwisko, email, numer_albumu, plec=None, kierunek=None, specjalnosc=None, tryb_studiow=None):
    u = Uzytkownik(
        id                    = uuid.uuid4(),
        first_name            = imie.strip(),
        last_name             = nazwisko.strip(),
        email                 = email.lower().strip(),
        album_number          = numer_albumu.strip(),
        plec                  = plec or None,
        kierunek              = kierunek or None,
        specjalnosc           = specjalnosc or None,
        tryb_studiow          = tryb_studiow or None,
        role                  = RolaUzytkownika.STUDENT,
        password_hash         = generate_password_hash(numer_albumu.strip()),
        wymagana_zmiana_hasla = True,
        is_active             = True,
    )
    db.session.add(u)
    return u


# ── Użytkownicy ───────────────────────────────────────────────────────────────

@management_bp.route('/uzytkownicy')
@login_required
def lista_uzytkownikow():
    strona     = request.args.get('strona', 1, type=int)
    szukaj     = request.args.get('szukaj', '').strip()
    filtr_rola = request.args.get('rola', '').strip()

    q = db.session.query(Uzytkownik)
    if szukaj:
        q = q.filter(db.or_(
            Uzytkownik.first_name.ilike(f'%{szukaj}%'),
            Uzytkownik.last_name.ilike(f'%{szukaj}%'),
            Uzytkownik.email.ilike(f'%{szukaj}%'),
            Uzytkownik.album_number.ilike(f'%{szukaj}%'),
        ))
    if filtr_rola:
        try:
            q = q.filter_by(role=RolaUzytkownika[filtr_rola])
        except KeyError:
            pass

    uzytkownicy = q.order_by(Uzytkownik.last_name, Uzytkownik.first_name)\
                   .paginate(page=strona, per_page=25, error_out=False)
    csrf_form = FlaskForm()
    return render_template('management/uzytkownicy.html',
                           uzytkownicy=uzytkownicy,
                           csrf_form=csrf_form)


@management_bp.route('/uzytkownicy/nowy-student', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def nowy_student():
    form = FormularzStudenta()
    # populate UOPZ choices
    uopz_list = db.session.query(Uzytkownik).filter_by(role=RolaUzytkownika.UOPZ, is_active=True).order_by(Uzytkownik.last_name, Uzytkownik.first_name).all()
    form.uopz_id.choices = [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]
    if form.validate_on_submit():
        u = _utworz_studenta(
            form.imie.data, form.nazwisko.data,
            form.email.data, form.numer_albumu.data,
            plec=form.plec.data or None,
            kierunek=form.kierunek.data or None,
            specjalnosc=form.specjalnosc.data or None,
            tryb_studiow=form.tryb_studiow.data or None,
        )
        db.session.commit()
        flash(
            f'Konto studenta {u.first_name} {u.last_name} (nr alb. {u.album_number}) '
            f'zostało utworzone. Hasło tymczasowe: {u.album_number}',
            'success'
        )
        return redirect(url_for('management.lista_uzytkownikow'))
    return render_template('management/formularz_studenta.html', form=form, uzytkownik=None)


@management_bp.route('/uzytkownicy/<uuid:id>/edytuj-student', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def edytuj_studenta(id):
    u    = db.session.get(Uzytkownik, id) or abort(404)
    form = FormularzEdycjiStudenta(uzytkownik_id=id, obj=u)
    # populate UOPZ choices
    uopz_list = db.session.query(Uzytkownik).filter_by(role=RolaUzytkownika.UOPZ, is_active=True).order_by(Uzytkownik.last_name, Uzytkownik.first_name).all()
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
        return redirect(url_for('management.lista_uzytkownikow'))
    return render_template('management/formularz_studenta.html', form=form, uzytkownik=u)


@management_bp.route('/uzytkownicy/<uuid:id>/reset-hasla', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def reset_hasla(id):
    u = db.session.get(Uzytkownik, id) or abort(404)
    if u.role != RolaUzytkownika.STUDENT or not u.album_number:
        flash('Reset hasła dostępny tylko dla studentów z nr albumu.', 'danger')
        return redirect(url_for('management.lista_uzytkownikow'))
    u.password_hash         = generate_password_hash(u.album_number)
    u.wymagana_zmiana_hasla = True
    db.session.commit()
    flash(
        f'Hasło {u.first_name} {u.last_name} zresetowane do nr albumu ({u.album_number}).',
        'success'
    )
    return redirect(url_for('management.lista_uzytkownikow'))


@management_bp.route('/uzytkownicy/nowy-pracownik', methods=['GET', 'POST'])
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
        return redirect(url_for('management.lista_uzytkownikow'))
    return render_template('management/formularz_pracownika.html', form=form, uzytkownik=None)


@management_bp.route('/uzytkownicy/import-csv', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def import_csv():
    form   = FormularzImportuCSV()
    # populate UOPZ choices for template select
    uopz_list = db.session.query(Uzytkownik).filter_by(role=RolaUzytkownika.UOPZ, is_active=True).order_by(Uzytkownik.last_name, Uzytkownik.first_name).all()
    # attach a choices attribute so template can iterate over it
    form.uopz_id = type('X', (), {})()
    form.uopz_id.choices = [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]
    wyniki = None

    if form.validate_on_submit():
        plik      = form.plik.data
        zawartosc = plik.read().decode('utf-8-sig')
        czytnik   = csv.DictReader(io.StringIO(zawartosc))

        utworzono, pominieto, bledy = 0, 0, []

        for nr_wiersza, wiersz in enumerate(czytnik, start=2):
            try:
                imie         = (wiersz.get('imie') or wiersz.get('Imię') or '').strip()
                nazwisko     = (wiersz.get('nazwisko') or wiersz.get('Nazwisko') or '').strip()
                email        = (wiersz.get('email') or wiersz.get('Email') or '').strip().lower()
                nr_albumu    = (wiersz.get('numer_albumu') or wiersz.get('Nr albumu') or '').strip()
                plec         = (wiersz.get('plec') or wiersz.get('Płeć') or '').strip().upper() or None
                kierunek     = (wiersz.get('kierunek') or wiersz.get('Kierunek') or '').strip() or None
                specjalnosc  = (wiersz.get('specjalnosc') or wiersz.get('Specjalność') or '').strip() or None
                tryb_studiow = (wiersz.get('tryb_studiow') or wiersz.get('Tryb') or '').strip().lower() or None

                if not all([imie, nazwisko, email, nr_albumu]):
                    bledy.append(f'Wiersz {nr_wiersza}: brakujące dane (imie, nazwisko, email, numer_albumu)')
                    pominieto += 1
                    continue

                if db.session.query(Uzytkownik).filter(db.or_(
                    Uzytkownik.email == email,
                    Uzytkownik.album_number == nr_albumu
                )).first():
                    bledy.append(f'Wiersz {nr_wiersza}: {email} lub nr {nr_albumu} już istnieje')
                    pominieto += 1
                    continue

                _utworz_studenta(imie, nazwisko, email, nr_albumu,
                                 plec=plec, kierunek=kierunek,
                                 specjalnosc=specjalnosc, tryb_studiow=tryb_studiow)
                utworzono += 1

            except Exception as e:
                bledy.append(f'Wiersz {nr_wiersza}: {str(e)}')
                pominieto += 1

        db.session.commit()
        wyniki = {'utworzono': utworzono, 'pominieto': pominieto, 'bledy': bledy}
        if utworzono:
            flash(f'Import zakończony: {utworzono} kont utworzonych.', 'success')

    return render_template('management/import_csv.html', form=form, wyniki=wyniki)


@management_bp.route('/uzytkownicy/<uuid:id>/aktywnosc', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def przelacz_aktywnosc(id):
    u = db.session.get(Uzytkownik, id) or abort(404)
    if str(u.id) == str(current_user.id):
        flash('Nie możesz dezaktywować własnego konta.', 'danger')
        return redirect(url_for('management.lista_uzytkownikow'))
    u.is_active = not u.is_active
    db.session.commit()
    stan = 'aktywowane' if u.is_active else 'dezaktywowane'
    flash(f'Konto {u.first_name} {u.last_name} zostało {stan}.', 'success')
    return redirect(url_for('management.lista_uzytkownikow'))


@management_bp.route('/uzytkownicy/<uuid:id>/usun', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def usun_uzytkownika(id):
    u = db.session.get(Uzytkownik, id) or abort(404)
    if str(u.id) == str(current_user.id):
        flash('Nie możesz usunąć własnego konta.', 'danger')
        return redirect(url_for('management.lista_uzytkownikow'))
    imie_nazwisko = f'{u.first_name} {u.last_name}'
    db.session.delete(u)
    db.session.commit()
    flash(f'Konto {imie_nazwisko} zostało trwale usunięte.', 'success')
    return redirect(url_for('management.lista_uzytkownikow'))


# ── Praktyki ──────────────────────────────────────────────────────────────────

@management_bp.route('/praktyki')
@login_required
def lista_praktyk():
    strona = request.args.get('strona', 1, type=int)

    praktyki = db.session.query(Praktyka)\
                 .order_by(Praktyka.rok_uczelniany.desc(), Praktyka.semestr)\
                 .paginate(page=strona, per_page=25, error_out=False)

    csrf_form = FlaskForm()
    return render_template('management/praktyki.html',
                           praktyki=praktyki,
                           csrf_form=csrf_form)


@management_bp.route('/praktyki/nowa', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def nowa_praktyka():
    form = FormularzPraktyki()
    if form.validate_on_submit():
        rok = (form.rok_uczelniany.data or '').strip()
        try:
            wymiar = int(form.wymiar_godzin.data)
        except Exception:
            flash('Wymiar godzin musi być liczbą całkowitą.', 'danger')
            return render_template('management/formularz_praktyki.html', form=form)

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
        return redirect(url_for('management.lista_praktyk'))
    return render_template('management/formularz_praktyki.html', form=form)


@management_bp.route('/praktyki/<uuid:id>/aktywnosc', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def przelacz_aktywnosc_praktyki(id):
    p = db.session.get(Praktyka, id) or abort(404)
    p.status = StatusPraktyki.INACTIVE if p.status == StatusPraktyki.ACTIVE else StatusPraktyki.ACTIVE
    db.session.commit()
    stan = 'aktywowana' if p.status == StatusPraktyki.ACTIVE else 'dezaktywowana'
    flash(f'Praktyka {p.rok_uczelniany} ({p.semestr}) została {stan}.', 'success')
    return redirect(url_for('management.lista_praktyk'))


# ── Zgłoszenia studentów (enrollments) ───────────────────────────────────────
class FormularzPrzypiszUOPZ(FlaskForm):
    uopz_id = SelectField('Opiekun uczelniany (UOPZ)', choices=[], validators=[Optional()])


@management_bp.route('/zgloszenia')
@wymaga_roli(RolaUzytkownika.ADMIN)
def lista_zgloszen():
    strona = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()

    q = db.session.query(ZapisPraktyki).join(Uzytkownik, ZapisPraktyki.student_id == Uzytkownik.id)

    # Filtrowanie według statusu
    if status_filter:
        try:
            q = q.filter(ZapisPraktyki.status == StatusZapisu[status_filter])
        except KeyError:
            flash(f'Nieznany status: {status_filter}', 'warning')

    zgloszenia = q.order_by(ZapisPraktyki.enrolled_at.desc()).paginate(page=strona, per_page=25, error_out=False)
    csrf_form = FlaskForm()
    return render_template('management/enrollments/list.html', zgloszenia=zgloszenia, csrf_form=csrf_form)


@management_bp.route('/zgloszenia/<uuid:id>/przypisz-uopz', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def przypisz_uopz(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    form = FormularzPrzypiszUOPZ()
    uopz_list = db.session.query(Uzytkownik).filter_by(role=RolaUzytkownika.UOPZ, is_active=True).order_by(Uzytkownik.last_name, Uzytkownik.first_name).all()
    form.uopz_id.choices = [('', '--- brak ---')] + [(str(u.id), f"{u.first_name} {u.last_name}") for u in uopz_list]

    if form.validate_on_submit():
        if form.uopz_id.data:
            zapis.uopz_id = form.uopz_id.data
            zapis.status = StatusZapisu.AWAITING_APPROVAL
            db.session.commit()
            flash('Opiekun UOPZ przypisany, zgłoszenie przekazane do zatwierdzenia.', 'success')
        else:
            flash('Nie wybrano opiekuna.', 'warning')
        return redirect(url_for('management.lista_zgloszen'))

    if request.method == 'GET':
        form.uopz_id.data = str(zapis.uopz_id) if zapis.uopz_id else ''

    return render_template('management/enrollments/przypisz_uopz.html', form=form, zapis=zapis)


@management_bp.route('/zgloszenia/<uuid:id>/szczegoly', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def szczegoly_zgloszenia(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)

    # UOPZ może widzieć tylko swoje przypisane zgłoszenia
    if current_user.role == RolaUzytkownika.UOPZ and zapis.uopz_id != current_user.id:
        abort(403)

    # Pobierz harmonogram praktyki
    harmonogram = db.session.query(HarmonogramPraktyki).filter_by(enrollment_id=id).all()
    harmonogram_dict = {h.learning_outcome_id: h for h in harmonogram}

    # Pobierz wszystkie efekty uczenia
    efekty = db.session.query(EfektUczenia).order_by(EfektUczenia.id).all()

    # Formularz komentarzy
    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SubmitField

    class FormularzKomentarza(FlaskForm):
        komentarz = TextAreaField('Komentarz do studenta')
        zatwierdz = SubmitField('Zatwierdź zgłoszenie')
        odrzuc = SubmitField('Wymagane poprawki')

    form = FormularzKomentarza()

    if form.validate_on_submit():
        # Zapisz komentarz
        if current_user.role == RolaUzytkownika.ADMIN:
            zapis.admin_comments = form.komentarz.data
        else:  # UOPZ
            zapis.uopz_comments = form.komentarz.data

        # Zmień status na podstawie akcji
        if form.zatwierdz.data:
            zapis.status = StatusZapisu.IN_PROGRESS
            flash('Zgłoszenie zostało zatwierdzone!', 'success')
        elif form.odrzuc.data:
            zapis.status = StatusZapisu.PENDING
            zapis.student_notified_at = db.func.now()
            flash('Wysłano prośbę o poprawki do studenta.', 'info')

        db.session.commit()

        if current_user.role == RolaUzytkownika.ADMIN:
            return redirect(url_for('management.lista_zgloszen'))
        else:
            return redirect(url_for('management.moje_zgloszenia'))

    # Uploadowane dokumenty studenta
    uploaded_docs = db.session.query(UploadedDocument)\
        .filter_by(enrollment_id=id)\
        .order_by(UploadedDocument.uploaded_at.desc())\
        .all()

    return render_template('management/enrollments/szczegoly.html',
                         zapis=zapis,
                         harmonogram_dict=harmonogram_dict,
                         efekty=efekty,
                         form=form,
                         uploaded_docs=uploaded_docs)


@management_bp.route('/zgloszenia/<uuid:id>/zatwierdz-zaklad', methods=['POST'])
@wymaga_roli(RolaUzytkownika.UOPZ, RolaUzytkownika.ADMIN)
def zatwierdz_zaklad(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    # jeśli istnieje powiązany zakład, oznacz go jako zatwierdzony
    if zapis.zaklad:
        try:
            zapis.zaklad.zatwierdzone = True
        except Exception:
            pass
    zapis.status = StatusZapisu.IN_PROGRESS
    db.session.commit()
    flash('Zakład zatwierdzony. Praktyka rozpoczęła się.', 'success')
    return redirect(url_for('management.lista_zgloszen'))


@management_bp.route('/zgloszenia/<uuid:id>/potwierdz', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def potwierdz_zapis(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    zapis.status = StatusZapisu.IN_PROGRESS
    if current_user.role == RolaUzytkownika.UOPZ:
        zapis.uopz_id = current_user.id
    db.session.commit()
    flash(f'Zapis studenta na praktykę został potwierdzony. Zostałeś/aś przypisany/a jako opiekun.', 'success')
    return redirect(request.referrer or url_for('dashboard.index'))


@management_bp.route('/moje-zgloszenia')
@wymaga_roli(RolaUzytkownika.UOPZ)
def moje_zgloszenia():
    """Lista zgłoszeń przypisanych do aktualnego UOPZ"""
    from app_admin.routes.evaluation import get_pilne_oceny

    strona = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()

    # Podstawowe zapytanie - wszystkie zgłoszenia przypisane do UOPZ
    q = db.session.query(ZapisPraktyki).filter(ZapisPraktyki.uopz_id == current_user.id)

    # Filtrowanie według statusu
    if status_filter:
        try:
            q = q.filter(ZapisPraktyki.status == StatusZapisu[status_filter])
        except KeyError:
            flash(f'Nieznany status: {status_filter}', 'warning')

    # Liczniki dla filtrów
    base_query = db.session.query(ZapisPraktyki).filter(ZapisPraktyki.uopz_id == current_user.id)
    liczniki = {
        'wszystkie': base_query.count(),
        'oczekujace': base_query.filter(ZapisPraktyki.status == StatusZapisu.AWAITING_APPROVAL).count(),
        'zatwierdzone': base_query.filter(ZapisPraktyki.status == StatusZapisu.IN_PROGRESS).count(),
    }

    # Pilne oceny
    pilne_oceny = get_pilne_oceny(current_user.id)

    zgloszenia = q.order_by(ZapisPraktyki.enrolled_at.desc()).paginate(page=strona, per_page=25, error_out=False)
    csrf_form = FlaskForm()
    return render_template('management/enrollments/moje_lista.html',
                         zgloszenia=zgloszenia,
                         liczniki=liczniki,
                         pilne_oceny=pilne_oceny,
                         csrf_form=csrf_form)


@management_bp.route('/praktyki/<uuid:id>/usun', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def usun_praktyke(id):
    p = db.session.get(Praktyka, id) or abort(404)
    opis = f'{p.rok_uczelniany} ({p.semestr})'
    db.session.delete(p)
    db.session.commit()
    flash(f'Praktyka {opis} została usunięta.', 'success')
    return redirect(url_for('management.lista_praktyk'))


# ── Zakłady (proste placeholdery, wcześniej brakowało endpointów używanych w szablonach)
class _EmptyPagination:
    def __init__(self):
        self.items = []
        self.page = 1
        self.pages = 1
    def iter_pages(self):
        return [1]


@management_bp.route('/zaklady')
@login_required
def lista_zakladow():
    szukaj = request.args.get('szukaj', '').strip()
    # Jeśli w przyszłości pojawi się model Zaklad, zastąpić implementację poniżej
    zaklady = _EmptyPagination()
    csrf_form = FlaskForm()
    return render_template('management/zaklady.html', zaklady=zaklady, csrf_form=csrf_form)


@management_bp.route('/zaklady/nowy', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def nowy_zaklad():
    flash('Funkcja dodawania zakładu jeszcze niezaimplementowana.', 'warning')
    return redirect(url_for('management.lista_zakladow'))


@management_bp.route('/zaklady/<uuid:id>/edytuj', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def edytuj_zaklad(id):
    flash('Edycja zakładu jeszcze niezaimplementowana.', 'warning')
    return redirect(url_for('management.lista_zakladow'))


# ── Komisja weryfikująca ścieżki B/C ──────────────────────────────────────────

@management_bp.route('/komisja')
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def komisja_lista():
    """Lista wniosków do weryfikacji przez komisję"""
    strona = request.args.get('page', 1, type=int)

    # Wnioski wymagające weryfikacji komisji
    q = db.session.query(ZapisPraktyki)\
          .join(Uzytkownik, ZapisPraktyki.student_id == Uzytkownik.id)\
          .filter(ZapisPraktyki.status == StatusZapisu.COMMISSION_REVIEW)\
          .filter(ZapisPraktyki.track_type.in_(['EMPLOYMENT', 'OWN_BUSINESS']))

    wnioski = q.order_by(ZapisPraktyki.enrolled_at.desc())\
               .paginate(page=strona, per_page=25, error_out=False)

    csrf_form = FlaskForm()
    return render_template('management/komisja/lista.html', wnioski=wnioski, csrf_form=csrf_form)


@management_bp.route('/komisja/<uuid:id>/weryfikuj', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def komisja_weryfikuj(id):
    """Weryfikacja wniosku przez komisję"""
    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SelectField, SubmitField
    from wtforms.validators import DataRequired, Optional

    zapis = db.session.get(ZapisPraktyki, id) or abort(404)

    if zapis.status != StatusZapisu.COMMISSION_REVIEW:
        flash('Wniosek nie wymaga weryfikacji komisji.', 'warning')
        return redirect(url_for('management.komisja_lista'))

    class FormularzKomisji(FlaskForm):
        decyzja = SelectField('Decyzja komisji', choices=[
            ('APPROVED', 'Zatwierdzam - kieruję do dziekana'),
            ('PARTIALLY_APPROVED', 'Zatwierdzam częściowo - wymaga uzupełnień'),
            ('REJECTED', 'Odrzucam wniosek')
        ], validators=[DataRequired()])
        komentarz = TextAreaField('Komentarz komisji', validators=[Optional()])
        submit = SubmitField('Zapisz decyzję')

    form = FormularzKomisji()

    if form.validate_on_submit():
        zapis.komisja_decision = form.decyzja.data
        zapis.komisja_comments = form.komentarz.data
        zapis.komisja_decision_at = db.func.current_timestamp()

        # Zmień status w zależności od decyzji
        if form.decyzja.data == 'APPROVED':
            zapis.status = StatusZapisu.DEAN_APPROVAL
            flash('Wniosek zatwierdzony i przekazany do dziekana.', 'success')
        elif form.decyzja.data == 'PARTIALLY_APPROVED':
            zapis.status = StatusZapisu.AWAITING_APPROVAL  # Wraca do studenta
            zapis.uopz_comments = f"Komisja: {form.komentarz.data}"  # Dodaj komentarz dla studenta
            flash('Wniosek wymaga uzupełnień - student zostanie powiadomiony.', 'info')
        else:  # REJECTED
            zapis.status = StatusZapisu.REJECTED
            zapis.uopz_comments = f"Wniosek odrzucony przez komisję: {form.komentarz.data}"
            flash('Wniosek został odrzucony.', 'warning')

        db.session.commit()
        return redirect(url_for('management.komisja_lista'))

    # Załaduj uploadowane dokumenty
    dokumenty = db.session.query(UploadedDocument)\
                  .filter_by(enrollment_id=id)\
                  .order_by(UploadedDocument.uploaded_at.desc())\
                  .all()

    return render_template('management/komisja/weryfikuj.html',
                         form=form, zapis=zapis, dokumenty=dokumenty)


@management_bp.route('/dziekan')
@wymaga_roli(RolaUzytkownika.ADMIN)
def dziekan_lista():
    """Lista wniosków czekających na decyzję dziekana"""
    strona = request.args.get('page', 1, type=int)

    # Wnioski zatwierdzone przez komisję, oczekujące na dziekana
    q = db.session.query(ZapisPraktyki)\
          .join(Uzytkownik, ZapisPraktyki.student_id == Uzytkownik.id)\
          .filter(ZapisPraktyki.status == StatusZapisu.DEAN_APPROVAL)\
          .filter(ZapisPraktyki.track_type.in_(['EMPLOYMENT', 'OWN_BUSINESS']))

    wnioski = q.order_by(ZapisPraktyki.enrolled_at.desc())\
               .paginate(page=strona, per_page=25, error_out=False)

    csrf_form = FlaskForm()
    return render_template('management/dziekan/lista.html', wnioski=wnioski, csrf_form=csrf_form)


@management_bp.route('/dziekan/<uuid:id>/decyzja', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def dziekan_decyzja(id):
    """Decyzja dziekana w sprawie wniosku"""
    from flask_wtf import FlaskForm
    from wtforms import TextAreaField, SelectField, SubmitField
    from wtforms.validators import DataRequired, Optional

    zapis = db.session.get(ZapisPraktyki, id) or abort(404)

    if zapis.status != StatusZapisu.DEAN_APPROVAL:
        flash('Wniosek nie wymaga decyzji dziekana.', 'warning')
        return redirect(url_for('management.dziekan_lista'))

    class FormularzDziekana(FlaskForm):
        decyzja = SelectField('Decyzja dziekana', choices=[
            ('APPROVED', 'Wyrażam zgodę na zaliczenie praktyki'),
            ('REJECTED', 'Nie wyrażam zgody na zaliczenie')
        ], validators=[DataRequired()])
        komentarz = TextAreaField('Komentarz dziekana', validators=[Optional()])
        submit = SubmitField('Zapisz decyzję')

    form = FormularzDziekana()

    if form.validate_on_submit():
        zapis.dean_decision = form.decyzja.data
        zapis.dean_comments = form.komentarz.data
        zapis.dean_decision_at = db.func.current_timestamp()

        # Zmień status w zależności od decyzji
        if form.decyzja.data == 'APPROVED':
            zapis.status = StatusZapisu.IN_PROGRESS
            flash('Wniosek zatwierdzony przez dziekana. Student może kontynuować praktykę.', 'success')
        else:  # REJECTED
            zapis.status = StatusZapisu.REJECTED
            zapis.uopz_comments = f"Dziekan nie wyraził zgody: {form.komentarz.data}"
            flash('Wniosek odrzucony przez dziekana.', 'warning')

        db.session.commit()
        return redirect(url_for('management.dziekan_lista'))

    return render_template('management/dziekan/decyzja.html', form=form, zapis=zapis)


# ── ZARZĄDZANIE FIRMAMI ──────────────────────────────────────────────────────

@management_bp.route('/firmy')
@wymaga_roli(RolaUzytkownika.ADMIN)
def lista_firm():
    """Lista firm w systemie"""
    strona = request.args.get('page', 1, type=int)
    szukaj = request.args.get('szukaj', '').strip()
    status = request.args.get('status', 'wszystkie')

    q = db.session.query(Firma)

    # Filtr statusu
    if status == 'aktywne':
        q = q.filter_by(is_active=True)
    elif status == 'nieaktywne':
        q = q.filter_by(is_active=False)
    # 'wszystkie' - bez filtra

    # Wyszukiwanie
    if szukaj:
        q = q.filter(
            db.or_(
                Firma.nazwa.ilike(f'%{szukaj}%'),
                Firma.adres.ilike(f'%{szukaj}%'),
                Firma.miasto.ilike(f'%{szukaj}%'),
                Firma.nip_krs.ilike(f'%{szukaj}%')
            )
        )

    firmy = q.order_by(Firma.nazwa).paginate(page=strona, per_page=25, error_out=False)

    csrf_form = FlaskForm()
    return render_template('management/firmy/lista.html', firmy=firmy, csrf_form=csrf_form)


@management_bp.route('/firmy/dodaj', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def dodaj_firme():
    """Dodawanie nowej firmy"""
    form = FormularzFirmy()

    if form.validate_on_submit():
        # Sprawdź czy aktywna firma o tej nazwie już istnieje
        istniejaca = db.session.query(Firma).filter_by(nazwa=form.nazwa.data.strip(), is_active=True).first()
        if istniejaca:
            flash('Firma o tej nazwie już istnieje w systemie.', 'error')
            return render_template('management/firmy/formularz.html', form=form, tryb='dodaj')

        # Sprawdź czy firma o tym NIP/KRS już istnieje (jeśli podano)
        if form.nip_krs.data and form.nip_krs.data.strip():
            istniejaca_nip = db.session.query(Firma).filter_by(nip_krs=form.nip_krs.data.strip(), is_active=True).first()
            if istniejaca_nip:
                flash(f'Firma z numerem NIP/KRS "{form.nip_krs.data.strip()}" już istnieje w systemie ({istniejaca_nip.nazwa}).', 'error')
                return render_template('management/firmy/formularz.html', form=form, tryb='dodaj')

        firma = Firma(
            id=uuid.uuid4(),
            nazwa=form.nazwa.data.strip(),
            adres=form.adres.data.strip() if form.adres.data else None,
            miasto=form.miasto.data.strip() if form.miasto.data else None,
            nip_krs=form.nip_krs.data.strip() if form.nip_krs.data else None
        )

        db.session.add(firma)
        db.session.commit()

        flash('Firma została dodana do systemu.', 'success')
        return redirect(url_for('management.lista_firm'))

    return render_template('management/firmy/formularz.html', form=form, tryb='dodaj')


@management_bp.route('/firmy/<uuid:id>/edytuj', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def edytuj_firme(id):
    """Edycja danych firmy"""
    firma = db.session.get(Firma, id) or abort(404)

    form = FormularzFirmy(obj=firma)


    if form.validate_on_submit():
        # Sprawdź czy inna aktywna firma o tej nazwie już istnieje
        istniejaca = db.session.query(Firma)\
            .filter(Firma.nazwa == form.nazwa.data.strip())\
            .filter(Firma.id != firma.id)\
            .filter(Firma.is_active == True)\
            .first()

        if istniejaca:
            flash('Firma o tej nazwie już istnieje w systemie.', 'error')
            return render_template('management/firmy/formularz.html',
                                 form=form, tryb='edytuj', firma=firma)

        # Sprawdź czy inna firma o tym NIP/KRS już istnieje (jeśli podano)
        if form.nip_krs.data and form.nip_krs.data.strip():
            istniejaca_nip = db.session.query(Firma)\
                .filter(Firma.nip_krs == form.nip_krs.data.strip())\
                .filter(Firma.id != firma.id)\
                .filter(Firma.is_active == True)\
                .first()
            if istniejaca_nip:
                flash(f'Firma z numerem NIP/KRS "{form.nip_krs.data.strip()}" już istnieje w systemie ({istniejaca_nip.nazwa}).', 'error')
                return render_template('management/firmy/formularz.html',
                                     form=form, tryb='edytuj', firma=firma)

        firma.nazwa = form.nazwa.data.strip()
        firma.adres = form.adres.data.strip() if form.adres.data else None
        firma.miasto = form.miasto.data.strip() if form.miasto.data else None
        firma.nip_krs = form.nip_krs.data.strip() if form.nip_krs.data else None

        db.session.commit()

        flash('Dane firmy zostały zaktualizowane.', 'success')
        return redirect(url_for('management.lista_firm'))

    return render_template('management/firmy/formularz.html',
                         form=form, tryb='edytuj', firma=firma)


@management_bp.route('/firmy/<uuid:id>/usun', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def usun_firme(id):
    """Trwałe usunięcie firmy"""
    firma = db.session.get(Firma, id) or abort(404)

    # Sprawdź czy firma ma jakiekolwiek praktyki
    wszystkie_praktyki = db.session.query(ZapisPraktyki)\
        .filter_by(firma_id=firma.id)\
        .count()

    if wszystkie_praktyki > 0:
        flash(f'Nie można usunąć firmy - ma {wszystkie_praktyki} praktyk w historii.', 'error')
        return redirect(url_for('management.lista_firm'))

    nazwa_firmy = firma.nazwa
    db.session.delete(firma)
    db.session.commit()
    flash(f'Firma "{nazwa_firmy}" została trwale usunięta z systemu.', 'success')
    return redirect(url_for('management.lista_firm'))


@management_bp.route('/firmy/<uuid:id>/przelacz-aktywnosc', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def przelacz_aktywnosc_firmy(id):
    """Przełącz status aktywności firmy"""
    firma = db.session.get(Firma, id) or abort(404)

    if firma.is_active:
        # Sprawdź czy firma ma aktywne praktyki przed dezaktywacją
        aktywne_praktyki = db.session.query(ZapisPraktyki)\
            .filter_by(firma_id=firma.id)\
            .filter(ZapisPraktyki.status.in_([
                StatusZapisu.AWAITING_APPROVAL,
                StatusZapisu.IN_PROGRESS,
                StatusZapisu.COMMISSION_REVIEW,
                StatusZapisu.DEAN_APPROVAL
            ])).count()

        if aktywne_praktyki > 0:
            flash(f'Nie można dezaktywować firmy - ma {aktywne_praktyki} aktywnych praktyk.', 'error')
            return redirect(url_for('management.lista_firm'))

        firma.is_active = False
        flash('Firma została dezaktywowana - nie będzie widoczna dla studentów.', 'success')
    else:
        firma.is_active = True
        flash('Firma została aktywowana - będzie widoczna dla studentów.', 'success')

    db.session.commit()
    return redirect(url_for('management.lista_firm'))
