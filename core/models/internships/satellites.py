"""Satellite entities for an InternshipEnrollment.

WorkplaceDetails, PathJustification, Examination, FinalGrades,
ProcessEvent, InternshipSchedule, InternshipReport, IndividualProgram,
DocumentNumber.
"""

import uuid

from sqlalchemy.dialects.postgresql import UUID

from core.extensions import db
from core.models.internships._common import FK_ENROLLMENTS, FK_USERS, ON_SET_NULL
from core.models.internships.enums import EventType


class WorkplaceDetails(db.Model):
    """Snapshot of workplace and mentor data copied from the enrollment form."""

    __tablename__ = "workplace_details"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey(FK_ENROLLMENTS, ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    company_name = db.Column(db.String(255), nullable=True)
    company_address = db.Column(db.String(255), nullable=True)
    company_zip = db.Column(db.String(10), nullable=True)
    company_city = db.Column(db.String(255), nullable=True)
    company_tax_id = db.Column(db.String(50), nullable=True)
    authorized_person = db.Column("company_authorized_person", db.String(255), nullable=True)
    authorized_person_position = db.Column(
        "company_authorized_position", db.String(255), nullable=True
    )
    authorized_person_email = db.Column("company_authorized_email", db.String(255), nullable=True)

    workplace_mentor_name = db.Column("workplace_supervisor_name", db.String(255), nullable=True)
    workplace_mentor_position = db.Column(
        "workplace_supervisor_position", db.String(255), nullable=True
    )
    workplace_mentor_phone = db.Column("workplace_supervisor_phone", db.String(50), nullable=True)
    workplace_mentor_email = db.Column("workplace_supervisor_email", db.String(255), nullable=True)

    enrollment = db.relationship("InternshipEnrollment", back_populates="workplace_details")


class PathJustification(db.Model):
    """Uzasadnienie wyboru ścieżki B albo C (opcjonalne)."""

    __tablename__ = "path_justifications"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey(FK_ENROLLMENTS, ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    justification = db.Column(db.Text, nullable=True)
    attachments = db.Column(db.Text, nullable=True)
    employment_subtype = db.Column(db.String(20), nullable=True)  # 'WORK' or 'INTERNSHIP'

    enrollment = db.relationship("InternshipEnrollment", back_populates="path_justification")


class Examination(db.Model):
    """Three examination questions with grades (issued by supervisor)."""

    __tablename__ = "examinations"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey(FK_ENROLLMENTS, ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    question_1 = db.Column(db.Text, nullable=True)
    grade_1 = db.Column(db.Numeric(3, 1), nullable=True)
    question_2 = db.Column(db.Text, nullable=True)
    grade_2 = db.Column(db.Numeric(3, 1), nullable=True)
    question_3 = db.Column(db.Text, nullable=True)
    grade_3 = db.Column(db.Numeric(3, 1), nullable=True)

    commission_chair = db.Column(db.String(200), nullable=True)
    commission_member_2 = db.Column(db.String(200), nullable=True)
    commission_member_3 = db.Column(db.String(200), nullable=True)

    enrollment = db.relationship("InternshipEnrollment", back_populates="examination")


class FinalGrades(db.Model):
    """Final component grades for an internship."""

    __tablename__ = "final_grades"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey(FK_ENROLLMENTS, ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    report_grade = db.Column(db.Numeric(3, 1), nullable=True)
    supervisor_grade = db.Column(db.Numeric(3, 1), nullable=True)
    workplace_grade = db.Column(db.Numeric(3, 1), nullable=True)
    supervisor_grade_description = db.Column(db.Text, nullable=True)
    workplace_grade_description = db.Column(db.Text, nullable=True)
    supervisor_notes = db.Column(db.Text, nullable=True)
    workplace_notes = db.Column(db.Text, nullable=True)

    enrollment = db.relationship("InternshipEnrollment", back_populates="final_grades")


class ProcessEvent(db.Model):
    """Workflow event log: comments, committee and dean decisions."""

    __tablename__ = "process_events"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete="CASCADE"), nullable=False
    )
    event_type = db.Column(
        db.Enum(EventType, name="event_type", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    decision = db.Column(db.String(20), nullable=True)
    comment = db.Column(db.Text, nullable=True)
    executed_by_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey(FK_USERS, ondelete=ON_SET_NULL), nullable=True
    )
    executed_at = db.Column(db.DateTime, server_default=db.func.now())

    enrollment = db.relationship("InternshipEnrollment", back_populates="process_events")
    executed_by = db.relationship("User", foreign_keys=[executed_by_id], lazy="select")


class InternshipSchedule(db.Model):
    """Schedule of learning outcome completion for one enrollment."""

    __tablename__ = "internship_schedules"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete="CASCADE"), nullable=False
    )
    learning_outcome_id = db.Column(
        "outcome_id", db.Integer, db.ForeignKey("learning_outcomes.id"), nullable=False
    )
    department_name = db.Column(db.String(255), nullable=False)
    example_tasks = db.Column(db.Text, nullable=False)
    days_count = db.Column(db.Integer, nullable=False, default=0)

    learning_outcome = db.relationship("LearningOutcome", lazy="select")


class InternshipReport(db.Model):
    """Student's internship report."""

    __tablename__ = "internship_reports"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey(FK_ENROLLMENTS, ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    workplace_description = db.Column(db.Text, nullable=True)
    analysis = db.Column(db.Text, nullable=True)
    skills = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())


class IndividualProgram(db.Model):
    """Individual internship program (optional)."""

    __tablename__ = "individual_programs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey(FK_ENROLLMENTS, ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status = db.Column(db.String(30), nullable=False, default="DRAFT")
    approved_by_supervisor = db.Column(db.Boolean, default=False)
    approved_at = db.Column(db.DateTime, nullable=True)
    supervisor_comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    enrollment = db.relationship(
        "InternshipEnrollment", backref=db.backref("individual_program", passive_deletes=True)
    )


class DocumentNumber(db.Model):
    """Sequential administrative document number."""

    __tablename__ = "document_numbers"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete="CASCADE"), nullable=False
    )
    document_type = db.Column(db.String(50), nullable=False)
    number = db.Column(db.String(100), nullable=False)
    generated_at = db.Column(db.DateTime, server_default=db.func.now())

    enrollment = db.relationship("InternshipEnrollment")
