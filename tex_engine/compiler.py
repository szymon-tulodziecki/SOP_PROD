"""
tex_engine/compiler.py

Silnik kompilacji PDF. Przyjmuje nazwę szablonu i kontekst danych,
wyrenderowuje szablon Jinja2, wywołuje lualatex (trzy przebiegi),
zwraca bajty PDF lub rzuca TexCompilationError.

Zabezpieczenia:
    - lualatex uruchamiany z flagami -no-shell-escape i -interaction=nonstopmode
    - Timeout 60 sekund na kompilację
    - Każda kompilacja w izolowanym tmpdir (automicznie usuwany)
    - stdin zamknięty (/dev/null)
"""

import os
import shutil
import subprocess
import tempfile
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .sanitizer import sanitize, sanitize_date, sanitize_int

logger = logging.getLogger(__name__)

# Katalog z szablonami .j2.tex (nie surowe .tex z repozytorium)
TEMPLATES_DIR = Path(__file__).parent / "templates"

# Ile sekund max na jeden przebieg lualatex
COMPILE_TIMEOUT = 60

# Ile razy uruchamiamy lualatex (referencje krzyżowe, spis treści itp.)
COMPILE_PASSES = 3


class TexCompilationError(RuntimeError):
    """Wyrzucany gdy lualatex zakończy się błędem."""
    def __init__(self, message: str, log: str = ""):
        super().__init__(message)
        self.log = log


def _build_jinja_env() -> Environment:
    """
    Buduje środowisko Jinja2 z niestandardowymi tagami, żeby nie kolidować
    z LaTeX-owymi nawiasami klamrowymi.

    Bloki:   <<% ... %>>
    Zmienne: << ... >>
    Komentarze: <<# ... #>>
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        block_start_string="<<%",
        block_end_string="%>>",
        variable_start_string="<<",
        variable_end_string=">>",
        comment_start_string="<<#",
        comment_end_string="#>>",
        undefined=StrictUndefined,   # błąd gdy zmienna brakuje w kontekście
        keep_trailing_newline=True,
    )
    # Rejestrujemy filtry sanityzujące jako globalne filtry Jinji
    env.filters["s"]    = sanitize          # {{ wartosc | s }}
    env.filters["date"] = sanitize_date     # {{ data | date }}
    env.filters["num"]  = sanitize_int      # {{ godziny | num }}
    return env


_JINJA_ENV: Environment | None = None


def get_jinja_env() -> Environment:
    """Singleton – środowisko Jinja2 tworzymy raz."""
    global _JINJA_ENV
    if _JINJA_ENV is None:
        _JINJA_ENV = _build_jinja_env()
    return _JINJA_ENV


def _find_lualatex() -> str:
    """Zwraca ścieżkę do binarki lualatex lub rzuca EnvironmentError."""
    binary = shutil.which("lualatex")
    if binary is None:
        raise EnvironmentError(
            "Nie znaleziono lualatex w PATH. "
            "Zainstaluj TeX Live (np. sudo apt install texlive-full) "
            "lub upewnij się, że lualatex jest w PATH."
        )
    return binary


def _run_lualatex(lualatex: str, tex_file: Path, workdir: Path) -> str:
    """
    Wywołuje jeden przebieg lualatex. Zwraca zawartość pliku .log.
    Rzuca TexCompilationError jeśli proces zakończy się kodem != 0.
    """
    cmd = [
        lualatex,
        "-no-shell-escape",          # blokuje \write18 / shell escape
        "-interaction=nonstopmode",  # nie czeka na input; kontynuuje
        "-halt-on-error",            # zatrzymuje się przy pierwszym błędzie
        "-output-directory", str(workdir),
        str(tex_file),
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            timeout=COMPILE_TIMEOUT,
            stdin=subprocess.DEVNULL,   # zamknięty stdin
        )
    except subprocess.TimeoutExpired:
        raise TexCompilationError(
            f"lualatex przekroczył limit czasu ({COMPILE_TIMEOUT}s). "
            "Sprawdź szablon pod kątem nieskończonych pętli."
        )

    # Odczyt logu
    log_file = workdir / tex_file.with_suffix(".log").name
    log_text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""

    if result.returncode != 0:
        raise TexCompilationError(
            f"lualatex zakończył się błędem (kod {result.returncode}). "
            "Sprawdź atrybut .log w wyjątku.",
            log=log_text,
        )

    return log_text


def compile_pdf(template_name: str, context: dict) -> bytes:
    """
    Publiczne API silnika.

    Renderuje szablon Jinja2 z katalogu tex_engine/templates/,
    kompiluje przez lualatex (3 przebiegi) w izolowanym tmpdir,
    zwraca surowe bajty PDF.

    Args:
        template_name:  Nazwa pliku szablonu (np. "zal6_dziennik.tex.j2").
        context:        Słownik z danymi do wstrzyknięcia (wartości NIE escapowane –
                        szablony używają filtra | s, | date itd.).

    Returns:
        bytes  –  zawartość pliku PDF

    Raises:
        TexCompilationError:  gdy lualatex zgłosi błąd kompilacji.
        jinja2.UndefinedError: gdy szablon użyje zmiennej nie podanej w context.
        EnvironmentError:     gdy lualatex nie jest zainstalowany.
    """
    lualatex = _find_lualatex()
    env = get_jinja_env()

    # 1. Renderowanie szablonu Jinja2 -> kod TeX
    template = env.get_template(template_name)
    tex_source = template.render(**context)

    # 2. Kompilacja w izolowanym katalogu tymczasowym
    with tempfile.TemporaryDirectory(prefix="sop_tex_") as tmpdir:
        workdir = Path(tmpdir)
        tex_file = workdir / "document.tex"
        tex_file.write_text(tex_source, encoding="utf-8")

        logger.info("Kompilacja %s (context keys: %s)", template_name, list(context.keys()))

        for pass_num in range(1, COMPILE_PASSES + 1):
            logger.debug("  Pass %d/%d ...", pass_num, COMPILE_PASSES)
            _run_lualatex(lualatex, tex_file, workdir)

        # 3. Odczyt PDF
        pdf_file = workdir / "document.pdf"
        if not pdf_file.exists():
            raise TexCompilationError("lualatex zakończył się sukcesem, ale brak pliku PDF.")

        pdf_bytes = pdf_file.read_bytes()
        logger.info("PDF wygenerowany: %d bajtów", len(pdf_bytes))
        return pdf_bytes
