"""Walidacja kompletności danych przed generowaniem dokumentów."""
from __future__ import annotations


def validate_completeness(zapis, doc_type: str) -> list[str]:
    """Zwraca listę brakujących pól wymaganych dla danego dokumentu."""
    missing = []
    if not (getattr(zapis, 'company_display_name', None) or (zapis.company and zapis.company.name)):
        missing.append('Nazwa firmy')
    if not (getattr(zapis, 'company_display_address', None) or (zapis.company and zapis.company.address)):
        missing.append('Adres firmy')
    if doc_type == 'ZAL_6' and not getattr(zapis, 'journal_entries', None):
        missing.append('Brak wpisów w dzienniku')
    return missing
