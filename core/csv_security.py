"""Utilities for safe CSV exports."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def sanitize_csv_cell(value: Any) -> Any:
    """Neutralize spreadsheet formula injection in exported CSV cells."""
    if not isinstance(value, str):
        return value
    if value.startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def sanitize_csv_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of a CSV row with formula-like string values escaped."""
    return {key: sanitize_csv_cell(value) for key, value in row.items()}
