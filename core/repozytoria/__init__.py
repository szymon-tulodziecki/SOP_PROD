"""core/repozytoria — warstwa dostępu do danych (Repository Pattern).

Każda klasa repozytorium jest jedynym miejscem, w którym
konstruowane są zapytania ORM do konkretnej domeny.
Kontrolery i serwisy nigdy nie wywołują db.session.query() bezpośrednio.
"""
from core.repozytoria.uzytkownicy import RepozytoriumUzytkownikow
from core.repozytoria.praktyki import RepozytoriumPraktyk, RepozytoriumZapisow
from core.repozytoria.wpisy import RepozytoriumWpisow
from core.repozytoria.efekty import RepozytoriumEfektow
from core.repozytoria.firmy import RepozytoriumFirm
from core.repozytoria.dokumenty import RepozytoriumLogow, RepozytoriumDokumentowStudenta
from core.repozytoria.oceny import RepozytoriumOcen

__all__ = [
    'RepozytoriumUzytkownikow',
    'RepozytoriumPraktyk',
    'RepozytoriumZapisow',
    'RepozytoriumWpisow',
    'RepozytoriumEfektow',
    'RepozytoriumFirm',
    'RepozytoriumLogow',
    'RepozytoriumDokumentowStudenta',
    'RepozytoriumOcen',
]
