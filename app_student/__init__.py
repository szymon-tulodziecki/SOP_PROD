from flask import Flask, render_template
from jinja2 import select_autoescape
from core.extensions import db, login_manager
from app_student.config import config_dict


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
    env = __import__('os').environ.get('FLASK_ENV', 'development')
    app.config.from_object(config_dict.get(env, config_dict['default']))

    db.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = 'auth.logowanie'
    login_manager.login_message = 'Zaloguj się, aby uzyskać dostęp.'

    with app.app_context():
        from core.auth  import stworz_blueprint_auth
        from core.pliki import stworz_blueprint_pliki
        from core.modele import RolaUzytkownika
        from app_student.routes.pulpit       import dashboard_bp
        from app_student.routes.praktyki     import praktyki_bp
        from app_student.routes.dziennik     import dziennik_bp
        from app_student.routes.sprawozdania import sprawozdania_bp
        from app_student.routes.dokumenty    import documents_bp

        auth_bp    = stworz_blueprint_auth(
            dozwolone_role=[RolaUzytkownika.STUDENT],
            template_logowania='auth/logowanie.html',
            template_zmiany_hasla='auth/zmien_haslo.html',
        )
        uploads_bp = stworz_blueprint_pliki()

        app.register_blueprint(auth_bp)
        app.register_blueprint(dashboard_bp,  url_prefix='/panel')
        app.register_blueprint(praktyki_bp,   url_prefix='/praktyki')
        app.register_blueprint(dziennik_bp,   url_prefix='/dziennik')
        app.register_blueprint(sprawozdania_bp, url_prefix='/sprawozdanie')
        app.register_blueprint(documents_bp,  url_prefix='/dokumenty')
        app.register_blueprint(uploads_bp,    url_prefix='/uploads')

    # Kontekst globalny: informacje o aktywnym zapisie studenta
    @app.context_processor
    def inject_aktywny_zapis():
        from flask_login import current_user
        from core.modele import ZapisPraktyki, StatusZapisu
        info = {'ma_aktywny': False, 'sciezka': None, 'status': None}
        try:
            if current_user.is_authenticated:
                z = db.session.query(ZapisPraktyki).filter(
                    ZapisPraktyki.student_id == current_user.id,
                    ZapisPraktyki.status.in_([
                        StatusZapisu.IN_PROGRESS, StatusZapisu.COMPLETED,
                        StatusZapisu.COMMISSION_REVIEW, StatusZapisu.DEAN_APPROVAL,
                        StatusZapisu.AWAITING_APPROVAL,
                    ])
                ).first()
                if z:
                    info = {
                        'ma_aktywny': True,
                        'sciezka': z.track_type.value if z.track_type else 'STANDARD',
                        'status': z.status.value,
                    }
        except Exception:
            pass
        wymaga_uwagi = False
        try:
            if current_user.is_authenticated:
                from core.modele import ZapisPraktyki, StatusZapisu
                z = db.session.query(ZapisPraktyki).filter(
                    ZapisPraktyki.student_id == current_user.id,
                    ZapisPraktyki.status == StatusZapisu.AWAITING_APPROVAL,
                    ZapisPraktyki.komentarze_uopz.isnot(None),
                    ZapisPraktyki.komentarze_uopz != '',
                ).first()
                if z:
                    wymaga_uwagi = True
        except Exception:
            pass
        return {'aktywny_zapis_info': info, 'nav_wymaga_uwagi': wymaga_uwagi}

    # Dodaj funkcje pomocnicze do szablonów
    @app.template_global()
    def tlumacz_status(status_value):
        translations = {
            'PENDING': 'Szkic',
            'AWAITING_APPROVAL': 'Oczekuje na zatwierdzenie',
            'COMMISSION_REVIEW': 'Weryfikacja komisji',
            'DEAN_APPROVAL': 'Oczekuje na dziekana',
            'IN_PROGRESS': 'W trakcie',
            'COMPLETED': 'Zakończona',
            'REJECTED': 'Odrzucony'
        }
        return translations.get(status_value, status_value)

    @app.before_request
    def sprawdz_studenta():
        from flask import request, redirect, url_for, abort
        from flask_login import current_user
        from core.modele import RolaUzytkownika

        if not current_user.is_authenticated:
            return

        if getattr(current_user.role, 'value', current_user.role) != 'STUDENT':
            abort(403)

        if (getattr(current_user, 'wymagana_zmiana_hasla', False)
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
        app.logger.exception('Unhandled Exception:') if hasattr(app, 'logger') else None
        return render_template('errors/blad.html',
            kod='500', tytul='Błąd serwera',
            opis='Wystąpił nieoczekiwany błąd. Administratorzy zostali powiadomieni.',
            tekst_przycisku='Wróć do pulpitu'), 500


@login_manager.user_loader
def wczytaj_uzytkownika(user_id):
    from core.modele import Uzytkownik
    return db.session.get(Uzytkownik, user_id)
