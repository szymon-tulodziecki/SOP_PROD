import logging
import os

from flask import Flask
from jinja2 import select_autoescape
from sqlalchemy.exc import SQLAlchemyError

from core.extensions import db, login_manager, csrf, limiter
from core.error_handlers import register_error_handlers
from app_student.config import CONFIGURATION_MAP


def _check_enrollment_requires_action(enrollments) -> bool:
    from core.models import EnrollmentStatus
    for z in enrollments:
        s = z.status
        if s == EnrollmentStatus.PENDING and (z.admin_comments or z.supervisor_comments):
            return True
        if s in (EnrollmentStatus.REVISION_REQUIRED, EnrollmentStatus.REJECTED):
            return True
    return False


def _build_enrollment_context() -> dict:
    from flask_login import current_user
    from core.models import EnrollmentStatus
    from core.repositories import EnrollmentRepository
    info = {'is_active': False, 'path_type': None, 'status': None}
    requires_attention = False
    try:
        if current_user.is_authenticated:
            _repo = EnrollmentRepository()
            z = _repo.aktywny_dla_studenta(current_user.id, [
                EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMPLETED,
                EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.DIRECTOR_APPROVAL,
                EnrollmentStatus.AWAITING_APPROVAL, EnrollmentStatus.REVISION_REQUIRED,
            ])
            if z:
                info = {
                    'is_active': True,
                    'path_type': z.track_type.value if z.track_type else 'STANDARD',
                    'status': z.status.value,
                }
            zapisy_do_sprawdzenia = _repo.aktywne_dla_studenta(current_user.id, [
                EnrollmentStatus.PENDING,
                EnrollmentStatus.AWAITING_APPROVAL,
                EnrollmentStatus.REVISION_REQUIRED,
                EnrollmentStatus.REJECTED,
            ])
            requires_attention = _check_enrollment_requires_action(zapisy_do_sprawdzenia)
    except SQLAlchemyError as exc:
        logging.getLogger(__name__).warning("inject_enrollment_context error: %s", exc)
    return {
        'active_enrollment_info': info,
        'nav_requires_attention': requires_attention,
    }


def create_app():
    from pathlib import Path as _Path
    from flask import Blueprint as _Blueprint, Response
    app = Flask(__name__)

    # Core static assets (CSS design system + templates)
    core_bp = _Blueprint(
        'core_static', __name__,
        static_folder=str(_Path(__file__).parent.parent / 'core' / 'static'),
        static_url_path='/core/static',
        template_folder=str(_Path(__file__).parent.parent / 'core' / 'templates'),
    )
    app.register_blueprint(core_bp)
    app.jinja_options = app.jinja_options.copy()
    app.jinja_options.update({
        'autoescape': select_autoescape(['html', 'xml'])
    })
    env = os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(CONFIGURATION_MAP.get(env, CONFIGURATION_MAP['default']))

    @app.route('/health', methods=['GET'])
    def health():
        return {'status': 'ok'}, 200

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.session_protection = 'strong'
    csrf.init_app(app)
    limiter.init_app(app)
    register_error_handlers(app)
    from core.security import configure_security_headers
    configure_security_headers(app)

    @app.route('/assets/student.css', endpoint='student_css_bundle', methods=['GET'])
    def student_css_bundle():
        css_root = _Path(__file__).parent.parent / 'core' / 'static' / 'css' / 'modul'
        local_css = _Path(__file__).parent / 'static' / 'css' / 'student.css'
        modules = [
            'zmienne.css',
            'komunikaty.css',
            'formularze.css',
            'logowanie.css',
            'uklad.css',
            'karty.css',
            'tabele.css',
            'przyciski.css',
            'statusy.css',
            'komponenty.css',
            'dashboard.css',
            'utils.css',
        ]
        parts = []
        for module_name in modules:
            parts.append((css_root / module_name).read_text(encoding='utf-8'))
        parts.append(local_css.read_text(encoding='utf-8'))

        from flask import request as _req
        import gzip as _gzip
        raw = '\n'.join(parts).encode('utf-8')
        if 'gzip' in _req.headers.get('Accept-Encoding', ''):
            body = _gzip.compress(raw, compresslevel=6)
            response = Response(body, mimetype='text/css')
            response.headers['Content-Encoding'] = 'gzip'
        else:
            response = Response(raw, mimetype='text/css')
        response.cache_control.public = True
        response.cache_control.max_age = 31536000
        response.cache_control.immutable = True
        return response

    @app.after_request
    def cache_static_assets(response):
        from flask import request

        if request.path.startswith(('/static/', '/core/static/', '/assets/')):
            response.cache_control.public = True
            response.cache_control.max_age = 31536000
            response.cache_control.immutable = True
            response.cache_control.no_cache = None
            response.cache_control.no_store = None
        return response

    login_manager.login_view = 'auth.logowanie'
    login_manager.login_message = 'Zaloguj się, aby uzyskać dostęp.'

    with app.app_context():
        from core.auth  import create_auth_blueprint
        from core.files import create_files_blueprint
        from core.models import UserRole
        from app_student.routes.dashboard   import dashboard_bp
        from app_student.routes.internships import internships_bp
        from app_student.routes.logbook     import logbook_bp
        from app_student.routes.reports     import reports_bp
        from app_student.routes.documents   import documents_bp

        auth_bp    = create_auth_blueprint(
            allowed_roles=[UserRole.STUDENT],
            login_template='auth/logowanie.html',
        )
        uploads_bp = create_files_blueprint()

        app.register_blueprint(auth_bp)
        app.register_blueprint(dashboard_bp,  url_prefix='/panel')
        app.register_blueprint(internships_bp, url_prefix='/praktyki')
        app.register_blueprint(logbook_bp,     url_prefix='/dziennik')
        app.register_blueprint(reports_bp,     url_prefix='/report')
        app.register_blueprint(documents_bp,  url_prefix='/dokumenty')
        app.register_blueprint(uploads_bp,    url_prefix='/uploads')

    # Kontekst globalny: informacje o aktywnym zapisie studenta
    app.context_processor(_build_enrollment_context)

    # Dodaj funkcje pomocnicze do szablonów
    @app.template_global()
    def translate_status(status_value):
        from core.translations import translate_status as core_translate_status
        return core_translate_status(status_value)

    @app.before_request
    def validate_student_role():
        from flask import request, redirect, url_for, abort
        from flask_login import current_user
        from core.models import UserRole

        if not current_user.is_authenticated:
            return

        if getattr(current_user.role, 'value', current_user.role) != 'STUDENT':
            abort(403)

    return app


@login_manager.user_loader
def load_user(user_id):
    from core.models import User
    return db.session.get(User, user_id)
