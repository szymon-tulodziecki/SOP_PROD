"""
tex_service — pakiet kompilacji LaTeX do PDF.

Eksportuje:
  - compile_pdf(template_name, context) -> bytes
  - render_tex(template_name, context)  -> str
  - compile_raw_tex(tex_source)         -> bytes
  - TexCompilationError
  - pdf_service  (instancja PDFService)
"""

import sys
import os

# Gwarantuj że katalog tex_service/ jest w sys.path (potrzebne dla
# lokalnych importów: 'from sanitizer import ...' w compiler.py)
_pkg_dir = os.path.dirname(__file__)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

from compiler import (          # noqa: E402
    TexCompilationError,
    render_tex,
    compile_raw_tex,
    compile_pdf,
)
from pdf_service import pdf_service  # noqa: E402

__all__ = [
    "TexCompilationError",
    "render_tex",
    "compile_raw_tex",
    "compile_pdf",
    "pdf_service",
]
