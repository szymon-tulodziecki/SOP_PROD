from flask import Flask, render_template
from app_student.extensions import db, login_manager
from app_student.config import config_dict


def create_app():
    app = Flask(__name__)
    env = __import__('os').environ.get('FLASK_ENV', 'development')
    app.config.from_object(config_dict.get(env, config_dict['default']))

    db.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = 'auth.logowanie'
    login_manager.login_message = 'Zaloguj się, aby uzyskać dostęp.'

    with app.app_context():
        from app_student.routes.auth import auth_bp
        from app_student.routes.dashboard import dashboard_bp
        from app_student.routes.praktyki import praktyki_bp
        from app_student.routes.dziennik import dziennik_bp
        from app_student.routes.sprawozdania import sprawozdania_bp
        from app_student.routes.documents import documents_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(dashboard_bp, url_prefix='/panel')
        app.register_blueprint(praktyki_bp,  url_prefix='/praktyki')
        app.register_blueprint(dziennik_bp,  url_prefix='/dziennik')
        app.register_blueprint(sprawozdania_bp, url_prefix='/sprawozdanie')
        app.register_blueprint(documents_bp, url_prefix='/dokumenty')

    @app.before_request
    def sprawdz_studenta():
        from flask import request, redirect, url_for, abort
        from flask_login import current_user
        from app_student.models import RolaUzytkownika

        if not current_user.is_authenticated:
            return

        if getattr(current_user.role, 'value', current_user.role) != 'STUDENT':
            abort(403)

        if (getattr(current_user, 'wymagana_zmiana_hasla', False)
                and request.endpoint not in ('auth.zmien_haslo', 'auth.wylogowanie', 'static')):
            return redirect(url_for('auth.zmien_haslo'))

    @app.errorhandler(403)
    def blad_403(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def blad_404(e):
        return render_template('errors/404.html'), 404

    return app


@login_manager.user_loader
def wczytaj_uzytkownika(user_id):
    from app_student.models import Uzytkownik
    return db.session.get(Uzytkownik, user_id)
