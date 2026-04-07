"""core/uslugi — warstwa usług biznesowych.

Usługi zawierają logikę domenową i orkiestrują
repozytoria. Kontrolery wywołują wyłącznie usługi —
nie tworzą zapytań ORM ani nie operują bezpośrednio
na sesjach bazy danych.
"""
from core.uslugi.praktyki    import UslugaPraktyk
from core.uslugi.uzytkownicy import UslugaUzytkownikow
from core.uslugi.ocenianie   import SerwisOceniania

__all__ = ['UslugaPraktyk', 'UslugaUzytkownikow', 'SerwisOceniania']
