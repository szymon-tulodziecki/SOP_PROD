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
    # backward-compat aliases
    RolaUzytkownika,
    Uzytkownik,
    OpikunUczelniany,
)

from core.modele.firmy import (
    Company,
    # backward-compat alias
    Firma,
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
    # backward-compat aliases
    StatusPraktyki,
    StatusZapisu,
    SciezkaPraktyki,
    TypZdarzenia,
    Praktyka,
    ZapisPraktyki,
    DaneMiejscaPraktyki,
    UzasadnienieSciezki,
    Sprawdzian,
    OcenyKoncowe,
    ZdarzenieProces,
    HarmonogramPraktyki,
    Sprawozdanie,
    IndywidualnyProgram,
    NumerPisma,
)

from core.modele.dziennik import (
    AssessmentResult,
    LearningOutcome,
    entry_outcomes,
    JournalEntry,
    OutcomeAssessment,
    # backward-compat aliases
    WynikOceny,
    EfektUczenia,
    wpisy_efekty,
    WpisDziennika,
    OcenaPraktyki,
)

from core.modele.dokumenty import (
    DocumentStatus,
    DocumentAuditLog,
    UploadedDocument,
    # backward-compat aliases
    StatusDokumentu,
    LogAudytuDokumentow,
    DokumentPrzeslany,
)

__all__ = [
    # uzytkownicy — English
    'UserRole', 'User', 'Student', 'Administrator', 'UniversityMentor',
    # uzytkownicy — compat
    'RolaUzytkownika', 'Uzytkownik', 'OpikunUczelniany',
    # firmy — English
    'Company',
    # firmy — compat
    'Firma',
    # praktyki — English
    'InternshipStatus', 'EnrollmentStatus', 'InternshipPath', 'EventType',
    'Internship', 'InternshipEnrollment',
    'WorkplaceDetails', 'PathJustification', 'Examination', 'FinalGrades',
    'ProcessEvent', 'InternshipSchedule', 'InternshipReport',
    'IndividualProgram', 'DocumentNumber',
    # praktyki — compat
    'StatusPraktyki', 'StatusZapisu', 'SciezkaPraktyki', 'TypZdarzenia',
    'Praktyka', 'ZapisPraktyki',
    'DaneMiejscaPraktyki', 'UzasadnienieSciezki', 'Sprawdzian', 'OcenyKoncowe',
    'ZdarzenieProces', 'HarmonogramPraktyki', 'Sprawozdanie',
    'IndywidualnyProgram', 'NumerPisma',
    # dziennik — English
    'AssessmentResult', 'LearningOutcome', 'entry_outcomes',
    'JournalEntry', 'OutcomeAssessment',
    # dziennik — compat
    'WynikOceny', 'EfektUczenia', 'wpisy_efekty', 'WpisDziennika', 'OcenaPraktyki',
    # dokumenty — English
    'DocumentStatus', 'DocumentAuditLog', 'UploadedDocument',
    # dokumenty — compat
    'StatusDokumentu', 'LogAudytuDokumentow', 'DokumentPrzeslany',
]
