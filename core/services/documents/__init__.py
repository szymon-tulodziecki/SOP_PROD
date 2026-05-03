"""Documents service package.

Public API re-exports â€” keep import paths stable for callers.
Submodules:
  - policy:     DOC_CONFIG, STATIC_TEMPLATES, DocumentEntry, resolve_documents, build_flags
  - context:    build_context (canonical TeX context)
  - validation: validate_completeness
  - sse:        sse_pdf_status
"""
from core.services.documents.policy import (
    DOC_CONFIG,
    STATIC_TEMPLATES,
    DocumentEntry,
    build_flags,
    resolve_documents,
)
from core.services.documents.context import build_context
from core.services.documents.validation import validate_completeness
from core.services.documents.sse import sse_pdf_status

__all__ = [
    'DOC_CONFIG',
    'STATIC_TEMPLATES',
    'DocumentEntry',
    'build_flags',
    'resolve_documents',
    'build_context',
    'validate_completeness',
    'sse_pdf_status',
]
