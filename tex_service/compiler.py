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

from sanitizer import sanitize, sanitize_text, sanitize_date, sanitize_int

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

COMPILE_TIMEOUT = int(os.environ.get("LATEX_TIMEOUT", "60"))
COMPILE_PASSES = 2


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
    env.filters["text"] = sanitize_text
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
        "-output-directory",
        str(workdir),
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
        raise TexCompilationError(f"lualatex przekroczył limit czasu ({COMPILE_TIMEOUT}s).")

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


def compile_pdf(template_name: str, context: dict) -> bytes:
    """Publiczne API: template + context → bajty PDF.

    Jedyna dozwolona ścieżka kompilacji. Surowy TeX pochodzi wyłącznie
    z szablonu Jinja2 zaaudytowanego w systemie plików kontenera —
    nigdy z danych dostarczonych przez użytkownika.

    Architektura allowlist: użytkownik dostarcza wyłącznie klucze JSON
    (dane domenowe), nie struktury TeX. Sanitizer w filtrach Jinja2
    (|s, |date, |num) zapobiega wstrzyknięciu specjalnych znaków LaTeX
    nawet w polach tekstowych.
    """
    logger.info("Kompilacja %s", template_name)
    lualatex = _find_lualatex()
    tex_source = render_tex(template_name, context)

    with tempfile.TemporaryDirectory(prefix="tex_") as tmpdir:
        workdir = Path(tmpdir)
        tex_file = workdir / "document.tex"
        tex_file.write_text(tex_source, encoding="utf-8")

        for _ in range(COMPILE_PASSES):
            _run_lualatex(lualatex, tex_file, workdir)

        pdf_file = workdir / "document.pdf"
        if not pdf_file.exists():
            raise TexCompilationError("lualatex zakończył się sukcesem, ale brak pliku PDF.")

        pdf_bytes = pdf_file.read_bytes()

    logger.info("Wygenerowano %d bajtów", len(pdf_bytes))
    return pdf_bytes
