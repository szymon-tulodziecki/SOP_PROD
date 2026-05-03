"""
core/autoryzacja.py

Authentication and authorization module for Microsoft Entra ID
(OAuth 2.0 / OpenID Connect).

Usage:
    from core.auth import create_auth_blueprint
    app.register_blueprint(create_auth_blueprint(
        allowed_roles=[UserRole.STUDENT],
        login_template='auth/logowanie.html',
    ))
"""
import secrets
from functools import wraps

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.exc import SQLAlchemyError

from core.extensions import limiter
from core.repositories import UserRepository

user_repository = UserRepository()

_ROUTE_LOGIN = 'auth.logowanie'
_ROUTE_DASHBOARD = 'dashboard.index'
_MS_SCOPES = ['User.Read']
_OAUTH_COOKIE_MAX_AGE = 600


def _oauth_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt='oauth-state')


def _oauth_cookie_name(suffix: str) -> str:
    session_cookie = current_app.config.get('SESSION_COOKIE_NAME', 'session')
    return f'{session_cookie}_oauth_{suffix}'


def _set_oauth_cookie(response, suffix: str, value: str) -> None:
    response.set_cookie(
        _oauth_cookie_name(suffix),
        _oauth_serializer().dumps(value),
        max_age=_OAUTH_COOKIE_MAX_AGE,
        secure=current_app.config.get('SESSION_COOKIE_SECURE', False),
        httponly=True,
        samesite='Lax',
    )


def _read_oauth_cookie(suffix: str) -> str | None:
    raw = request.cookies.get(_oauth_cookie_name(suffix))
    if not raw:
        return None
    try:
        return _oauth_serializer().loads(raw, max_age=_OAUTH_COOKIE_MAX_AGE)
    except BadSignature:
        return None


def _clear_oauth_cookies(response) -> None:
    for suffix in ('state', 'next'):
        response.delete_cookie(_oauth_cookie_name(suffix))


def _redirect_clearing_oauth(location: str):
    response = make_response(redirect(location))
    _clear_oauth_cookies(response)
    return response


def roles_required(*allowed_roles):
    """Require the current user to have one of the allowed roles."""
    def decorator(func):
        @wraps(func)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in allowed_roles:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def _msal_app():
    """Build the MSAL ConfidentialClientApplication instance."""
    import msal

    return msal.ConfidentialClientApplication(
        client_id=current_app.config['AZURE_CLIENT_ID'],
        client_credential=current_app.config['AZURE_CLIENT_SECRET'],
        authority=(
            f"https://login.microsoftonline.com/"
            f"{current_app.config['AZURE_TENANT_ID']}"
        ),
    )


def _acquire_token(code: str) -> dict | None:
    """Exchange an OAuth authorization code for tokens."""
    try:
        return _msal_app().acquire_token_by_authorization_code(
            code=code,
            scopes=_MS_SCOPES,
            redirect_uri=url_for('auth.ms_callback', _external=True),
        )
    except Exception:
        current_app.logger.exception('OAuth token exchange failed')
        return None


def _resolve_user(ms_email: str, allowed_roles):
    """Return (user, error_message); exactly one element is None."""
    try:
        user = user_repository.find_by_email(ms_email)
    except SQLAlchemyError:
        current_app.logger.exception('Database error during Microsoft login')
        return None, 'BĹ‚Ä…d poĹ‚Ä…czenia z bazÄ… danych.'

    if not user or not user.is_active:
        current_app.logger.info('Unknown Microsoft account login attempt: %s', ms_email)
        return None, (
            'Twoje konto Microsoft nie jest zarejestrowane w systemie. '
            'Skontaktuj siÄ™ z administratorem.'
        )

    if allowed_roles and user.role not in allowed_roles:
        return None, 'Twoje konto nie ma dostÄ™pu do tego panelu.'

    return user, None


def _ms_callback_handler(allowed_roles):
    """Handle the Microsoft OAuth callback."""
    expected_state = session.pop('oauth_state', None) or _read_oauth_cookie('state')
    if not expected_state or request.args.get('state') != expected_state:
        current_app.logger.warning('OAuth state mismatch; possible CSRF attack')
        flash('BĹ‚Ä…d bezpieczeĹ„stwa logowania. SprĂłbuj ponownie.', 'danger')
        return _redirect_clearing_oauth(url_for(_ROUTE_LOGIN))

    if 'error' in request.args:
        error_desc = request.args.get('error_description', request.args['error'])
        current_app.logger.warning('Microsoft OAuth error: %s', error_desc)
        flash('Logowanie przez Microsoft nie powiodĹ‚o siÄ™.', 'danger')
        return _redirect_clearing_oauth(url_for(_ROUTE_LOGIN))

    code = request.args.get('code')
    if not code:
        flash('Brak kodu autoryzacyjnego od Microsoft.', 'danger')
        return _redirect_clearing_oauth(url_for(_ROUTE_LOGIN))

    result = _acquire_token(code)
    if result is None:
        flash('BĹ‚Ä…d komunikacji z Microsoft. SprĂłbuj ponownie.', 'danger')
        return _redirect_clearing_oauth(url_for(_ROUTE_LOGIN))

    if 'error' in result:
        current_app.logger.warning(
            'Token error: %s - %s',
            result.get('error'),
            result.get('error_description'),
        )
        flash('Nie udaĹ‚o siÄ™ uzyskaÄ‡ tokenu od Microsoft.', 'danger')
        return _redirect_clearing_oauth(url_for(_ROUTE_LOGIN))

    ms_email = (result.get('id_token_claims', {}).get('preferred_username') or '').lower().strip()
    if not ms_email:
        flash('Nie udaĹ‚o siÄ™ odczytaÄ‡ adresu e-mail z konta Microsoft.', 'danger')
        return _redirect_clearing_oauth(url_for(_ROUTE_LOGIN))

    user, err = _resolve_user(ms_email, allowed_roles)
    if err:
        flash(err, 'danger')
        return _redirect_clearing_oauth(url_for(_ROUTE_LOGIN))

    next_page = session.pop('oauth_next', None) or _read_oauth_cookie('next')
    session.clear()
    login_user(user, remember=False)
    current_app.logger.info('Microsoft login succeeded: %s (role: %s)', ms_email, user.role)
    target = next_page if next_page and next_page.startswith('/') else url_for(_ROUTE_DASHBOARD)
    return _redirect_clearing_oauth(target)


def create_auth_blueprint(
    allowed_roles: list | None = None,
    login_template: str = 'auth/logowanie.html',
) -> Blueprint:
    auth_bp = Blueprint('auth', __name__)

    @auth_bp.route('/', methods=['GET'])
    @auth_bp.route('/logowanie', methods=['GET'])
    def logowanie():
        if current_user.is_authenticated:
            return redirect(url_for(_ROUTE_DASHBOARD))
        return render_template(login_template)

    @auth_bp.route('/ms-login', methods=['GET'])
    @limiter.limit("20 per minute")
    def ms_login():
        if current_user.is_authenticated:
            return redirect(url_for(_ROUTE_DASHBOARD))

        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        next_page = request.args.get('next', '')
        if next_page.startswith('/'):
            session['oauth_next'] = next_page

        try:
            auth_url = _msal_app().get_authorization_request_url(
                scopes=_MS_SCOPES,
                state=state,
                redirect_uri=url_for('auth.ms_callback', _external=True),
            )
        except Exception:
            current_app.logger.exception('Failed to build Microsoft authorization URL')
            flash('BĹ‚Ä…d konfiguracji logowania. Skontaktuj siÄ™ z administratorem.', 'danger')
            return redirect(url_for(_ROUTE_LOGIN))

        response = make_response(redirect(auth_url))
        _set_oauth_cookie(response, 'state', state)
        if next_page.startswith('/'):
            _set_oauth_cookie(response, 'next', next_page)
        return response

    @auth_bp.route('/ms-callback', methods=['GET'])
    @limiter.limit("20 per minute")
    def ms_callback():
        return _ms_callback_handler(allowed_roles)

    @auth_bp.route('/wylogowanie', methods=['GET', 'POST'])
    @login_required
    def wylogowanie():
        logout_user()
        session.clear()
        tenant = current_app.config.get('AZURE_TENANT_ID', 'common')
        post_logout = url_for('auth.logowanie', _external=True)
        ms_logout_url = (
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/logout"
            f"?post_logout_redirect_uri={post_logout}"
        )
        return redirect(ms_logout_url)

    return auth_bp
