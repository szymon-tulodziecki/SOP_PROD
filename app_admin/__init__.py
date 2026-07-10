import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
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
    # Za nginxem z prefiksem (/praktyki-admin/) — bez ProxyFix url_for buduje złe linki
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # ── Core static assets (CSS design system + templates) ──────
    core_bp = _Blueprint(
        "core_static",
        __name__,
        static_folder=str(_Path(__file__).parent.parent / "core" / "static"),
        static_url_path="/core/static",
        template_folder=str(_Path(__file__).parent.parent / "core" / "templates"),
    )
    app.register_blueprint(core_bp)

    app.jinja_options = app.jinja_options.copy()
    app.jinja_options.update({"autoescape": select_autoescape(["html", "xml"])})

    # Configure file-based logging so exceptions are captured when console is silent
    logs_dir = Path(app.root_path) / "logs"
    try:
        logs_dir.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(logs_dir / "app.log", maxBytes=1000000, backupCount=5)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
        )
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
    except OSError as exc:
        # Logs directory may be read-only in containerized environments;
        # fall back to stderr-only logging.
        logging.getLogger(__name__).warning("Cannot configure file logging: %s", exc)

    from app_admin.config import CONFIGURATION_MAP

    env = os.environ.get("FLASK_ENV", "development")
    app.config.from_object(CONFIGURATION_MAP.get(env, CONFIGURATION_MAP["default"]))

    @app.route("/health", methods=["GET"])
    def health():
        return {"status": "ok"}, 200

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.session_protection = "strong"
    csrf.init_app(app)
    limiter.init_app(app)
    register_error_handlers(app)
    from core.security import configure_security_headers

    configure_security_headers(app)
    from core.i18n import register_i18n

    register_i18n(app)

    login_manager.login_view = "auth.logowanie"
    from core.i18n import t

    login_manager.login_message = "Zaloguj się, aby uzyskać dostęp do tej strony."
    login_manager.localize_callback = t
    login_manager.login_message_category = "warning"
    with app.app_context():
        from core.auth import create_auth_blueprint
        from core.files import create_files_blueprint
        from core.models import UserRole
        from app_admin.routes.dashboard import dashboard_bp
        from app_admin.routes.management import zarzadzanie_bp
        from app_admin.routes.evaluation import evaluation_bp
        from app_admin.routes.journal import journal_bp
        from app_admin.routes.logs import logi_bp
        from app_admin.routes.dziekanat import dziekanat_bp

        auth_bp = create_auth_blueprint(
            allowed_roles=[
                UserRole.ADMIN,
                UserRole.UOPZ,
                UserRole.KOMISJA,
                UserRole.DYREKTOR,
                UserRole.DZIEKANAT,
            ],
            login_template="auth/logowanie.html",
        )
        uploads_bp = create_files_blueprint()

        app.register_blueprint(auth_bp)
        app.register_blueprint(dashboard_bp, url_prefix="/panel")
        app.register_blueprint(zarzadzanie_bp, url_prefix="/zarzadzanie")
        app.register_blueprint(evaluation_bp, url_prefix="/assessments")
        app.register_blueprint(journal_bp, url_prefix="/dzienniki")
        app.register_blueprint(uploads_bp, url_prefix="/uploads")
        app.register_blueprint(logi_bp, url_prefix="/logi")
        app.register_blueprint(dziekanat_bp, url_prefix="/porozumienia")

    @app.context_processor
    def inject_nav_counts():
        counts = {}
        try:
            from flask_login import current_user

            if current_user.is_authenticated:
                from core.repositories import EnrollmentRepository
                from core.models import UserRole

                supervisor_id = current_user.id if current_user.role == UserRole.UOPZ else None
                counts.update(EnrollmentRepository().liczniki_nav(supervisor_id=supervisor_id))
        except Exception as exc:
            app.logger.warning("inject_nav_counts error: %s", exc)
        return counts

    @app.context_processor
    def inject_now():
        from datetime import datetime

        return {"now": datetime.utcnow}

    @app.context_processor
    def inject_tlumacz():
        from core.translations import translate_status
        from core.presenters import flash_icon

        return {
            "translate_status": translate_status,
            "ikona_komunikatu": flash_icon,
        }

    @app.context_processor
    def inject_rola_sidebar():
        from flask_login import current_user
        from core.presenters import sidebar_role_label

        if current_user.is_authenticated:
            return {"rola_sidebar": sidebar_role_label(current_user)}
        return {"rola_sidebar": ""}

    return app


@login_manager.user_loader
def load_user(user_id):
    from core.models import User

    return db.session.get(User, user_id)
