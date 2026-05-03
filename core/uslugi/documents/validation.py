"""Pre-generation completeness validation for documents."""
from __future__ import annotations


def waliduj_kompletnosc(zapis, doc_type: str) -> list[str]:
    """Returns a list of missing field labels required for the given document."""
    missing = []
    if not (getattr(zapis, 'firma_nazwa', None) or (zapis.firma and zapis.firma.name)):
        missing.append('Nazwa firmy')
    if not (getattr(zapis, 'firma_adres', None) or (zapis.firma and zapis.firma.address)):
        missing.append('Adres firmy')
    if doc_type == 'ZAL_6' and not getattr(zapis, 'wpisy_dziennika', None):
        missing.append('Brak wpisów w dzienniku')
    return missing
