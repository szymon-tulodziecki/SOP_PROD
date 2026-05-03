"""Business services coordinate domain logic and repositories."""
from core.services.internships import InternshipService
from core.services.users import UserService
from core.services.evaluation import EvaluationService, AssessmentService
from core.services.committee import CommitteeService
from core.services.documents import (
    DOC_CONFIG, STATIC_TEMPLATES,
    DocumentEntry, build_flags, resolve_documents, build_context,
)

__all__ = [
    'InternshipService', 'UserService', 'EvaluationService', 'AssessmentService', 'CommitteeService',
    'DOC_CONFIG', 'STATIC_TEMPLATES',
    'DocumentEntry', 'build_flags', 'resolve_documents', 'build_context',
]
