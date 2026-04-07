# core/error_handlers.py
"""
Centralizowana obsługa błędów HTTP dla całej aplikacji.
Rejestruje handlery 403, 404, 500 z wspólnymi szablonami.
"""

from flask import render_template


def register_error_handlers(app):
    """
    Rejestruje wszystkie error handlery dla aplikacji.
    
    Użycie:
        from core.error_handlers import register_error_handlers
        app = Flask(__name__)
        register_error_handlers(app)
    """
    
    @app.errorhandler(403)
    def blad_403(e):
        return render_template('errors/blad.html',
            kod='403', 
            tytul='Brak dostępu',
            opis='Nie masz uprawnień do wyświetlenia tej strony.',
            tekst_przycisku='Wróć do pulpitu'), 403

    @app.errorhandler(404)
    def blad_404(e):
        return render_template('errors/blad.html',
            kod='404', 
            tytul='Nie znaleziono strony',
            opis='Strona, której szukasz nie istnieje lub została przeniesiona.',
            tekst_przycisku='Wróć do pulpitu'), 404

    @app.errorhandler(500)
    def blad_500(e):
        app.logger.exception('Unhandled Exception:')
        return render_template('errors/blad.html',
            kod='500', 
            tytul='Błąd serwera',
            opis='Wystąpił nieoczekiwany błąd. Administratorzy zostali powiadomieni.',
            tekst_przycisku='Wróć do pulpitu'), 500
