"""
tex_engine/sanitizer.py

Funkcje czyszczące tekst wejściowy przed wstrzyknięciem do szablonu LaTeX.
Cel: ochrona przed uszkodzeniem dokumentu i wstrzyknięciem złośliwego kodu TeX.
"""

import re

# Znaki specjalne LaTeXa i ich bezpieczne odpowiedniki (kolejność MA ZNACZENIE)
_REPLACEMENTS = [
    (r"\\",  r"\\textbackslash{}"),   # lewy ukośnik – musi być PIERWSZY
    ("&",    r"\&"),
    ("%",    r"\%"),
    ("$",    r"\$"),
    ("#",    r"\#"),
    ("_",    r"\_"),
    ("{",    r"\{"),
    ("}",    r"\}"),
    ("~",    r"\\textasciitilde{}"),
    ("^",    r"\\textasciicircum{}"),
]

# Niebezpieczne sekwencje TeX-a, które nie powinny się pojawić w danych użytkownika
_DANGEROUS_PATTERNS = re.compile(
    r"\\(write18|input|include|csname|expandafter|catcode|def\s|let\s|"
    r"unexpanded|noexpand|jobname|openout|closeout|read|verbatimfile)",
    re.IGNORECASE,
)


def sanitize(text: str, max_length: int = 1000):
    """
    Główna funkcja sanityzacji. Przyjmuje surowy tekst od użytkownika,
    zwraca bezpieczny ciąg gotowy do wklejenia do szablonu LaTeX.

    Obsługuje dwa tryby użycia jako filtr Jinja2:
        {{ wartość | s }}          – domyślny max_length=1000
        {{ wartość | s(400) }}     – niestandardowy max_length

    Args:
        text:       Tekst wejściowy LUB int (max_length) gdy wywołano jako s(400).
        max_length: Maksymalna długość wyjściowego stringa (ochrona przed DoS).

    Returns:
        Escapowany string bezpieczny dla LaTeXa, lub funkcję-wrapper gdy
        wywołano jako s(400) – Jinja2 wywoła ją z wartością.
    """
    # Jinja2 filtr z argumentem: {{ val | s(400) }} -> sanitize(400) -> zwróć callable
    if isinstance(text, int):
        _max = text
        def _wrapper(inner_text: str) -> str:
            return sanitize(inner_text, max_length=_max)
        return _wrapper

    if not isinstance(text, str):
        text = str(text)

    # Ochrona przed wstrzyknięciem niebezpiecznych komend TeX
    if _DANGEROUS_PATTERNS.search(text):
        raise ValueError(
            f"Niedozwolona sekwencja TeX wykryta w danych wejściowych: {text[:80]!r}"
        )

    # Escapowanie znaków specjalnych (uwaga na kolejność!)
    for raw, escaped in _REPLACEMENTS:
        text = text.replace(raw, escaped)

    # Normalizacja białych znaków: akapity (dwa newlines) zamieniamy
    # na LaTeX-owy \par, pojedyncze newline zamieniamy na spację.
    text = re.sub(r"\r\n|\r", "\n", text)          # ujednolicenie końców linii
    text = re.sub(r"\n{2,}", r" \\par ", text)      # podwójny newline -> \par
    text = text.replace("\n", " ")                  # pojedynczy newline -> spacja

    # Obcięcie do max_length znaków (zapobieganie przepełnieniu pamięci LaTeXa)
    if len(text) > max_length:
        text = text[:max_length]

    return text


def sanitize_date(date_obj) -> str:
    """
    Konwertuje obiekt datetime.date do czytelnego formatu polskiego.
    Bezpieczne – date nie zawiera znaków specjalnych LaTeXa.
    """
    from datetime import date
    if isinstance(date_obj, date):
        months = [
            "", "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
            "lipca", "sierpnia", "września", "października", "listopada", "grudnia"
        ]
        return f"{date_obj.day} {months[date_obj.month]} {date_obj.year}"
    return str(date_obj)


def sanitize_int(value) -> str:
    """
    Konwertuje liczbę do stringa. Ochrona przed wstrzyknięciem przez pola numeryczne.
    """
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "0"
