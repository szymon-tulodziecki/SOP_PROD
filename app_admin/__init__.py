import os

from flask import Flask, render_template
from jinja2 import select_autoescape
from core.extensions import db, login_manager
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def create_app():
    from pathlib import Path as _Path
    from flask import Blueprint as _Blueprint
    app = Flask(__name__)

    # ── Core static assets (CSS design system + templates) ──────
    core_bp = _Blueprint(
        'core_static', __name__,
        static_folder=str(_Path(__file__).parent.parent / 'core' / 'static'),
        static_url_path='/core/static',
        template_folder=str(_Path(__file__).parent.parent / 'core' / 'templates'),
    )
    app.register_blueprint(core_bp)

    app.jinja_options = app.jinja_options.copy()
    app.jinja_options.update(dict(
        autoescape=select_autoescape(['html', 'xml'])
    ))

    # Configure file-based logging so exceptions are captured when console is silent
    logs_dir = Path(app.root_path) / 'logs'
    try:
        logs_dir.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(logs_dir / 'app.log', maxBytes=1000000, backupCount=5)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
    except Exception:
        pass

    from app_admin.config import config_dict
    env = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config_dict.get(env, config_dict['default']))

    db.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = 'auth.logowanie'
    # Polish translation for Flask-Login unauthorized message
    login_manager.login_message = 'Zaloguj się, aby uzyskać dostęp do tej strony.'
    login_manager.login_message_category = 'warning'
    with app.app_context():
        from core.auth  import stworz_blueprint_auth, wymaga_roli
        from core.pliki import stworz_blueprint_pliki
        from core.modele import RolaUzytkownika
        from app_admin.routes.pulpit      import dashboard_bp
        from app_admin.routes.zarzadzanie import zarzadzanie_bp
        from app_admin.routes.ocenianie   import evaluation_bp
        from app_admin.routes.dziennik    import journal_bp
        from app_admin.routes.dokumenty   import documents_bp

        auth_bp    = stworz_blueprint_auth(
            dozwolone_role=[RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ],
            template_logowania='auth/logowanie.html',
            template_zmiany_hasla='auth/zmien_haslo.html',
        )
        uploads_bp = stworz_blueprint_pliki()

        app.register_blueprint(auth_bp)
        app.register_blueprint(dashboard_bp,  url_prefix='/panel')
        app.register_blueprint(zarzadzanie_bp, url_prefix='/zarzadzanie')
        app.register_blueprint(evaluation_bp, url_prefix='/oceny')
        app.register_blueprint(journal_bp,    url_prefix='/dzienniki')
        app.register_blueprint(documents_bp,  url_prefix='/dokumenty')
        app.register_blueprint(uploads_bp,    url_prefix='/uploads')

    @app.context_processor
    def inject_nav_counts():
        counts = {}
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                from core.modele import ZapisPraktyki, StatusZapisu
                counts['nav_oczekujace'] = db.session.query(ZapisPraktyki).filter(
                    ZapisPraktyki.status == StatusZapisu.AWAITING_APPROVAL
                ).count()
                counts['nav_komisja'] = db.session.query(ZapisPraktyki).filter(
                    ZapisPraktyki.status == StatusZapisu.COMMISSION_REVIEW
                ).count()
                counts['nav_dziekan'] = db.session.query(ZapisPraktyki).filter(
                    ZapisPraktyki.status == StatusZapisu.DEAN_APPROVAL
                ).count()
        except Exception:
            pass
        return counts

    @app.context_processor
    def inject_tlumacz():
        return dict(tlumacz_status=lambda val: {
            'PENDING': 'Oczekuje',
            'IN_PROGRESS': 'W trakcie',
            'COMPLETED': 'Zakończona',
            'ACTIVE': 'Aktywna',
            'INACTIVE': 'Nieaktywna',
            'AWAITING_APPROVAL': 'Oczekuje na akceptację',
            'COMMISSION_REVIEW': 'Weryfikacja komisji',
            'DEAN_APPROVAL': 'Oczekuje na dziekana',
            'REJECTED': 'Odrzucony'
        }.get(val, val))

    @app.before_request
    def sprawdz_zmiane_hasla():
        from flask import request, redirect, url_for
        from flask_login import current_user
        if (current_user.is_authenticated
                and getattr(current_user, 'wymagana_zmiana_hasla', False)
                and request.endpoint not in ('auth.zmien_haslo', 'auth.wylogowanie', 'static')):
            return redirect(url_for('auth.zmien_haslo'))

    @app.errorhandler(403)
    def blad_403(e):
        return render_template('errors/blad.html',
            kod='403', tytul='Brak dostępu',
            opis='Nie masz uprawnień do wyświetlenia tej strony.',
            tekst_przycisku='Wróć do pulpitu'), 403

    @app.errorhandler(404)
    def blad_404(e):
        return render_template('errors/blad.html',
            kod='404', tytul='Nie znaleziono strony',
            opis='Strona, której szukasz nie istnieje lub została przeniesiona.',
            tekst_przycisku='Wróć do pulpitu'), 404

    @app.errorhandler(500)
    def blad_500(e):
        app.logger.exception('Unhandled Exception:')
        return render_template('errors/blad.html',
            kod='500', tytul='Błąd serwera',
            opis='Wystąpił nieoczekiwany błąd. Administratorzy zostali powiadomieni.',
            tekst_przycisku='Wróć do pulpitu'), 500

    return app

@login_manager.user_loader
def wczytaj_uzytkownika(user_id):
    from core.modele import Uzytkownik
    return db.session.get(Uzytkownik, user_id)