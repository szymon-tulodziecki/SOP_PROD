"""core/modele/dziennik.py

Domain models: Internship journal, learning outcomes, assessments.
"""
import uuid
import enum

from sqlalchemy.dialects.postgresql import UUID
from core.extensions import db


class AssessmentResult(enum.Enum):
    ACHIEVED            = 'ACHIEVED'
    PARTIALLY_ACHIEVED  = 'PARTIALLY_ACHIEVED'
    NOT_ACHIEVED        = 'NOT_ACHIEVED'


class LearningOutcome(db.Model):
    """Learning outcomes — reference dictionary table."""
    __tablename__ = 'learning_outcomes'

    id          = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)

    @property
    def kod(self) -> str:
        return str(self.id).zfill(2)

    # Backward-compat
    @property
    def opis(self):
        return self.description


# Junction table: journal_entry ↔ learning_outcomes
entry_outcomes = db.Table(
    'entry_outcomes',
    db.Column(
        'entry_id',
        UUID(as_uuid=True),
        db.ForeignKey('journal_entries.id', ondelete='CASCADE'),
        primary_key=True,
    ),
    db.Column(
        'outcome_id',
        db.Integer,
        db.ForeignKey('learning_outcomes.id'),
        primary_key=True,
    ),
)


class JournalEntry(db.Model):
    """A single journal entry for a student's internship."""
    __tablename__ = 'journal_entries'

    id             = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id  = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    entry_date     = db.Column(db.Date,    nullable=False)
    duration_hours = db.Column(db.Integer, nullable=False)
    description    = db.Column(db.Text,    nullable=False)

    learning_outcomes = db.relationship('LearningOutcome', secondary=entry_outcomes, lazy='subquery')

    # Backward-compat shims
    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def data_wpisu(self):
        return self.entry_date

    @property
    def liczba_godzin(self):
        return self.duration_hours

    @property
    def opis(self):
        return self.description

    @property
    def efekty_uczenia(self):
        return self.learning_outcomes

    @efekty_uczenia.setter
    def efekty_uczenia(self, value):
        self.learning_outcomes = value


class OutcomeAssessment(db.Model):
    """Assessment of a single learning outcome for one enrollment."""
    __tablename__ = 'outcome_assessments'

    id                 = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id      = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)
    result             = db.Column(
        db.Enum(AssessmentResult, name='assessment_result', values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    notes = db.Column(db.Text, nullable=True)

    learning_outcome = db.relationship('LearningOutcome', lazy='select')

    # Backward-compat shims
    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def efekt_id(self):
        return self.learning_outcome_id

    @property
    def wynik(self):
        return self.result

    @wynik.setter
    def wynik(self, v):
        self.result = v

    @property
    def uwagi(self):
        return self.notes

    @property
    def efekt(self):
        return self.learning_outcome


# Backward-compat aliases
WynikOceny    = AssessmentResult
EfektUczenia  = LearningOutcome
WpisDziennika = JournalEntry
OcenaPraktyki = OutcomeAssessment
wpisy_efekty  = entry_outcomes
