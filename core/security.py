_SELF = "'self'"

CONTENT_SECURITY_POLICY = {
    'default-src': [_SELF],
    'style-src': [_SELF],
    'script-src': [_SELF],
    'img-src': [_SELF, 'data:'],
    'font-src': [_SELF],
}


def configure_security_headers(app) -> None:
    try:
        from flask_talisman import Talisman
    except ImportError:
        app.after_request(_set_fallback_security_headers)
        return

    Talisman(
        app,
        content_security_policy=CONTENT_SECURITY_POLICY,
        force_https=app.config.get('SESSION_COOKIE_SECURE', False),
        session_cookie_secure=app.config.get('SESSION_COOKIE_SECURE', False),
        session_cookie_http_only=True,
        frame_options='DENY',
    )


def _set_fallback_security_headers(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "style-src 'self'; "
        "script-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self';"
    )
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    return response
