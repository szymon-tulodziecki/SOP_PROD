"""Documents service package.

Public API re-exports — keep import paths stable for callers.
Submodules:
  - policy:     DOC_CONFIG, STATIC_TEMPLATES, DocumentEntry, rozwiaz_dokumenty, buduj_flagi
  - context:    build_context (canonical TeX context)
  - validation: waliduj_kompletnosc
  - sse:        sse_pdf_status
"""
from core.uslugi.documents.policy import (
    DOC_CONFIG,
    STATIC_TEMPLATES,
    DocumentEntry,
    buduj_flagi,
    rozwiaz_dokumenty,
)
from core.uslugi.documents.context import build_context
from core.uslugi.documents.validation import waliduj_kompletnosc
from core.uslugi.documents.sse import sse_pdf_status

__all__ = [
    'DOC_CONFIG',
    'STATIC_TEMPLATES',
    'DocumentEntry',
    'buduj_flagi',
    'rozwiaz_dokumenty',
    'build_context',
    'waliduj_kompletnosc',
    'sse_pdf_status',
]
