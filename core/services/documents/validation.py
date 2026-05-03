"""Pre-generation completeness validation for documents."""
from __future__ import annotations


def validate_completeness(zapis, doc_type: str) -> list[str]:
    """Returns a list of missing field labels required for the given document."""
    missing = []
    if not (getattr(zapis, 'company_display_name', None) or (zapis.company and zapis.company.name)):
        missing.append('Nazwa firmy')
    if not (getattr(zapis, 'company_display_address', None) or (zapis.company and zapis.company.address)):
        missing.append('Adres firmy')
    if doc_type == 'ZAL_6' and not getattr(zapis, 'journal_entries', None):
        missing.append('Brak wpisĂłw w dzienniku')
    return missing
