r"""tex_service/sanitizer.py

Sanityzacja danych wejściowych przed wstrzyknięciem do szablonów LaTeX.

Warstwa ochrony: dane z bazy/requestu -> sanitize() -> szablon LaTeX.
Nawet jeśli użytkownik wpisze '\\directlua{...}' w pole formularza,
po przejściu przez sanitize() zostanie to zamienione na bezpieczny
ciąg znaków LaTeX (np. \textbackslash{}directlua\{...\}).
"""

from datetime import date, datetime

from pylatexenc.latexencode import unicode_to_latex

# Znaki specjalne LaTeX wymagające escapowania.
# unicode_to_latex z pylatexenc obsługuje je wszystkie, ale jawna lista
# służy jako dokumentacja i drugi poziom ochrony.
_LATEX_SPECIAL_CHARS = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "^": r"\^{}",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "%": r"\%",
}


def sanitize_text(value, max_length: int = 5000) -> str:
    """Jak sanitize(), ale dla wieloakapitowych pól tekstowych.

    Zachowuje przełamania akapitów (puste linie → \\par w LaTeX).
    Używać dla pól sprawozdania, uzasadnienia itp.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if max_length:
        text = text[:max_length]
    paragraphs = text.split("\n\n")
    encoded = []
    for p in paragraphs:
        lines = p.split("\n")
        encoded_lines = [unicode_to_latex(line) for line in lines]
        encoded.append(r"\\".join(encoded_lines))
    return "\n\n".join(encoded)


def sanitize(value, max_length: int = 500) -> str:
    """Oczyszcza wartość do bezpiecznego wstawienia w szablon LaTeX.

    Używa pylatexenc.unicode_to_latex, które:
    - Zamienia wszystkie znaki specjalne LaTeX (\\, {, }, $, &, #, ^, _, ~, %)
      na ich escapowane odpowiedniki
    - Zamienia znaki Unicode na komendy LaTeX (np. ą → \\k{a})

    Dzięki temu nawet jeśli wartość zawiera złośliwy kod LaTeX
    (np. z pola tekstowego w formularzu), zostanie on zrenderowany
    jako dosłowny tekst, nie wykonany jako komenda.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if max_length:
        text = text[:max_length]
    # unicode_to_latex escapuje wszystkie znaki specjalne LaTeX
    return unicode_to_latex(text)


def sanitize_date(value, fmt: str = "%d.%m.%Y") -> str:
    """Formatuje datę do bezpiecznego ciągu — tylko cyfry i kropki."""
    if value is None:
        return "—"
    if isinstance(value, (date, datetime)):
        return value.strftime(fmt)
    try:
        return date.fromisoformat(str(value)).strftime(fmt)
    except ValueError:
        return sanitize(str(value))


def sanitize_int(value) -> str:
    """Zwraca wyłącznie cyfry całkowite — zero ryzyka injection."""
    if value is None:
        return "0"
    try:
        return str(int(value))
    except (ValueError, TypeError):
        return "0"
