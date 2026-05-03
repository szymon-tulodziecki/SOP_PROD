"""core/modele/dziennik.py

Modele domenowe: dziennik praktyki, efekty uczenia się i oceny.
"""
import uuid
import enum

from sqlalchemy.dialects.postgresql import UUID
from core.extensions import db

_FK_JOURNAL_ENTRIES  = 'journal_entries.id'
_FK_LEARNING_OUTCOMES = 'learning_outcomes.id'
_FK_ENROLLMENTS      = 'internship_enrollments.id'


class AssessmentResult(enum.Enum):
    ACHIEVED = 'ACHIEVED'
    PARTIALLY_ACHIEVED = 'PARTIALLY_ACHIEVED'
    NOT_ACHIEVED = 'NOT_ACHIEVED'


class LearningOutcome(db.Model):
    """Learning outcomes — reference dictionary table."""
    __tablename__ = 'learning_outcomes'

    id          = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)

    @property
    def code(self) -> str:
        return str(self.id).zfill(2)


# Tabela łącząca: journal_entry ↔ learning_outcomes
entry_outcomes = db.Table(
    'entry_outcomes',
    db.Column(
        'entry_id',
        UUID(as_uuid=True),
        db.ForeignKey(_FK_JOURNAL_ENTRIES, ondelete='CASCADE'),
        primary_key=True,
    ),
    db.Column(
        'outcome_id',
        db.Integer,
        db.ForeignKey(_FK_LEARNING_OUTCOMES),
        primary_key=True,
    ),
)


class JournalEntry(db.Model):
    """A single journal entry for a student's internship."""
    __tablename__ = 'journal_entries'

    id             = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id  = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False)
    entry_date     = db.Column(db.Date,    nullable=False)
    duration_hours = db.Column(db.Integer, nullable=False)
    description    = db.Column(db.Text,    nullable=False)

    learning_outcomes = db.relationship('LearningOutcome', secondary=entry_outcomes, lazy='subquery')

    __table_args__ = (
        db.UniqueConstraint('enrollment_id', 'entry_date', name='uq_journal_entry_enrollment_date'),
    )


class OutcomeAssessment(db.Model):
    """Assessment of a single learning outcome for one enrollment."""
    __tablename__ = 'outcome_assessments'

    id                 = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id      = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey(_FK_LEARNING_OUTCOMES), nullable=False)
    result             = db.Column(
        db.Enum(AssessmentResult, name='assessment_result', values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    notes = db.Column(db.Text, nullable=True)

    learning_outcome = db.relationship('LearningOutcome', lazy='select')


    @property
    def learning_outcome(self):
        return self.learning_outcome


class CommitteeOutcomeEvaluation(db.Model):
    """Commission's per-outcome evaluation (Załącznik 4a) for path B submissions."""
    __tablename__ = 'committee_outcome_evaluations'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey(_FK_LEARNING_OUTCOMES), nullable=False)
    result              = db.Column(
        db.Enum(AssessmentResult, name='assessment_result', values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    notes = db.Column(db.Text, nullable=True)

    learning_outcome = db.relationship('LearningOutcome', lazy='select')

    __table_args__ = (
        db.UniqueConstraint('enrollment_id', 'learning_outcome_id', name='uq_committee_outcome_enrollment'),
    )
