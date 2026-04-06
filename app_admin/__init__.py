import os

from flask import Flask, render_template
from jinja2 import select_autoescape
from core.extensions import db, login_manager
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def create_app():
    app = Flask(__name__)

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
        from app_admin.routes.auth       import auth_bp
        from app_admin.routes.dashboard  import dashboard_bp
        from app_admin.routes.management import management_bp
        from app_admin.routes.evaluation import evaluation_bp
        from app_admin.routes.journal    import journal_bp
        from app_admin.routes.documents  import documents_bp
        from app_admin.routes.uploads    import uploads_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(dashboard_bp,  url_prefix='/panel')
        app.register_blueprint(management_bp, url_prefix='/zarzadzanie')
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
                from core.models import ZapisPraktyki, StatusZapisu
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

    @app.errorhandler(404)
    def blad_404(e):
        return render_template('errors/404.html', kod='404'), 404


    @app.errorhandler(500)
    def blad_500(e):
        app.logger.exception('Unhandled Exception:')
        return render_template('errors/500.html', kod='500'), 500


    return app

@login_manager.user_loader
def wczytaj_uzytkownika(user_id):
    from core.models import Uzytkownik
    return db.session.get(Uzytkownik, user_id)