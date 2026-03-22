# tex_engine – silnik generowania PDF-ów przez LuaLaTeX
# Punkt wejścia: tex_engine.compiler.compile_pdf(template_name, context) -> bytes
from .compiler import compile_pdf
from .sanitizer import sanitize

__all__ = ["compile_pdf", "sanitize"]
