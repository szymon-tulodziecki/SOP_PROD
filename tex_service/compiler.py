"""tex_service/compiler.py

Silnik kompilacji PDF. Przyjmuje nazwę szablonu i kontekst danych,
wyrenderowuje szablon Jinja2, wywołuje lualatex,
zwraca bajty PDF lub rzuca TexCompilationError.
"""

import os
import re
import shutil
import subprocess
import tempfile
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from sanitizer import sanitize, sanitize_date, sanitize_int

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

COMPILE_TIMEOUT = int(os.environ.get('LATEX_TIMEOUT', '60'))
COMPILE_PASSES = 1


class TexCompilationError(RuntimeError):
    def __init__(self, message: str, log: str = ""):
        super().__init__(message)
        self.log = log


def _build_jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        block_start_string="<<%",
        block_end_string="%>>",
        variable_start_string="<<",
        variable_end_string=">>",
        comment_start_string="<<#",
        comment_end_string="#>>",
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    env.filters["s"] = sanitize
    env.filters["date"] = sanitize_date
    env.filters["num"] = sanitize_int
    return env


_JINJA_ENV: Environment | None = None


def get_jinja_env() -> Environment:
    global _JINJA_ENV
    if _JINJA_ENV is None:
        _JINJA_ENV = _build_jinja_env()
    return _JINJA_ENV


def _find_lualatex() -> str:
    binary = shutil.which("lualatex")
    if binary is None:
        raise EnvironmentError(
            "Nie znaleziono lualatex w PATH. "
            "Sprawdź czy texlive jest zainstalowany w kontenerze."
        )
    return binary


def _run_lualatex(lualatex: str, tex_file: Path, workdir: Path) -> str:
    cmd = [
        lualatex,
        "-no-shell-escape",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-output-directory", str(workdir),
        str(tex_file),
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            timeout=COMPILE_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise TexCompilationError(
            f"lualatex przekroczył limit czasu ({COMPILE_TIMEOUT}s)."
        )

    log_file = workdir / tex_file.with_suffix(".log").name
    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""

    if result.returncode != 0:
        raise TexCompilationError(
            f"lualatex zakończył się błędem (kod {result.returncode}).",
            log=log_text,
        )

    return log_text


def render_tex(template_name: str, context: dict) -> str:
    """Renderuje szablon Jinja2 → surowy tekst TeX."""
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context)


_MAX_RAW_TEX_SIZE = 100_000  # 100 KB — wystarczy dla każdego dokumentu

# Wzorce niebezpiecznych komend LaTeX.
# Każdy wpis: (wzorzec_regex, opis_dla_użytkownika).
# WAŻNE: to jest lista blokowanych wzorców (blocklist), nie lista dozwolonych.
# Blocklist nigdy nie jest kompletna — główną ochroną jest sandboxing kontenera.
_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # ── Shell escape — bezpośrednie wykonanie kodu powłoki ──────────────
    (r'\\write\s*18\b',               r'\write18 — shell escape'),
    (r'\\write\s*-\s*1\b',            r'\write-1 — zapis na terminal'),
    (r'\\immediate\s*\\write\s*18\b', r'\immediate\write18 — shell escape'),
    (r'\\ShellEscape\b',              r'\ShellEscape — shell escape (shellesc)'),

    # ── Lua — wykonanie dowolnego kodu Lua/systemu ───────────────────────
    (r'\\directlua\b',  r'\directlua — wykonanie kodu Lua'),
    (r'\\latelua\b',    r'\latelua — wykonanie kodu Lua'),
    (r'\\luacode\b',    r'\luacode — środowisko Lua'),
    (r'\\luaexec\b',    r'\luaexec — wykonanie Lua'),
    (r'\\luastring\b',  r'\luastring — ciąg Lua'),
    (r'\\lua[A-Za-z]+', r'\lua* — komenda Lua'),

    # ── Odczyt plików systemu ────────────────────────────────────────────
    (r'\\input\s*\{',          r'\input{} — dołączenie pliku'),
    (r'\\include\s*\{',        r'\include{} — dołączenie pliku'),
    (r'\\verbatiminput\b',     r'\verbatiminput — odczyt pliku jako tekst'),
    (r'\\lstinputlisting\b',   r'\lstinputlisting — odczyt pliku (listings)'),
    (r'\\inputminted\b',       r'\inputminted — odczyt pliku (minted)'),
    (r'\\subfile\b',           r'\subfile — dołączenie podpliku'),
    (r'\\import\b',            r'\import — dołączenie z zewnętrznego katalogu'),
    (r'\\openin\b',            r'\openin — otwarcie strumienia odczytu'),
    (r'\\read\b',              r'\read — odczyt ze strumienia'),

    # ── Zapis plików systemu ─────────────────────────────────────────────
    (r'\\openout\b',           r'\openout — otwarcie strumienia zapisu'),
    (r'\\newwrite\b',          r'\newwrite — rejestracja strumienia zapisu'),
    (r'\\newread\b',           r'\newread — rejestracja strumienia odczytu'),
    (r'\\immediate\s*\\write', r'\immediate\write — natychmiastowy zapis'),
    (r'\\write\s*\\',          r'\write\register — zapis przez rejestr'),

    # ── Niebezpieczne pakiety ────────────────────────────────────────────
    (r'\\usepackage\s*(?:\[.*?\])?\s*\{shellesc\}',  r'pakiet shellesc — shell escape'),
    (r'\\usepackage\s*(?:\[.*?\])?\s*\{minted\}',    r'pakiet minted — wykonanie kodu powłoki'),
    (r'\\usepackage\s*(?:\[.*?\])?\s*\{sagetex\}',   r'pakiet sagetex — wykonanie kodu Python/Sage'),
    (r'\\usepackage\s*(?:\[.*?\])?\s*\{pythontex\}', r'pakiet pythontex — wykonanie kodu Python'),

    # ── Obejście interpretera — zmiana znaczenia znaków ─────────────────
    (r'\\catcode\b',  r'\catcode — zmiana kodu kategorii znaków'),
    (r'\\csname\b',   r'\csname — obfuskacja nazwy komendy'),

    # ── Niskopoziomowe prymitywy pdftex/luatex ───────────────────────────
    (r'\\pdfshellescape\b', r'\pdfshellescape — flaga shell escape'),
    (r'\\pdfobj\b',         r'\pdfobj — niskopoziomowy obiekt PDF'),
    (r'\\special\b',        r'\special — komenda sterownika wyjścia'),
]


def _check_dangerous_commands(tex_source: str) -> None:
    """Sprawdza surowy kod TeX pod kątem niebezpiecznych komend.

    Rzuca TexCompilationError przy pierwszym dopasowaniu.
    Sprawdzanie jest case-insensitive i wieloliniowe.

    WAŻNE: Funkcja jest drugą linią obrony — pierwsze są:
    1. Sandboxing kontenera (read_only, no-new-privileges, cap_drop)
    2. lualatex -no-shell-escape

    Nie należy polegać wyłącznie na tej funkcji.
    """
    if len(tex_source) > _MAX_RAW_TEX_SIZE:
        raise TexCompilationError(
            f"Kod TeX jest zbyt długi ({len(tex_source)} znaków). "
            f"Maksymalny rozmiar to {_MAX_RAW_TEX_SIZE} znaków."
        )

    for pattern, description in _DANGEROUS_PATTERNS:
        if re.search(pattern, tex_source, re.IGNORECASE | re.DOTALL):
            raise TexCompilationError(
                f"Zablokowana niebezpieczna komenda LaTeX: {description}. "
                f"Ze względów bezpieczeństwa ta komenda jest niedozwolona "
                f"w trybie ręcznej kompilacji."
            )


def compile_raw_tex(tex_source: str) -> bytes:
    """Kompiluje surowy kod TeX → bajty PDF.

    Przed kompilacją sprawdza kod pod kątem niebezpiecznych komend
    (ochrona przed LaTeX Command Injection).
    """
    _check_dangerous_commands(tex_source)

    lualatex = _find_lualatex()

    with tempfile.TemporaryDirectory(prefix="tex_") as tmpdir:
        workdir = Path(tmpdir)
        tex_file = workdir / "document.tex"
        tex_file.write_text(tex_source, encoding="utf-8")

        for _ in range(COMPILE_PASSES):
            _run_lualatex(lualatex, tex_file, workdir)

        pdf_file = workdir / "document.pdf"
        if not pdf_file.exists():
            raise TexCompilationError("lualatex zakończył się sukcesem, ale brak pliku PDF.")

        return pdf_file.read_bytes()


def compile_pdf(template_name: str, context: dict) -> bytes:
    """Publiczne API: template + context → bajty PDF."""
    logger.info("Kompilacja %s", template_name)
    tex_source = render_tex(template_name, context)
    pdf_bytes = compile_raw_tex(tex_source)
    logger.info("Wygenerowano %d bajtów", len(pdf_bytes))
    return pdf_bytes
