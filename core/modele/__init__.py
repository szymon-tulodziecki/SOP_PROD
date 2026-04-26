"""core/modele/__init__.py

Exports all domain models.
Flask-Migrate (Alembic) must see every db.Model class
before it can generate migration scripts — hence the star-style imports.
"""

from core.modele.uzytkownicy import (
    UserRole,
    User,
    Student,
    Administrator,
    UniversityMentor,
    KomisjaUser,
    DyrektorUser,
)

from core.modele.firmy import (
    Company,
)

from core.modele.praktyki import (
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

from core.modele.dziennik import (
    AssessmentResult,
    LearningOutcome,
    entry_outcomes,
    JournalEntry,
    OutcomeAssessment,
    CommitteeOutcomeEvaluation,
)

from core.modele.dokumenty import (
    DocumentStatus,
    DocumentAuditLog,
    UploadedDocument,
)

__all__ = [
    # uzytkownicy
    'UserRole', 'User', 'Student', 'Administrator', 'UniversityMentor',
    'KomisjaUser', 'DyrektorUser',
    # firmy
    'Company',
    # praktyki
    'InternshipStatus', 'EnrollmentStatus', 'InternshipPath', 'EventType',
    'Internship', 'InternshipEnrollment',
    'WorkplaceDetails', 'PathJustification', 'Examination', 'FinalGrades',
    'ProcessEvent', 'InternshipSchedule', 'InternshipReport',
    'IndividualProgram', 'DocumentNumber',
    # dziennik
    'AssessmentResult', 'LearningOutcome', 'entry_outcomes',
    'JournalEntry', 'OutcomeAssessment', 'CommitteeOutcomeEvaluation',
    # dokumenty
    'DocumentStatus', 'DocumentAuditLog', 'UploadedDocument',
]
