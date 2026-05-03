"""InternshipEnrollment — student enrollment record with computed properties."""
import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property

from core.extensions import db
from core.models.internships._common import (
    CASCADE_DELETE,
    FK_USERS,
    ON_SET_NULL,
)
from core.models.internships.enums import (
    EnrollmentStatus,
    EventType,
    InternshipPath,
)


class InternshipEnrollment(db.Model):
    """Core student enrollment record."""
    __tablename__ = 'internship_enrollments'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    internship_id = db.Column(UUID(as_uuid=True), db.ForeignKey('internships.id', ondelete='CASCADE'), nullable=False)
    student_id    = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_USERS, ondelete='CASCADE'), nullable=False)
    supervisor_id = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_USERS, ondelete=ON_SET_NULL), nullable=True)
    company_id    = db.Column(UUID(as_uuid=True), db.ForeignKey('companies.id', ondelete=ON_SET_NULL), nullable=True)

    status = db.Column(
        db.Enum(EnrollmentStatus, name='enrollment_status', values_callable=lambda e: [x.value for x in e]),
        nullable=False, default=EnrollmentStatus.PENDING,
    )
    path_type = db.Column(
        db.Enum(InternshipPath, name='internship_path', values_callable=lambda e: [x.value for x in e]),
        nullable=False, default=InternshipPath.STANDARD,
    )

    start_date         = db.Column(db.Date,        nullable=True)
    end_date           = db.Column(db.Date,        nullable=True)
    specialization     = db.Column(db.String(255), nullable=True)
    accident_insurance = db.Column(db.Boolean,     default=False)
    total_hours_logged = db.Column(db.Integer,     default=0)
    enrolled_at        = db.Column(db.DateTime,    server_default=db.func.now())

    # ── Relacje ──────────────────────────────────────────
    student            = db.relationship('User',              foreign_keys=[student_id],   lazy='select')
    supervisor         = db.relationship('User',              foreign_keys=[supervisor_id], lazy='select')
    company            = db.relationship('Company',           foreign_keys=[company_id],   lazy='select')
    workplace_details  = db.relationship('WorkplaceDetails',  back_populates='enrollment', uselist=False, cascade=CASCADE_DELETE)
    path_justification = db.relationship('PathJustification', back_populates='enrollment', uselist=False, cascade=CASCADE_DELETE)
    examination        = db.relationship('Examination',       back_populates='enrollment', uselist=False, cascade=CASCADE_DELETE)
    final_grades       = db.relationship('FinalGrades',       back_populates='enrollment', uselist=False, cascade=CASCADE_DELETE)
    process_events     = db.relationship('ProcessEvent',      back_populates='enrollment', lazy='select', cascade=CASCADE_DELETE, order_by='ProcessEvent.executed_at')
    journal_entries    = db.relationship('JournalEntry',      backref='enrollment',        lazy='select', cascade=CASCADE_DELETE)
    outcome_assessments = db.relationship('OutcomeAssessment', backref='enrollment',       lazy='select', cascade=CASCADE_DELETE)
    schedule           = db.relationship('InternshipSchedule', backref='enrollment',       lazy='select', cascade=CASCADE_DELETE)
    report             = db.relationship('InternshipReport',  backref='enrollment',        uselist=False, lazy='select', cascade=CASCADE_DELETE)

    # ── Skróty do danych encji powiązanych ────────────────────

    @property
    def company_display_name(self):
        if self.company_id and self.company:
            return self.company.name
        return self.workplace_details.company_name if self.workplace_details else None

    @property
    def company_display_address(self):
        if self.company_id and self.company:
            return self.company.address
        return self.workplace_details.company_address if self.workplace_details else None

    @property
    def company_city(self):
        if self.company_id and self.company:
            return self.company.city
        return self.workplace_details.company_city if self.workplace_details else None

    @property
    def company_display_tax_id(self):
        if self.company_id and self.company:
            return self.company.tax_id
        return self.workplace_details.company_tax_id if self.workplace_details else None

    @property
    def authorized_person(self):
        return self.workplace_details.authorized_person if self.workplace_details else None

    @property
    def authorized_person_position(self):
        return self.workplace_details.authorized_person_position if self.workplace_details else None

    @property
    def workplace_mentor_name(self):
        return self.workplace_details.workplace_mentor_name if self.workplace_details else None

    @property
    def workplace_mentor_position(self):
        return self.workplace_details.workplace_mentor_position if self.workplace_details else None

    @property
    def workplace_mentor_phone(self):
        return self.workplace_details.workplace_mentor_phone if self.workplace_details else None

    @property
    def workplace_mentor_email(self):
        return self.workplace_details.workplace_mentor_email if self.workplace_details else None

    @property
    def path_justification_text(self):
        return self.path_justification.justification if self.path_justification else None

    @property
    def path_attachments(self):
        return self.path_justification.attachments if self.path_justification else None

    @property
    def report_grade(self):
        return self.final_grades.report_grade if self.final_grades else None

    @property
    def supervisor_grade(self):
        return self.final_grades.supervisor_grade if self.final_grades else None

    @property
    def workplace_grade(self):
        return self.final_grades.workplace_grade if self.final_grades else None

    @property
    def supervisor_grade_description(self):
        return self.final_grades.supervisor_grade_description if self.final_grades else None

    @property
    def workplace_grade_description(self):
        return self.final_grades.workplace_grade_description if self.final_grades else None

    @property
    def exam_question_1(self):
        return self.examination.question_1 if self.examination else None

    @property
    def exam_grade_1(self):
        return self.examination.grade_1 if self.examination else None

    @property
    def exam_question_2(self):
        return self.examination.question_2 if self.examination else None

    @property
    def exam_grade_2(self):
        return self.examination.grade_2 if self.examination else None

    @property
    def exam_question_3(self):
        return self.examination.question_3 if self.examination else None

    @property
    def exam_grade_3(self):
        return self.examination.grade_3 if self.examination else None

    # ── Metody pomocnicze zdarzeń procesu ──────────────────────────────────

    def _last_event(self, event_type: EventType):
        return next(
            (e for e in reversed(self.process_events) if e.event_type == event_type),
            None,
        )

    @property
    def committee_decision(self):
        e = self._last_event(EventType.COMMITTEE_DECISION)
        return e.decision if e else None

    @property
    def committee_comment(self):
        e = self._last_event(EventType.COMMITTEE_DECISION)
        return e.comment if e else None

    @property
    def committee_decision_at(self):
        e = self._last_event(EventType.COMMITTEE_DECISION)
        return e.executed_at if e else None

    @property
    def dean_decision(self):
        e = self._last_event(EventType.DIRECTOR_DECISION)
        return e.decision if e else None

    @property
    def dean_comment(self):
        e = self._last_event(EventType.DIRECTOR_DECISION)
        return e.comment if e else None

    @property
    def dean_decision_at(self):
        e = self._last_event(EventType.DIRECTOR_DECISION)
        return e.executed_at if e else None

    @property
    def admin_comments(self):
        e = self._last_event(EventType.ADMIN_COMMENT)
        return e.comment if e else None

    @property
    def supervisor_comments(self):
        e = self._last_event(EventType.SUPERVISOR_COMMENT)
        return e.comment if e else None

    # ── Grade computations ─────────────────────────────────────

    @hybrid_property
    def exam_grade(self):
        """Average of examination scores."""
        if self.examination is None:
            return None
        grades = [
            float(v) for v in (
                self.examination.grade_1,
                self.examination.grade_2,
                self.examination.grade_3,
            ) if v is not None
        ]
        return round(sum(grades) / len(grades), 2) if grades else None

    @hybrid_property
    def final_grade(self):
        """Final grade: path A = 0.4E+0.1S+0.2U+0.3Z, path B = 0.9E+0.1S."""
        if self.final_grades is None:
            return None
        e = self.exam_grade
        s = float(self.final_grades.report_grade) if self.final_grades.report_grade is not None else None

        def _round_half(v):
            return round(round(v * 2) / 2, 1)

        if self.path_type in (InternshipPath.EMPLOYMENT, InternshipPath.OWN_BUSINESS):
            if None in (e, s):
                return None
            return _round_half(0.9 * e + 0.1 * s)
        u = float(self.final_grades.supervisor_grade) if self.final_grades.supervisor_grade is not None else None
        z = float(self.final_grades.workplace_grade)  if self.final_grades.workplace_grade  is not None else None
        if None in (e, s, u, z):
            return None
        return _round_half(0.4 * e + 0.1 * s + 0.2 * u + 0.3 * z)

    # ── Metody pomocnicze ścieżek ───────────────────────────────────────────────

    @property
    def is_path_b(self) -> bool:
        return self.path_type in (InternshipPath.EMPLOYMENT, InternshipPath.OWN_BUSINESS)

    @property
    def is_standard(self) -> bool:
        return self.path_type == InternshipPath.STANDARD

    @property
    def progress_percent(self) -> int:
        if not self.internship or not self.internship.required_hours:
            return 0
        return min(int(self.total_hours_logged / self.internship.required_hours * 100), 100)

    @property
    def is_completed_or_in_progress(self) -> bool:
        return self.status in (EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMPLETED)

    @property
    def is_in_progress(self) -> bool:
        return self.status == EnrollmentStatus.IN_PROGRESS

    @property
    def is_pending(self) -> bool:
        return self.status == EnrollmentStatus.PENDING

    @property
    def is_revision_required(self) -> bool:
        return self.status == EnrollmentStatus.REVISION_REQUIRED

    @property
    def final_grade_is_passing(self) -> bool | None:
        """None when no grade, True for >= 3.0, False for < 3.0."""
        if self.final_grade is None:
            return None
        return float(self.final_grade) >= 3.0

    @property
    def is_custom_company(self) -> bool:
        """True when the company is not from the database (manually entered)."""
        return not self.company_id

    @property
    def company_has_standing_agreement(self) -> bool:
        return bool(self.company and self.company.has_standing_agreement)

    @property
    def can_download_printouts(self) -> bool:
        if not self.internship or not self.internship.required_hours:
            return False
        return (self.total_hours_logged or 0) >= self.internship.required_hours

    @property
    def status_css_class(self) -> str:
        from core.translations import status_css_class as _css
        return _css(self.status.value if self.status else '')

    @property
    def status_label(self) -> str:
        from core.translations import translate_status
        return translate_status(self.status.value if self.status else '')
