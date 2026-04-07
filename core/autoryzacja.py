"""
core/autoryzacja.py
Kanoniczny moduł autoryzacji — jeden dla całej platformy SOP.

Rejestracja w aplikacji:
    from core.autoryzacja import stworz_blueprint_auth
    app.register_blueprint(stworz_blueprint_auth(
        dozwolone_role=[RolaUzytkownika.STUDENT],
        template_logowania='auth/logowanie.html',
        template_zmiany_hasla='auth/zmien_haslo.html',
    ))

Jeśli dozwolone_role=None — brak filtrowania po roli (admin akceptuje
ADMIN i UOPZ, student akceptuje tylko STUDENT).
"""
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email, Length, EqualTo
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from core.modele import Uzytkownik, RolaUzytkownika
from core.extensions import db


# ── Formularze ────────────────────────────────────────────────────────────────

class FormularzLogowania(FlaskForm):
    email      = StringField('Adres e-mail', validators=[
        DataRequired('Podaj adres e-mail.'),
        Email('Podaj poprawny adres e-mail.'),
        Length(max=255),
    ])
    haslo      = PasswordField('Hasło', validators=[
        DataRequired('Podaj hasło.'),
        Length(min=1, max=128),
    ])
    zapamietaj = BooleanField('Zapamiętaj mnie')


class FormularzZmianyHasla(FlaskForm):
    nowe_haslo    = PasswordField('Nowe hasło', validators=[
        DataRequired(), Length(min=8, max=128),
    ])
    potwierdzenie = PasswordField('Powtórz hasło', validators=[
        DataRequired(),
        EqualTo('nowe_haslo', message='Hasła muszą być identyczne.'),
    ])


# ── Dekorator RBAC — używany przez oba podmodele ─────────────────────────────

def wymaga_roli(*dozwolone_role):
    """Sprawdza czy zalogowany użytkownik ma jedną z podanych ról."""
    def dekorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in dozwolone_role:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return dekorator


# ── Fabryka blueprintu ────────────────────────────────────────────────────────

def stworz_blueprint_auth(
    dozwolone_role: list | None = None,
    template_logowania: str     = 'auth/logowanie.html',
    template_zmiany_hasla: str  = 'auth/zmien_haslo.html',
) -> Blueprint:
    """
    Tworzy blueprint 'auth' skonfigurowany dla danego kontekstu.

    dozwolone_role  — lista RolaUzytkownika dopuszczonych do logowania;
                      None = akceptuj wszystkie aktywne konta.
    """
    auth_bp = Blueprint('auth', __name__)

    @auth_bp.route('/', methods=['GET'])
    @auth_bp.route('/logowanie', methods=['GET', 'POST'])
    def logowanie():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))

        form = FormularzLogowania()

        if form.validate_on_submit():
            email = form.email.data.lower().strip()
            try:
                uzytkownik = db.session.query(Uzytkownik).filter_by(email=email).first()
            except (OperationalError, SQLAlchemyError):
                current_app.logger.exception('Błąd połączenia z bazą podczas logowania')
                flash('Błąd połączenia z bazą danych. Spróbuj ponownie później.', 'danger')
                return render_template(template_logowania, form=form)

            if uzytkownik and uzytkownik.is_active and \
               check_password_hash(uzytkownik.password_hash, form.haslo.data):

                # Weryfikacja roli
                if dozwolone_role and uzytkownik.role not in dozwolone_role:
                    flash('Twoje konto nie ma dostępu do tego panelu.', 'danger')
                    return render_template(template_logowania, form=form)

                login_user(uzytkownik, remember=form.zapamietaj.data)
                next_page = request.args.get('next')
                return redirect(
                    next_page if next_page and next_page.startswith('/') else url_for('dashboard.index')
                )

            flash('Nieprawidłowy adres e-mail lub hasło.', 'danger')

        return render_template(template_logowania, form=form)

    @auth_bp.route('/wylogowanie', methods=['GET', 'POST'])
    @login_required
    def wylogowanie():
        logout_user()
        flash('Wylogowano pomyślnie.', 'success')
        return redirect(url_for('auth.logowanie'))

    @auth_bp.route('/zmien-haslo', methods=['GET', 'POST'])
    @login_required
    def zmien_haslo():
        form = FormularzZmianyHasla()
        if form.validate_on_submit():
            current_user.password_hash         = generate_password_hash(form.nowe_haslo.data)
            current_user.wymagana_zmiana_hasla = False
            db.session.commit()
            flash('Hasło zostało zmienione. Możesz korzystać z systemu.', 'success')
            return redirect(url_for('dashboard.index'))
        return render_template(template_zmiany_hasla, form=form)

    return auth_bp
