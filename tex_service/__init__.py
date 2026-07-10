"""
tex_service — pakiet kompilacji LaTeX do PDF.

Publiczne API:
  - compile_pdf(template_name, context) -> bytes
      Jedyna dozwolona ścieżka kompilacji: szablon Jinja2 + dane domenowe.
      Surowy TeX generowany jest wewnętrznie — nigdy nie pochodzi od użytkownika.
  - render_tex(template_name, context)  -> str
      Renderuje szablon → tekst TeX (używane przez testy).
  - TexCompilationError
"""

import sys
import os

# Gwarantuj że katalog tex_service/ jest w sys.path (potrzebne dla
# lokalnych importów: 'from sanitizer import ...' w compiler.py)
_pkg_dir = os.path.dirname(__file__)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

from compiler import (  # noqa: E402
    TexCompilationError,
    render_tex,
    compile_pdf,
)

__all__ = [
    "TexCompilationError",
    "render_tex",
    "compile_pdf",
]
