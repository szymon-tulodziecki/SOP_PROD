"""
tex_engine/compiler.py - Bridge to tex_service

This module provides backward compatibility by importing functions
from tex_service.compiler where the actual implementation resides.
"""

# Import functions from tex_service
import sys
import os

# Add tex_service to Python path
tex_service_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tex_service')
if tex_service_path not in sys.path:
    sys.path.insert(0, tex_service_path)

# Import and re-export the functions
from compiler import (
    TexCompilationError,
    render_tex,
    compile_raw_tex,
    compile_pdf
)

__all__ = [
    'TexCompilationError',
    'render_tex',
    'compile_raw_tex',
    'compile_pdf'
]