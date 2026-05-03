"""Satellite entities for an InternshipEnrollment.

WorkplaceDetails, PathJustification, Examination, FinalGrades,
ProcessEvent, InternshipSchedule, InternshipReport, IndividualProgram,
DocumentNumber.
"""
import uuid

from sqlalchemy.dialects.postgresql import UUID

from core.extensions import db
from core.modele.internships._common import FK_ENROLLMENTS, FK_USERS, ON_SET_NULL
from core.modele.internships.enums import EventType


class WorkplaceDetails(db.Model):
    """Snapshot of workplace and mentor data copied from the enrollment form."""
    __tablename__ = 'workplace_details'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)

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
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)
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
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)

    question_1 = db.Column(db.Text,          nullable=True)
    grade_1    = db.Column(db.Numeric(3, 1), nullable=True)
    question_2 = db.Column(db.Text,          nullable=True)
    grade_2    = db.Column(db.Numeric(3, 1), nullable=True)
    question_3 = db.Column(db.Text,          nullable=True)
    grade_3    = db.Column(db.Numeric(3, 1), nullable=True)

    commission_chair    = db.Column(db.String(200), nullable=True)
    commission_member_2 = db.Column(db.String(200), nullable=True)
    commission_member_3 = db.Column(db.String(200), nullable=True)

    enrollment = db.relationship('InternshipEnrollment', back_populates='examination')

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
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)

    report_grade                  = db.Column(db.Numeric(3, 1), nullable=True)
    supervisor_grade              = db.Column(db.Numeric(3, 1), nullable=True)
    workplace_grade               = db.Column(db.Numeric(3, 1), nullable=True)
    supervisor_grade_description  = db.Column(db.Text,          nullable=True)
    workplace_grade_description   = db.Column(db.Text,          nullable=True)

    enrollment = db.relationship('InternshipEnrollment', back_populates='final_grades')

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
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False)
    event_type    = db.Column(
        db.Enum(EventType, name='event_type', values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    decision       = db.Column(db.String(20), nullable=True)
    comment        = db.Column(db.Text,       nullable=True)
    executed_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_USERS, ondelete=ON_SET_NULL), nullable=True)
    executed_at    = db.Column(db.DateTime,   server_default=db.func.now())

    enrollment   = db.relationship('InternshipEnrollment', back_populates='process_events')
    executed_by  = db.relationship('User', foreign_keys=[executed_by_id], lazy='select')

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
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False)
    learning_outcome_id = db.Column('outcome_id', db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)
    department_name     = db.Column(db.String(255), nullable=False)
    example_tasks       = db.Column(db.Text,        nullable=False)
    days_count          = db.Column(db.Integer,     nullable=False, default=0)

    learning_outcome = db.relationship('LearningOutcome', lazy='select')

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

    id                    = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id         = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)
    workplace_description = db.Column(db.Text,     nullable=True)
    analysis              = db.Column(db.Text,     nullable=True)
    skills                = db.Column(db.Text,     nullable=True)
    updated_at            = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

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
    enrollment_id            = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False, unique=True)
    status                   = db.Column(db.String(30), nullable=False, default='DRAFT')
    approved_by_supervisor   = db.Column(db.Boolean,   default=False)
    approved_at              = db.Column(db.DateTime,  nullable=True)
    supervisor_comment       = db.Column(db.Text,      nullable=True)
    created_at               = db.Column(db.DateTime,  server_default=db.func.now())

    enrollment = db.relationship('InternshipEnrollment', backref=db.backref('individual_program', passive_deletes=True))

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
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey(FK_ENROLLMENTS, ondelete='CASCADE'), nullable=False)
    document_type = db.Column(db.String(50),  nullable=False)
    number        = db.Column(db.String(100), nullable=False)
    generated_at  = db.Column(db.DateTime,   server_default=db.func.now())

    enrollment = db.relationship('InternshipEnrollment')

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
