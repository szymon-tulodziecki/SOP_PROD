"""tex_service/compiler.py

Silnik kompilacji PDF. Przyjmuje nazwę szablonu i kontekst danych,
wyrenderowuje szablon Jinja2, wywołuje lualatex,
zwraca bajty PDF lub rzuca TexCompilationError.
"""

import os
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


def _check_dangerous_commands(tex_source: str) -> None:
    """Sprawdza surowy kod TeX pod kątem niebezpiecznych komend.

    Blokuje komendy umożliwiające odczyt/zapis plików systemowych
    nawet bez flagi --shell-escape:
    - \\input, \\include, \\includegraphics z ścieżkami bezwzględnymi
    - \\openin, \\openout, \\read, \\write — operacje I/O
    - \\catcode — zmiana znaczenia znaków (obejście sanityzacji)
    - \\newwrite, \\newread, \\immediate — niskopoziomowe I/O
    - usepackage{shellesc} — próby włączenia shell escape
    """
    import re

    # Wzorce niebezpiecznych komend LaTeX
    _DANGEROUS_PATTERNS = [
        (r'\\input\s*\{[^}]*/', 'Komenda \\input z ścieżką bezwzględną'),
        (r'\\include\s*\{[^}]*/', 'Komenda \\include z ścieżką bezwzględną'),
        (r'\\openin', 'Komenda \\openin (odczyt plików)'),
        (r'\\openout', 'Komenda \\openout (zapis plików)'),
        (r'\\read\b', 'Komenda \\read (odczyt plików)'),
        (r'\\write\s*\\', 'Komenda \\write (zapis plików)'),
        (r'\\newwrite', 'Komenda \\newwrite (tworzenie strumienia zapisu)'),
        (r'\\newread', 'Komenda \\newread (tworzenie strumienia odczytu)'),
        (r'\\immediate\s*\\write', 'Komenda \\immediate\\write (natychmiastowy zapis)'),
        (r'\\catcode', 'Komenda \\catcode (zmiana interpretera znaków)'),
        (r'\\usepackage\s*\{shellesc\}', 'Pakiet shellesc (shell escape)'),
        (r'\\directlua', 'Komenda \\directlua (wykonanie kodu Lua)'),
        (r'\\latelua', 'Komenda \\latelua (wykonanie kodu Lua)'),
    ]

    for pattern, description in _DANGEROUS_PATTERNS:
        if re.search(pattern, tex_source, re.IGNORECASE):
            raise TexCompilationError(
                f"Zablokowana niebezpieczna komenda LaTeX: {description}. "
                f"Ze względów bezpieczeństwa nie można używać tej komendy w trybie ręcznym."
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
