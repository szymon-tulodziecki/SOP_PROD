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
                    RolaUzytkownika, StatusPraktyki, StatusZapisu)
from app_admin.extensions import db
from app_admin.routes.auth import wymaga_roli

management_bp = Blueprint('management', __name__)


# ── Formularze ────────────────────────────────────────────────────────────────

class FormularzStudenta(FlaskForm):
    imie         = StringField('Imię',      validators=[DataRequired(), Length(max=100)])
    nazwisko     = StringField('Nazwisko',  validators=[DataRequired(), Length(max=100)])
    email        = StringField('E-mail',    validators=[DataRequired(), Email(), Length(max=255)])
    numer_albumu = StringField('Nr albumu', validators=[DataRequired(), Length(max=20)])
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


class FormularzPraktyki(FlaskForm):
    rok_uczelniany = StringField('Rok uczelniany', validators=[DataRequired(), Length(max=9)])
    semestr = SelectField('Semestr', choices=[
        ('zimowy', 'Zimowy'),
        ('letni',  'Letni'),
    ], validators=[DataRequired()])
    wymiar_godzin = StringField('Wymiar godzin (h)', validators=[DataRequired()])


# ── Pomocniki ─────────────────────────────────────────────────────────────────

def _utworz_studenta(imie, nazwisko, email, numer_albumu):
    u = Uzytkownik(
        id                    = uuid.uuid4(),
        first_name            = imie.strip(),
        last_name             = nazwisko.strip(),
        email                 = email.lower().strip(),
        album_number          = numer_albumu.strip(),
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
                imie      = (wiersz.get('imie') or wiersz.get('Imię') or '').strip()
                nazwisko  = (wiersz.get('nazwisko') or wiersz.get('Nazwisko') or '').strip()
                email     = (wiersz.get('email') or wiersz.get('Email') or '').strip().lower()
                nr_albumu = (wiersz.get('numer_albumu') or wiersz.get('Nr albumu') or '').strip()

                if not all([imie, nazwisko, email, nr_albumu]):
                    bledy.append(f'Wiersz {nr_wiersza}: brakujące dane')
                    pominieto += 1
                    continue

                if db.session.query(Uzytkownik).filter(db.or_(
                    Uzytkownik.email == email,
                    Uzytkownik.album_number == nr_albumu
                )).first():
                    bledy.append(f'Wiersz {nr_wiersza}: {email} lub nr {nr_albumu} już istnieje')
                    pominieto += 1
                    continue

                _utworz_studenta(imie, nazwisko, email, nr_albumu)
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
            q = q.filter_by(status=StatusZapisu[status_filter])
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

    return render_template('management/enrollments/szczegoly.html',
                         zapis=zapis,
                         harmonogram_dict=harmonogram_dict,
                         efekty=efekty,
                         form=form)


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
            q = q.filter_by(status=StatusZapisu[status_filter])
        except KeyError:
            flash(f'Nieznany status: {status_filter}', 'warning')

    # Liczniki dla filtrów
    base_query = db.session.query(ZapisPraktyki).filter(ZapisPraktyki.uopz_id == current_user.id)
    liczniki = {
        'wszystkie': base_query.count(),
        'oczekujace': base_query.filter_by(status=StatusZapisu.AWAITING_APPROVAL).count(),
        'zatwierdzone': base_query.filter_by(status=StatusZapisu.IN_PROGRESS).count(),
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
