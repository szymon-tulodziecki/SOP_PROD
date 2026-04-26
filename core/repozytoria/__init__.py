"""core/repozytoria — warstwa dostępu do danych (Repository Pattern).

Każda klasa repozytorium jest jedynym miejscem, w którym
konstruowane są zapytania ORM do konkretnej domeny.
Kontrolery i serwisy nigdy nie wywołują db.session.query() bezpośrednio.
"""
from core.repozytoria.uzytkownicy import UserRepository
from core.repozytoria.praktyki import InternshipRepository, EnrollmentRepository
from core.repozytoria.wpisy import JournalRepository
from core.repozytoria.efekty import OutcomeRepository
from core.repozytoria.firmy import CompanyRepository
from core.repozytoria.dokumenty import LogRepository, StudentDocumentRepository
from core.repozytoria.oceny import AssessmentRepository

__all__ = [
    'UserRepository',
    'InternshipRepository',
    'EnrollmentRepository',
    'JournalRepository',
    'OutcomeRepository',
    'CompanyRepository',
    'LogRepository',
    'StudentDocumentRepository',
    'AssessmentRepository',
]
