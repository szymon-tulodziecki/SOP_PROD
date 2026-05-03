"""Internship domain models package.

Public API re-exports â€” keep import paths stable for callers and Alembic.
Submodules:
  - enums:      InternshipStatus, EnrollmentStatus, InternshipPath, EventType
  - internship: Internship (academic edition)
  - enrollment: InternshipEnrollment (student enrollment + computed properties)
  - satellites: WorkplaceDetails, PathJustification, Examination, FinalGrades,
                ProcessEvent, InternshipSchedule, InternshipReport,
                IndividualProgram, DocumentNumber
"""
from core.models.internships.enums import (
    EnrollmentStatus,
    EventType,
    InternshipPath,
    InternshipStatus,
)
from core.models.internships.internship import Internship
from core.models.internships.enrollment import InternshipEnrollment
from core.models.internships.satellites import (
    DocumentNumber,
    Examination,
    FinalGrades,
    IndividualProgram,
    InternshipReport,
    InternshipSchedule,
    PathJustification,
    ProcessEvent,
    WorkplaceDetails,
)

__all__ = [
    'InternshipStatus', 'EnrollmentStatus', 'InternshipPath', 'EventType',
    'Internship', 'InternshipEnrollment',
    'WorkplaceDetails', 'PathJustification', 'Examination', 'FinalGrades',
    'ProcessEvent', 'InternshipSchedule', 'InternshipReport',
    'IndividualProgram', 'DocumentNumber',
]
