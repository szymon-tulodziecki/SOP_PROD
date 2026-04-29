"""core/repozytoria — warstwa dostępu do danych (Repository Pattern).

Każda klasa repozytorium jest jedynym miejscem, w którym
konstruowane są zapytania ORM do konkretnej domeny.
Kontrolery i serwisy nigdy nie wywołują db.session.query() bezpośrednio.
"""
from core.repozytoria.users import UserRepository
from core.repozytoria.internships import InternshipRepository, EnrollmentRepository
from core.repozytoria.entries import JournalRepository
from core.repozytoria.outcomes import OutcomeRepository
from core.repozytoria.companies import CompanyRepository
from core.repozytoria.documents import LogRepository, StudentDocumentRepository
from core.repozytoria.assessments import AssessmentRepository

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
