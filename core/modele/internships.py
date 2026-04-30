"""core/modele/praktyki.py

Domain models: Internships, enrollments, and satellite entities.
"""
import uuid
import enum

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property

from core.extensions import db

# ── Stałe ─────────────────────────────────────────────────────────────────────
_CASCADE_DELETE = 'all, delete-orphan'
_FK_USERS       = 'users.id'
_FK_ENROLLMENTS = 'internship_enrollments.id'
_ON_SET_NULL    = 'SET NULL'

# ── Enums ─────────────────────────────────────────────────────────────────────

class InternshipStatus(enum.Enum):
    ACTIVE = 'ACTIVE'
    INACTIVE = 'INACTIVE'


class EnrollmentStatus(enum.Enum):
    PENDING = 'PENDING'
    AWAITING_APPROVAL = 'AWAITING_APPROVAL'
    REVISION_REQUIRED = 'REVISION_REQUIRED'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED = 'COMPLETED'
    REJECTED = 'REJECTED'
    COMMISSION_REVIEW = 'COMMISSION_REVIEW'
    DIRECTOR_APPROVAL = 'DIRECTOR_APPROVAL'


class InternshipPath(enum.Enum):
    STANDARD = 'STANDARD'
    EMPLOYMENT = 'EMPLOYMENT'
    OWN_BUSINESS = 'OWN_BUSINESS'


class EventType(enum.Enum):
    ADMIN_COMMENT = 'ADMIN_KOMENTARZ'
    SUPERVISOR_COMMENT = 'UOPZ_KOMENTARZ'
    STUDENT_NOTIFICATION = 'POWIADOMIENIE_STUDENTA'
    COMMITTEE_DECISION = 'KOMISJA_DECYZJA'
    DIRECTOR_DECISION = 'DYREKTOR_DECYZJA'


# ── Core models ───────────────────────────────────────────────────────────────

class Internship(db.Model):
    """Internship edition — academic year and semester."""
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
        lazy='select', cascade=_CASCADE_DELETE, passive_deletes=True,
    )



class InternshipEnrollment(db.Model):
    """Core student enrollment record."""
    __tablename__ = 'internship_enrollments'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    internship_id = db.Column(UUID(as_uuid=True), db.ForeignKey('internships.id',  ondelete='CASCADE'), nullable=False)
    student_id    = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_USERS,        ondelete='CASCADE'), nullable=False)
    supervisor_id = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_USERS,        ondelete=_ON_SET_NULL), nullable=True)
    company_id    = db.Column(UUID(as_uuid=True), db.ForeignKey('companies.id',    ondelete=_ON_SET_NULL), nullable=True)

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

    # ── Relationships ──────────────────────────────────────────
    student          = db.relationship('User',              foreign_keys=[student_id],   lazy='select')
    uopz             = db.relationship('User',              foreign_keys=[supervisor_id], lazy='select')
    firma            = db.relationship('Company',           foreign_keys=[company_id],   lazy='select')
    workplace_details = db.relationship('WorkplaceDetails', back_populates='enrollment', uselist=False, cascade=_CASCADE_DELETE)
    path_justification = db.relationship('PathJustification', back_populates='enrollment', uselist=False, cascade=_CASCADE_DELETE)
    examination      = db.relationship('Examination',       back_populates='enrollment', uselist=False, cascade=_CASCADE_DELETE)
    final_grades     = db.relationship('FinalGrades',       back_populates='enrollment', uselist=False, cascade=_CASCADE_DELETE)
    process_events   = db.relationship('ProcessEvent',      back_populates='enrollment', lazy='select', cascade=_CASCADE_DELETE, order_by='ProcessEvent.executed_at')
    journal_entries  = db.relationship('JournalEntry',      backref='enrollment',        lazy='select', cascade=_CASCADE_DELETE)
    outcome_assessments = db.relationship('OutcomeAssessment', backref='enrollment',     lazy='select', cascade=_CASCADE_DELETE)
    schedule         = db.relationship('InternshipSchedule', backref='enrollment',       lazy='select', cascade=_CASCADE_DELETE)
    report           = db.relationship('InternshipReport',  backref='enrollment',        uselist=False, lazy='select', cascade=_CASCADE_DELETE)

    # ── Backward-compat property shims ────────────────────────

    @property
    def praktyka_id(self):
        return self.internship_id

    @property
    def praktyka(self):
        return self.internship

    @property
    def uopz_id(self):
        return self.supervisor_id

    @uopz_id.setter
    def uopz_id(self, v):
        self.supervisor_id = v

    @property
    def firma_id(self):
        return self.company_id

    @firma_id.setter
    def firma_id(self, v):
        self.company_id = v

    @property
    def sciezka(self):
        return self.path_type

    @sciezka.setter
    def sciezka(self, v):
        self.path_type = v

    @property
    def track_type(self):
        return self.path_type

    @track_type.setter
    def track_type(self, v):
        self.path_type = v

    @property
    def specjalnosc(self):
        return self.specialization

    @specjalnosc.setter
    def specjalnosc(self, v):
        self.specialization = v

    @property
    def dane_miejsca(self):
        return self.workplace_details

    @property
    def uzasadnienie(self):
        return self.path_justification

    @property
    def sprawdzian(self):
        return self.examination

    @property
    def oceny_koncowe(self):
        return self.final_grades

    @property
    def zdarzenia(self):
        return self.process_events

    @property
    def wpisy_dziennika(self):
        return self.journal_entries

    @property
    def oceny(self):
        return self.outcome_assessments

    @property
    def harmonogram(self):
        return self.schedule

    @property
    def sprawozdanie(self):
        return self.report

    # ── Shortcuts to satellite entity data ────────────────────

    @property
    def firma_nazwa(self):
        if self.company_id and self.firma:
            return self.firma.name
        return self.workplace_details.company_name if self.workplace_details else None

    @property
    def firma_adres(self):
        if self.company_id and self.firma:
            return self.firma.address
        return self.workplace_details.company_address if self.workplace_details else None

    @property
    def firma_miasto(self):
        if self.company_id and self.firma:
            return self.firma.city
        return self.workplace_details.company_city if self.workplace_details else None

    @property
    def firma_nip_krs(self):
        if self.company_id and self.firma:
            return self.firma.tax_id
        return self.workplace_details.company_tax_id if self.workplace_details else None

    @property
    def firma_upowazniony_osoba(self):
        return self.workplace_details.authorized_person if self.workplace_details else None

    @property
    def firma_upowazniony_stanowisko(self):
        return self.workplace_details.authorized_person_position if self.workplace_details else None

    @property
    def zopz_imie_nazwisko(self):
        return self.workplace_details.workplace_mentor_name if self.workplace_details else None

    @property
    def zopz_stanowisko(self):
        return self.workplace_details.workplace_mentor_position if self.workplace_details else None

    @property
    def zopz_telefon(self):
        return self.workplace_details.workplace_mentor_phone if self.workplace_details else None

    @property
    def zopz_email(self):
        return self.workplace_details.workplace_mentor_email if self.workplace_details else None

    @property
    def uzasadnienie_sciezki(self):
        return self.path_justification.justification if self.path_justification else None

    @property
    def zalaczniki_sciezki(self):
        return self.path_justification.attachments if self.path_justification else None

    @property
    def ocena_sprawozdania(self):
        return self.final_grades.report_grade if self.final_grades else None

    @property
    def ocena_uopz(self):
        return self.final_grades.supervisor_grade if self.final_grades else None

    @property
    def ocena_zopz(self):
        return self.final_grades.workplace_grade if self.final_grades else None

    @property
    def ocena_opisowa_uopz(self):
        return self.final_grades.supervisor_grade_description if self.final_grades else None

    @property
    def ocena_opisowa_zopz(self):
        return self.final_grades.workplace_grade_description if self.final_grades else None

    @property
    def sprawdzian_pytanie_1(self):
        return self.examination.question_1 if self.examination else None

    @property
    def sprawdzian_ocena_1(self):
        return self.examination.grade_1 if self.examination else None

    @property
    def sprawdzian_pytanie_2(self):
        return self.examination.question_2 if self.examination else None

    @property
    def sprawdzian_ocena_2(self):
        return self.examination.grade_2 if self.examination else None

    @property
    def sprawdzian_pytanie_3(self):
        return self.examination.question_3 if self.examination else None

    @property
    def sprawdzian_ocena_3(self):
        return self.examination.grade_3 if self.examination else None

    # ── Process event helpers ──────────────────────────────────

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

    # Backward-compat event property names
    @property
    def komentarze_admina(self):
        return self.admin_comments

    @property
    def komentarze_uopz(self):
        return self.supervisor_comments

    @property
    def decyzja_komisji(self):
        return self.committee_decision

    @property
    def komentarze_komisji(self):
        return self.committee_comment

    @property
    def decyzja_komisji_o(self):
        return self.committee_decision_at

    @property
    def decyzja_dyrektora(self):
        return self.dean_decision

    @property
    def komentarze_dyrektora(self):
        return self.dean_comment

    @property
    def decyzja_dyrektora_o(self):
        return self.dean_decision_at

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

    # ── Path helpers ───────────────────────────────────────────────

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
        """None gdy brak oceny, True gdy >= 3.0, False gdy < 3.0."""
        if self.final_grade is None:
            return None
        return float(self.final_grade) >= 3.0

    @property
    def is_custom_company(self) -> bool:
        """True gdy firma nie pochodzi z bazy (student wpisał ją ręcznie)."""
        return not self.company_id

    @property
    def firma_ma_umowe(self) -> bool:
        """True gdy firma posiada stałą umowę z uczelnią."""
        return bool(self.firma and self.firma.has_standing_agreement)

    @property
    def moze_pobrac_wydruki(self) -> bool:
        """True gdy zalogowane godziny osiągnęły wymagany wymiar."""
        if not self.internship or not self.internship.required_hours:
            return False
        return (self.total_hours_logged or 0) >= self.internship.required_hours

    @property
    def status_css_class(self) -> str:
        """Fragment klasy CSS dla statusu zapisu, np. 'draft' → 'status--draft'."""
        from core.tlumaczenia import status_css_class as _css
        return _css(self.status.value if self.status else '')

    @property
    def status_label(self) -> str:
        """Polska etykieta statusu zapisu."""
        from core.tlumaczenia import translate_status
        return translate_status(self.status.value if self.status else '')

    # Legacy computed grade aliases
    @hybrid_property
    def ocena_e(self):
        return self.exam_grade

    @hybrid_property
    def ocena_k(self):
        return self.final_grade


# ── Satellite entities ────────────────────────────────────────────────────────

class WorkplaceDetails(db.Model):
    """Snapshot of workplace and mentor data copied from the enrollment form."""
    __tablename__ = 'workplace_details'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)

    company_name                = db.Column(db.String(255), nullable=True)
    company_address             = db.Column(db.String(255), nullable=True)
    company_zip                 = db.Column(db.String(10),  nullable=True)
    company_city                = db.Column(db.String(255), nullable=True)
    company_tax_id              = db.Column(db.String(50),  nullable=True)
    authorized_person           = db.Column('company_authorized_person',   db.String(255), nullable=True)
    authorized_person_position  = db.Column('company_authorized_position', db.String(255), nullable=True)

    workplace_mentor_name     = db.Column('workplace_supervisor_name',     db.String(255), nullable=True)
    workplace_mentor_position = db.Column('workplace_supervisor_position', db.String(255), nullable=True)
    workplace_mentor_phone    = db.Column('workplace_supervisor_phone',    db.String(50),  nullable=True)
    workplace_mentor_email    = db.Column('workplace_supervisor_email',    db.String(255), nullable=True)

    enrollment = db.relationship('InternshipEnrollment', back_populates='workplace_details')

    # Backward-compat shims
    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def firma_nazwa(self):
        return self.company_name

    @firma_nazwa.setter
    def firma_nazwa(self, v):
        self.company_name = v

    @property
    def firma_adres(self):
        return self.company_address

    @firma_adres.setter
    def firma_adres(self, v):
        self.company_address = v

    @property
    def firma_miasto(self):
        return self.company_city

    @firma_miasto.setter
    def firma_miasto(self, v):
        self.company_city = v

    @property
    def firma_nip_krs(self):
        return self.company_tax_id

    @firma_nip_krs.setter
    def firma_nip_krs(self, v):
        self.company_tax_id = v

    @property
    def firma_upowazniony_osoba(self):
        return self.authorized_person

    @firma_upowazniony_osoba.setter
    def firma_upowazniony_osoba(self, v):
        self.authorized_person = v

    @property
    def firma_upowazniony_stanowisko(self):
        return self.authorized_person_position

    @firma_upowazniony_stanowisko.setter
    def firma_upowazniony_stanowisko(self, v):
        self.authorized_person_position = v

    @property
    def zopz_imie_nazwisko(self):
        return self.workplace_mentor_name

    @zopz_imie_nazwisko.setter
    def zopz_imie_nazwisko(self, v):
        self.workplace_mentor_name = v

    @property
    def zopz_stanowisko(self):
        return self.workplace_mentor_position

    @zopz_stanowisko.setter
    def zopz_stanowisko(self, v):
        self.workplace_mentor_position = v

    @property
    def zopz_telefon(self):
        return self.workplace_mentor_phone

    @zopz_telefon.setter
    def zopz_telefon(self, v):
        self.workplace_mentor_phone = v

    @property
    def zopz_email(self):
        return self.workplace_mentor_email

    @zopz_email.setter
    def zopz_email(self, v):
        self.workplace_mentor_email = v


class PathJustification(db.Model):
    """Justification for choosing path B or C (optional)."""
    __tablename__ = 'path_justifications'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)
    justification      = db.Column(db.Text,        nullable=True)
    attachments        = db.Column(db.Text,        nullable=True)
    employment_subtype = db.Column(db.String(20),  nullable=True)  # 'WORK' or 'INTERNSHIP'

    enrollment = db.relationship('InternshipEnrollment', back_populates='path_justification')

    # Backward-compat
    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def uzasadnienie(self):
        return self.justification

    @uzasadnienie.setter
    def uzasadnienie(self, v):
        self.justification = v

    @property
    def zalaczniki(self):
        return self.attachments

    @zalaczniki.setter
    def zalaczniki(self, v):
        self.attachments = v


class Examination(db.Model):
    """Three examination questions with grades (issued by supervisor)."""
    __tablename__ = 'examinations'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)

    question_1 = db.Column(db.Text,          nullable=True)
    grade_1    = db.Column(db.Numeric(3, 1), nullable=True)
    question_2 = db.Column(db.Text,          nullable=True)
    grade_2    = db.Column(db.Numeric(3, 1), nullable=True)
    question_3 = db.Column(db.Text,          nullable=True)
    grade_3    = db.Column(db.Numeric(3, 1), nullable=True)

    commission_chair    = db.Column(db.String(200), nullable=True)  # Przewodniczący Komisji
    commission_member_2 = db.Column(db.String(200), nullable=True)  # Członek 2
    commission_member_3 = db.Column(db.String(200), nullable=True)  # Członek 3

    enrollment = db.relationship('InternshipEnrollment', back_populates='examination')

    # Backward-compat
    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def pytanie_1(self):
        return self.question_1

    @property
    def ocena_1(self):
        return self.grade_1

    @property
    def pytanie_2(self):
        return self.question_2

    @property
    def ocena_2(self):
        return self.grade_2

    @property
    def pytanie_3(self):
        return self.question_3

    @property
    def ocena_3(self):
        return self.grade_3


class FinalGrades(db.Model):
    """Final component grades for an internship."""
    __tablename__ = 'final_grades'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)

    report_grade                  = db.Column(db.Numeric(3, 1), nullable=True)
    supervisor_grade              = db.Column(db.Numeric(3, 1), nullable=True)
    workplace_grade               = db.Column(db.Numeric(3, 1), nullable=True)
    supervisor_grade_description  = db.Column(db.Text,          nullable=True)
    workplace_grade_description   = db.Column(db.Text,          nullable=True)

    enrollment = db.relationship('InternshipEnrollment', back_populates='final_grades')

    # Backward-compat
    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def ocena_sprawozdania(self):
        return self.report_grade

    @property
    def ocena_uopz(self):
        return self.supervisor_grade

    @property
    def ocena_zopz(self):
        return self.workplace_grade

    @property
    def ocena_opisowa_uopz(self):
        return self.supervisor_grade_description

    @property
    def ocena_opisowa_zopz(self):
        return self.workplace_grade_description


class ProcessEvent(db.Model):
    """Workflow event log: comments, committee and dean decisions."""
    __tablename__ = 'process_events'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False)
    event_type    = db.Column(
        db.Enum(EventType, name='event_type', values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    decision       = db.Column(db.String(20), nullable=True)   # 'APPROVED' / 'REJECTED'
    comment        = db.Column(db.Text,       nullable=True)
    executed_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_USERS, ondelete=_ON_SET_NULL), nullable=True)
    executed_at    = db.Column(db.DateTime,   server_default=db.func.now())

    enrollment   = db.relationship('InternshipEnrollment', back_populates='process_events')
    executed_by  = db.relationship('User', foreign_keys=[executed_by_id], lazy='select')

    # Backward-compat
    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def typ(self):
        return self.event_type

    @property
    def decyzja(self):
        return self.decision

    @property
    def komentarz(self):
        return self.comment

    @property
    def wykonane_przez_id(self):
        return self.executed_by_id

    @property
    def wykonano_o(self):
        return self.executed_at

    @property
    def wykonane_przez(self):
        return self.executed_by


class InternshipSchedule(db.Model):
    """Schedule of learning outcome completion for one enrollment."""
    __tablename__ = 'internship_schedules'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False)
    learning_outcome_id = db.Column('outcome_id', db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)
    department_name     = db.Column(db.String(255), nullable=False)
    example_tasks       = db.Column(db.Text,        nullable=False)
    days_count          = db.Column(db.Integer,     nullable=False, default=0)

    learning_outcome = db.relationship('LearningOutcome', lazy='select')

    # Backward-compat
    @property
    def zapis_id(self):
        return self.enrollment_id

    @zapis_id.setter
    def zapis_id(self, v):
        self.enrollment_id = v

    @property
    def efekt_id(self):
        return self.learning_outcome_id

    @efekt_id.setter
    def efekt_id(self, v):
        self.learning_outcome_id = v

    @property
    def efekt(self):
        return self.learning_outcome

    @property
    def nazwa_dzialu(self):
        return self.department_name

    @nazwa_dzialu.setter
    def nazwa_dzialu(self, v):
        self.department_name = v

    @property
    def przykladowe_prace(self):
        return self.example_tasks

    @przykladowe_prace.setter
    def przykladowe_prace(self, v):
        self.example_tasks = v

    @property
    def liczba_dni(self):
        return self.days_count

    @liczba_dni.setter
    def liczba_dni(self, v):
        self.days_count = v


class InternshipReport(db.Model):
    """Student's internship report."""
    __tablename__ = 'internship_reports'

    id                   = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id        = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)
    workplace_description = db.Column(db.Text,     nullable=True)
    analysis             = db.Column(db.Text,      nullable=True)
    skills               = db.Column(db.Text,      nullable=True)
    updated_at           = db.Column(db.DateTime,  server_default=db.func.now(), onupdate=db.func.now())

    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def charakterystyka_miejsca(self):
        return self.workplace_description

    @charakterystyka_miejsca.setter
    def charakterystyka_miejsca(self, v):
        self.workplace_description = v

    @property
    def opis_i_analiza(self):
        return self.analysis

    @opis_i_analiza.setter
    def opis_i_analiza(self, v):
        self.analysis = v

    @property
    def wiedza(self):
        return self.skills

    @wiedza.setter
    def wiedza(self, v):
        self.skills = v


class IndividualProgram(db.Model):
    """Individual internship program (optional)."""
    __tablename__ = 'individual_programs'

    id                       = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id            = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)
    status                   = db.Column(db.String(30), nullable=False, default='DRAFT')
    approved_by_supervisor   = db.Column(db.Boolean,   default=False)
    approved_at              = db.Column(db.DateTime,   nullable=True)
    supervisor_comment       = db.Column(db.Text,       nullable=True)
    created_at               = db.Column(db.DateTime,   server_default=db.func.now())

    enrollment = db.relationship('InternshipEnrollment', backref=db.backref('individual_program', passive_deletes=True))

    # Backward-compat
    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def zatwierdzony_przez_uopz(self):
        return self.approved_by_supervisor

    @property
    def zatwierdzono_o(self):
        return self.approved_at

    @property
    def komentarz_uopz(self):
        return self.supervisor_comment


class DocumentNumber(db.Model):
    """Sequential administrative document number."""
    __tablename__ = 'document_numbers'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False)
    document_type = db.Column(db.String(50),  nullable=False)
    number        = db.Column(db.String(100), nullable=False)
    generated_at  = db.Column(db.DateTime,   server_default=db.func.now())

    enrollment = db.relationship('InternshipEnrollment')

    # Backward-compat
    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def typ_dokumentu(self):
        return self.document_type

    @property
    def numer(self):
        return self.number

    @property
    def wygenerowano(self):
        return self.generated_at
