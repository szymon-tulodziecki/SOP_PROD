"""core/repozytoria — warstwa dostępu do danych (Repository Pattern).

Każda klasa repozytorium jest jedynym miejscem, w którym
konstruowane są zapytania ORM do konkretnej domeny.
Kontrolery i serwisy nigdy nie wywołują db.session.query() bezpośrednio.
"""
from core.repozytoria.uzytkownicy import RepozytoriumUzytkownikow
from core.repozytoria.praktyki import RepozytoriumPraktyk, RepozytoriumZapisow

__all__ = [
    'RepozytoriumUzytkownikow',
    'RepozytoriumPraktyk',
    'RepozytoriumZapisow',
]
