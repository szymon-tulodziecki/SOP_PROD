import os

from flask import Flask
from jinja2 import select_autoescape
from core.extensions import db, login_manager, csrf, limiter
from core.error_handlers import register_error_handlers
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
    csrf.init_app(app)
    limiter.init_app(app)
    register_error_handlers(app)

    login_manager.login_view = 'auth.logowanie'
    # Polish translation for Flask-Login unauthorized message
    login_manager.login_message = 'Zaloguj się, aby uzyskać dostęp do tej strony.'
    login_manager.login_message_category = 'warning'
    with app.app_context():
        from core.autoryzacja  import stworz_blueprint_auth, wymaga_roli
        from core.pliki import stworz_blueprint_pliki
        from core.modele import UserRole
        from app_admin.routes.pulpit      import dashboard_bp
        from app_admin.routes.zarzadzanie import zarzadzanie_bp
        from app_admin.routes.ocenianie   import evaluation_bp
        from app_admin.routes.dziennik    import journal_bp
        from app_admin.routes.dokumenty   import documents_bp
        from app_admin.routes.logi        import logi_bp

        auth_bp    = stworz_blueprint_auth(
            dozwolone_role=[UserRole.ADMIN, UserRole.UOPZ, UserRole.KOMISJA, UserRole.DYREKTOR],
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
        app.register_blueprint(logi_bp,       url_prefix='/logi')

    @app.context_processor
    def inject_nav_counts():
        counts = {}
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                from core.repozytoria import EnrollmentRepository
                from core.modele import UserRole
                uopz_id = current_user.id if current_user.role == UserRole.UOPZ else None
                counts.update(EnrollmentRepository().liczniki_nav(supervisor_id=uopz_id))
        except Exception as exc:
            app.logger.warning("inject_nav_counts error: %s", exc)
        return counts

    @app.context_processor
    def inject_now():
        from datetime import datetime
        return dict(now=datetime.utcnow)

    @app.context_processor
    def inject_tlumacz():
        from core.tlumaczenia import tlumacz_status
        return dict(tlumacz_status=tlumacz_status)


    return app

@login_manager.user_loader
def wczytaj_uzytkownika(user_id):
    from core.modele import User
    return db.session.get(User, user_id)