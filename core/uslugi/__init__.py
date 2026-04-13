"""core/uslugi — warstwa usług biznesowych.

Usługi zawierają logikę domenową i orkiestrują
repozytoria. Kontrolery wywołują wyłącznie usługi —
nie tworzą zapytań ORM ani nie operują bezpośrednio
na sesjach bazy danych.
"""
from core.uslugi.praktyki  import UslugaPraktyk
from core.uslugi.uzytkownicy import UslugaUzytkownikow
from core.uslugi.ocenianie import SerwisOceniania
from core.uslugi.dokumenty import (
    DOC_CONFIG, STATIC_TEMPLATES,
    DocumentEntry, buduj_flagi, rozwiaz_dokumenty, buduj_kontekst,
)

__all__ = [
    'UslugaPraktyk', 'UslugaUzytkownikow', 'SerwisOceniania',
    'DOC_CONFIG', 'STATIC_TEMPLATES',
    'DocumentEntry', 'buduj_flagi', 'rozwiaz_dokumenty', 'buduj_kontekst',
]
