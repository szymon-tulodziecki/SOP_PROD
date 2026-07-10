# core/error_handlers.py
"""
Centralizowana obsługa błędów HTTP dla całej aplikacji.
Rejestruje handlery 403, 404, 500 z wspólnymi szablonami.
"""

from flask import render_template

from core.i18n import t

_TMPL_BLAD = "errors/blad.html"
_BTN_PULPIT = "Wróć do pulpitu"


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
        return (
            render_template(
                _TMPL_BLAD,
                kod="403",
                tytul=t("Brak dostępu"),
                opis=t("Nie masz uprawnień do wyświetlenia tej strony."),
                tekst_przycisku=t(_BTN_PULPIT),
            ),
            403,
        )

    @app.errorhandler(404)
    def blad_404(e):
        return (
            render_template(
                _TMPL_BLAD,
                kod="404",
                tytul=t("Nie znaleziono strony"),
                opis=t("Strona, której szukasz nie istnieje lub została przeniesiona."),
                tekst_przycisku=t(_BTN_PULPIT),
            ),
            404,
        )

    @app.errorhandler(500)
    def blad_500(e):
        app.logger.exception("Unhandled Exception:")
        return (
            render_template(
                _TMPL_BLAD,
                kod="500",
                tytul=t("Błąd serwera"),
                opis=t("Wystąpił nieoczekiwany błąd. Administratorzy zostali powiadomieni."),
                tekst_przycisku=t(_BTN_PULPIT),
            ),
            500,
        )
