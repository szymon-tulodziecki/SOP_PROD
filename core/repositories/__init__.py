"""core/repozytoria — warstwa dostępu do danych (Repository Pattern).

Każda klasa repozytorium jest jedynym miejscem, w którym
konstruowane są zapytania ORM do konkretnej domeny.
Kontrolery i serwisy nigdy nie wywołują db.session.query() bezpośrednio.
"""
from core.repositories.users import UserRepository
from core.repositories.internships import InternshipRepository, EnrollmentRepository
from core.repositories.entries import JournalRepository
from core.repositories.outcomes import OutcomeRepository
from core.repositories.companies import CompanyRepository
from core.repositories.documents import LogRepository, StudentDocumentRepository
from core.repositories.assessments import AssessmentRepository

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
