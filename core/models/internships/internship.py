"""Internship model â€” academic year and semester edition."""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from core.extensions import db
from core.models.internships._common import CASCADE_DELETE
from core.models.internships.enums import InternshipStatus


class Internship(db.Model):
    """Internship edition â€” academic year and semester."""
    __tablename__ = 'internships'

    id             = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    academic_year  = db.Column(db.String(9),  nullable=False)
    semester       = db.Column(db.String(10), nullable=False)
    required_hours = db.Column(db.Integer, nullable=False, default=160)
    status         = db.Column(
        db.Enum(InternshipStatus, name='internship_status', values_callable=lambda e: [x.value for x in e]),
        nullable=False, default=InternshipStatus.INACTIVE,
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    deleted_at = db.Column(db.DateTime, nullable=True, default=None)

    _SEMESTER_LABELS = {'winter': 'Zimowy', 'summer': 'Letni'}

    @property
    def semester_label(self) -> str:
        return self._SEMESTER_LABELS.get((self.semester or '').lower(), self.semester or '')

    enrollments = db.relationship(
        'InternshipEnrollment', backref='internship',
        lazy='select', cascade=CASCADE_DELETE, passive_deletes=True,
    )
