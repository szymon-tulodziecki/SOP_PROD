"""Lekka internacjonalizacja bez zależności zewnętrznych.

Kluczem tłumaczenia jest polski tekst źródłowy — brak wpisu w słowniku
oznacza fallback do polskiego. Język trzymany w session['lang'].

Użycie:
    from core.i18n import t, lazy_t
    t('Zapisz')                          # w widokach / prezenterach (request time)
    lazy_t('Adres e-mail')               # w definicjach formularzy WTForms (import time)
    {{ t('Zapisz') }}                    # w szablonach (wstrzyknięte przez register_i18n)
"""

from __future__ import annotations

from flask import has_request_context, redirect, request, session

from core.i18n.en import EN
from core.i18n.uk import UK

SUPPORTED_LANGS = ("pl", "en", "uk")
DEFAULT_LANG = "pl"

TRANSLATIONS = {"en": EN, "uk": UK}


def get_lang() -> str:
    if has_request_context():
        lang = session.get("lang")
        if lang in SUPPORTED_LANGS:
            return lang
    return DEFAULT_LANG


def t(text: str, **kwargs) -> str:
    """Tłumaczy polski tekst na aktualny język; kwargs podstawiane przez str.format."""
    if isinstance(text, lazy_t):
        text = text._text
    lang = get_lang()
    if lang != DEFAULT_LANG:
        text = TRANSLATIONS[lang].get(text, text)
    if kwargs:
        text = text.format(**kwargs)
    return text


class lazy_t:
    """Leniwe tłumaczenie — wartość liczona przy str(), nie przy definicji.

    Potrzebne dla etykiet i komunikatów WTForms, które powstają przy imporcie
    modułu, zanim istnieje kontekst żądania.
    """

    __slots__ = ("_text", "_kwargs")

    def __init__(self, text: str, **kwargs):
        self._text = text
        self._kwargs = kwargs

    def __str__(self) -> str:
        return t(self._text, **self._kwargs)

    def __repr__(self) -> str:
        return f"lazy_t({self._text!r})"

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(self._text)

    def __len__(self):
        return len(str(self))

    def __mod__(self, args):
        return str(self) % args


# Teksty używane w plikach static/js — wstrzykiwane do szablonów jako JSON
# (tag <script type="application/json" id="js-i18n">), czytane przez js/i18n.js.
JS_STRINGS = (
    # kreator: krok 1 (pasek kroków + opisy ścieżek)
    "2. Miejsce praktyki",
    "3. Wysłanie",
    "4. Wysłanie",
    "2. Wniosek",
    "3. Komisja",
    "4. Dyrektor",
    "2. Dane",
    "Ścieżka A: Odbędziesz praktykę w zakładzie pracy na podstawie porozumienia z uczelnią — porozumienie (zał. 1) przygotowuje i wysyła dziekanat. Wymagane: Oświadczenie zakładu pracy (zał. 9), Program (zał. 2). Po zakończeniu: Dziennik praktyki (zał. 6), Sprawozdanie (zał. 7), Potwierdzenie efektów uczenia się (zał. 4).",
    "Ścieżka B: Złożysz wniosek (zał. 4b) o uznanie trzynastu efektów uczenia się na podstawie doświadczenia zawodowego. Komisja ds. praktyk wyda opinię (zał. 4a), a Dyrektor Instytutu podejmie ostateczną decyzję. Wybierz poniżej rodzaj zatrudnienia - od tego zależy, jakie dokumenty musisz dołączyć.",
    # kreator: krok 2B/C (upload + licznik)
    "min. 500 znaków",
    "Usuń plik",
    "Nie udało się pobrać listy załączników.",
    "Wybierz plik.",
    "Wysyłanie...",
    "Błąd",
    "Nie udało się przesłać.",
    "Wybierz plik PDF lub przeciągnij tutaj",
    "Wybierz plik PDF",
    "Plik dodany pomyślnie.",
    "Błąd połączenia.",
    "Nie udało się usunąć pliku.",
    "Plik usunięty.",
    # generator PDF (student)
    "Generowanie...",
    "Generowanie wymuszone...",
    "Lista brakujących pól:",
    "Czy mimo to wygenerować dokument?",
    "Błąd serwera",
    "Błąd generowania PDF",
    # dziennik PDF (admin)
    "Pobierz PDF",
    "Gotowe!",
    "Błąd kompilacji",
    "sprawdź logi workera",
    "Kompilacja...",
    "Zlecam generowanie PDF...",
    "Kompilacja w toku...",
    "Błąd zlecenia",
    "nieznany",
    "Błąd połączenia z serwerem.",
    # panel_ui (obie apki)
    "Wybierz plik CSV",
)


def register_i18n(app) -> None:
    """Rejestruje route zmiany języka i wstrzykuje helpery do szablonów."""

    @app.route("/jezyk/<lang>", methods=["GET"])
    def zmien_jezyk(lang):
        if lang in SUPPORTED_LANGS:
            session["lang"] = lang
        return redirect(request.referrer or "/")

    @app.context_processor
    def inject_i18n():
        return {
            "t": t,
            "aktualny_jezyk": get_lang(),
            "dostepne_jezyki": SUPPORTED_LANGS,
            "js_i18n": {s: t(s) for s in JS_STRINGS},
        }
