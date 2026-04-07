"""core/modele/__init__.py

Eksportuje wszystkie modele domenowe.
Flask-Migrate (Alembic) musi widzieć każdą klasę db.Model,
zanim wygeneruje skrypt migracji — stąd gwiazdkowe importy.
"""

from core.modele.uzytkownicy import (
    RolaUzytkownika,
    Uzytkownik,
    Student,
    Administrator,
    OpikunUczelniany,
)

from core.modele.firmy import Firma

from core.modele.praktyki import (
    StatusPraktyki,
    StatusZapisu,
    SciezkaPraktyki,
    Praktyka,
    ZapisPraktyki,
    HarmonogramPraktyki,
    Sprawozdanie,
    IndywidualnyProgram,
    NumerPisma,
)

from core.modele.dziennik import (
    WynikOceny,
    EfektUczenia,
    wpisy_efekty,
    WpisDziennika,
    OcenaPraktyki,
)

from core.modele.dokumenty import (
    StatusDokumentu,
    LogAudytuDokumentow,
    DocumentAuditLog,        # alias
    DokumentPrzeslany,
    UploadedDocument,        # alias
)

__all__ = [
    # uzytkownicy
    'RolaUzytkownika', 'Uzytkownik', 'Student', 'Administrator', 'OpikunUczelniany',
    # firmy
    'Firma',
    # praktyki
    'StatusPraktyki', 'StatusZapisu', 'SciezkaPraktyki',
    'Praktyka', 'ZapisPraktyki', 'HarmonogramPraktyki',
    'Sprawozdanie', 'IndywidualnyProgram', 'NumerPisma',
    # dziennik
    'WynikOceny', 'EfektUczenia', 'wpisy_efekty', 'WpisDziennika', 'OcenaPraktyki',
    # dokumenty
    'StatusDokumentu', 'LogAudytuDokumentow', 'DocumentAuditLog',
    'DokumentPrzeslany', 'UploadedDocument',
]
