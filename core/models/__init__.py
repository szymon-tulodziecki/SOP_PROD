"""core/modele/__init__.py

Exports all domain models.
Flask-Migrate (Alembic) must see every db.Model class
before it can generate migration scripts — hence the star-style imports.
"""

from core.models.users import (
    UserRole,
    UserRoleAssoc,
    User,
    Student,
    Administrator,
    UniversityMentor,
    KomisjaUser,
    DyrektorUser,
    DziekanatUser,
)

from core.models.companies import (
    Company,
)

from core.models.internships import (
    InternshipStatus,
    EnrollmentStatus,
    InternshipPath,
    EventType,
    Internship,
    InternshipEnrollment,
    WorkplaceDetails,
    PathJustification,
    Examination,
    FinalGrades,
    ProcessEvent,
    InternshipSchedule,
    InternshipReport,
    IndividualProgram,
    DocumentNumber,
)

from core.models.journal import (
    AssessmentResult,
    LearningOutcome,
    entry_outcomes,
    JournalEntry,
    OutcomeAssessment,
    CommitteeOutcomeEvaluation,
)

from core.models.documents import (
    DocumentAuditLog,
    UploadedDocument,
)

from core.models.agreements import (
    AgreementStatus,
    InternshipAgreement,
    AgreementEnrollment,
)

__all__ = [
    # uzytkownicy
    "UserRole",
    "UserRoleAssoc",
    "User",
    "Student",
    "Administrator",
    "UniversityMentor",
    "KomisjaUser",
    "DyrektorUser",
    "DziekanatUser",
    # firmy
    "Company",
    # praktyki
    "InternshipStatus",
    "EnrollmentStatus",
    "InternshipPath",
    "EventType",
    "Internship",
    "InternshipEnrollment",
    "WorkplaceDetails",
    "PathJustification",
    "Examination",
    "FinalGrades",
    "ProcessEvent",
    "InternshipSchedule",
    "InternshipReport",
    "IndividualProgram",
    "DocumentNumber",
    # dziennik
    "AssessmentResult",
    "LearningOutcome",
    "entry_outcomes",
    "JournalEntry",
    "OutcomeAssessment",
    "CommitteeOutcomeEvaluation",
    # dokumenty
    "DocumentAuditLog",
    "UploadedDocument",
    # porozumienia
    "AgreementStatus",
    "InternshipAgreement",
    "AgreementEnrollment",
]
