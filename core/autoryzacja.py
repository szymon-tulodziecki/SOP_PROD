"""
core/autoryzacja.py
Kanoniczny moduł autoryzacji — Microsoft Entra ID (OAuth 2.0 / OIDC).

Rejestracja w aplikacji:
    from core.autoryzacja import stworz_blueprint_auth
    app.register_blueprint(stworz_blueprint_auth(
        dozwolone_role=[RolaUzytkownika.STUDENT],
        template_logowania='auth/logowanie.html',
        template_zmiany_hasla='auth/zmien_haslo.html',
    ))
"""
import os
import secrets
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, abort, current_app, session)
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import PasswordField
from wtforms.validators import DataRequired, Length, EqualTo
from sqlalchemy.exc import SQLAlchemyError

from core.modele import User, UserRole
from core.extensions import db, limiter
from core.repozytoria import UserRepository

_repo_uzytk = UserRepository()

_ROUTE_LOGIN     = 'auth.logowanie'
_ROUTE_DASHBOARD = 'dashboard.index'


# ── Formularz zmiany hasła (zachowany dla kont technicznych) ─────────────────

class FormularzZmianyHasla(FlaskForm):
    nowe_haslo    = PasswordField('Nowe hasło', validators=[
        DataRequired(), Length(min=8, max=128),
    ])
    potwierdzenie = PasswordField('Powtórz hasło', validators=[
        DataRequired(),
        EqualTo('nowe_haslo', message='Hasła muszą być identyczne.'),
    ])


# ── Dekorator RBAC ────────────────────────────────────────────────────────────

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


# ── Pomocnicze — MSAL ─────────────────────────────────────────────────────────

def _msal_app():
    """Buduje instancję MSAL ConfidentialClientApplication."""
    import msal
    return msal.ConfidentialClientApplication(
        client_id     = current_app.config['AZURE_CLIENT_ID'],
        client_credential = current_app.config['AZURE_CLIENT_SECRET'],
        authority     = (
            f"https://login.microsoftonline.com/"
            f"{current_app.config['AZURE_TENANT_ID']}"
        ),
    )


_MS_SCOPES = ['User.Read']


# ── Pomocnicze — callback Microsoft ──────────────────────────────────────────

def _acquire_token(code: str) -> dict | None:
    """Wymienia kod OAuth na token; zwraca None przy błędzie komunikacji."""
    try:
        result = _msal_app().acquire_token_by_authorization_code(
            code         = code,
            scopes       = _MS_SCOPES,
            redirect_uri = url_for('auth.ms_callback', _external=True),
        )
        return result
    except Exception:
        current_app.logger.exception('Błąd wymiany kodu OAuth na token')
        return None


def _resolve_user(ms_email: str, dozwolone_role):
    """Zwraca krotkę (user, error_msg) — dokładnie jedno z nich jest None."""
    try:
        uzytkownik = _repo_uzytk.znajdz_po_emailu(ms_email)
    except SQLAlchemyError:
        current_app.logger.exception('Błąd bazy danych podczas logowania MS')
        return None, 'Błąd połączenia z bazą danych.'

    if not uzytkownik or not uzytkownik.is_active:
        current_app.logger.info('Próba logowania nieznanego konta MS: %s', ms_email)
        return None, (
            'Twoje konto Microsoft nie jest zarejestrowane w systemie. '
            'Skontaktuj się z administratorem.'
        )

    if dozwolone_role and uzytkownik.role not in dozwolone_role:
        return None, 'Twoje konto nie ma dostępu do tego panelu.'

    return uzytkownik, None


def _ms_callback_handler(dozwolone_role):
    """Shared logic for the /ms-callback route — extracted to reduce nesting."""
    expected_state = session.pop('oauth_state', None)
    if not expected_state or request.args.get('state') != expected_state:
        current_app.logger.warning('OAuth state mismatch — możliwy atak CSRF')
        flash('Błąd bezpieczeństwa logowania. Spróbuj ponownie.', 'danger')
        return redirect(url_for(_ROUTE_LOGIN))

    if 'error' in request.args:
        error_desc = request.args.get('error_description', request.args['error'])
        current_app.logger.warning('Microsoft OAuth error: %s', error_desc)
        flash('Logowanie przez Microsoft nie powiodło się.', 'danger')
        return redirect(url_for(_ROUTE_LOGIN))

    code = request.args.get('code')
    if not code:
        flash('Brak kodu autoryzacyjnego od Microsoft.', 'danger')
        return redirect(url_for(_ROUTE_LOGIN))

    result = _acquire_token(code)
    if result is None:
        flash('Błąd komunikacji z Microsoft. Spróbuj ponownie.', 'danger')
        return redirect(url_for(_ROUTE_LOGIN))

    if 'error' in result:
        current_app.logger.warning('Token error: %s — %s',
                                   result.get('error'), result.get('error_description'))
        flash('Nie udało się uzyskać tokenu od Microsoft.', 'danger')
        return redirect(url_for(_ROUTE_LOGIN))

    ms_email = (result.get('id_token_claims', {}).get('preferred_username') or '').lower().strip()
    if not ms_email:
        flash('Nie udało się odczytać adresu e-mail z konta Microsoft.', 'danger')
        return redirect(url_for(_ROUTE_LOGIN))

    uzytkownik, err = _resolve_user(ms_email, dozwolone_role)
    if err:
        flash(err, 'danger')
        return redirect(url_for(_ROUTE_LOGIN))

    login_user(uzytkownik, remember=False)
    current_app.logger.info('Zalogowano przez Microsoft: %s (rola: %s)', ms_email, uzytkownik.role)
    next_page = session.pop('oauth_next', None)
    return redirect(next_page if next_page and next_page.startswith('/') else url_for(_ROUTE_DASHBOARD))


# ── Fabryka blueprintu ────────────────────────────────────────────────────────

def stworz_blueprint_auth(
    dozwolone_role: list | None = None,
    template_logowania: str     = 'auth/logowanie.html',
    template_zmiany_hasla: str  = 'auth/zmien_haslo.html',
) -> Blueprint:
    auth_bp = Blueprint('auth', __name__)

    # ── Strona logowania — wyświetla przycisk "Zaloguj przez Microsoft" ───────

    @auth_bp.route('/', methods=['GET'])
    @auth_bp.route('/logowanie', methods=['GET'])
    def logowanie():
        if current_user.is_authenticated:
            return redirect(url_for(_ROUTE_DASHBOARD))
        return render_template(template_logowania)

    # ── Krok 1: przekieruj do Microsoft ──────────────────────────────────────

    @auth_bp.route('/ms-login', methods=['GET'])
    @limiter.limit("20 per minute")
    def ms_login():
        if current_user.is_authenticated:
            return redirect(url_for(_ROUTE_DASHBOARD))

        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        # zachowaj next po zalogowaniu
        next_page = request.args.get('next', '')
        if next_page.startswith('/'):
            session['oauth_next'] = next_page

        try:
            auth_url = _msal_app().get_authorization_request_url(
                scopes       = _MS_SCOPES,
                state        = state,
                redirect_uri = url_for('auth.ms_callback', _external=True),
            )
        except Exception:
            current_app.logger.exception('Błąd budowania URL autoryzacji Microsoft')
            flash('Błąd konfiguracji logowania. Skontaktuj się z administratorem.', 'danger')
            return redirect(url_for(_ROUTE_LOGIN))

        return redirect(auth_url)

    # ── Krok 2: callback z Microsoft ─────────────────────────────────────────

    @auth_bp.route('/ms-callback', methods=['GET'])
    @limiter.limit("20 per minute")
    def ms_callback():
        return _ms_callback_handler(dozwolone_role)

    # ── Wylogowanie ───────────────────────────────────────────────────────────

    @auth_bp.route('/wylogowanie', methods=['GET', 'POST'])
    @login_required
    def wylogowanie():
        logout_user()
        session.clear()
        # Wylogowanie globalne z Microsoft (single sign-out)
        tenant = current_app.config.get('AZURE_TENANT_ID', 'common')
        post_logout = url_for('auth.logowanie', _external=True)
        ms_logout_url = (
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/logout"
            f"?post_logout_redirect_uri={post_logout}"
        )
        return redirect(ms_logout_url)

    # ── Zmiana hasła (dla kont technicznych / awaryjnych) ────────────────────

    @auth_bp.route('/zmien-haslo', methods=['GET', 'POST'])
    @login_required
    def zmien_haslo():
        from werkzeug.security import generate_password_hash
        form = FormularzZmianyHasla()
        if form.validate_on_submit():
            current_user.password_hash          = generate_password_hash(form.nowe_haslo.data)
            current_user.require_password_change = False
            db.session.commit()
            flash('Hasło zostało zmienione.', 'success')
            return redirect(url_for(_ROUTE_DASHBOARD))
        return render_template(template_zmiany_hasla, form=form)

    return auth_bp
