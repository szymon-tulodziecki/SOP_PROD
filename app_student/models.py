# app_student/models.py
import uuid
import enum
from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import UUID
from app_student.extensions import db


# ── Enums ─────────────────────────────────────────────────────────────────────

class RolaUzytkownika(enum.Enum):
    STUDENT = 'STUDENT'
    UOPZ    = 'UOPZ'
    ADMIN   = 'ADMIN'


class StatusPraktyki(enum.Enum):
    ACTIVE   = 'ACTIVE'
    INACTIVE = 'INACTIVE'


class StatusZapisu(enum.Enum):
    PENDING           = 'PENDING'
    AWAITING_APPROVAL = 'AWAITING_APPROVAL'
    IN_PROGRESS       = 'IN_PROGRESS'
    COMPLETED         = 'COMPLETED'


class SciezkaPraktyki(enum.Enum):
    STANDARD = 'STANDARD'
    EMPLOYMENT = 'EMPLOYMENT'
    OWN_BUSINESS = 'OWN_BUSINESS'


class WynikOceny(enum.Enum):
    OSIAGNIETO     = 'ACHIEVED'
    CZESCIOWO      = 'PARTIALLY_ACHIEVED'
    NIE_OSIAGNIETO = 'NOT_ACHIEVED'


# ── Modele ────────────────────────────────────────────────────────────────────

class Uzytkownik(UserMixin, db.Model):
    __tablename__ = 'users'

    id                    = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email                 = db.Column(db.String(255), unique=True, nullable=False)
    password_hash         = db.Column(db.String(255), nullable=False)
    first_name            = db.Column(db.String(100), nullable=False)
    last_name             = db.Column(db.String(100), nullable=False)
    album_number          = db.Column(db.String(20), nullable=True)
    role                  = db.Column(db.Enum(RolaUzytkownika, name='user_role', values_callable=lambda e: [x.value for x in e]), nullable=False)
    is_active             = db.Column(db.Boolean, default=True)
    wymagana_zmiana_hasla = db.Column(db.Boolean, default=True)
    created_at            = db.Column(db.DateTime, default=db.func.current_timestamp())

    def __repr__(self):
        return f'<User {self.email}>'


class EfektUczenia(db.Model):
    __tablename__ = 'learning_outcomes'

    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f'<EfektUczenia {self.id}: {self.description[:50]}...>'


class Praktyka(db.Model):
    __tablename__ = 'internships'

    id             = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rok_uczelniany = db.Column(db.String(9), nullable=False)
    semestr        = db.Column(db.String(10), nullable=False)
    wymiar_godzin  = db.Column(db.Integer, nullable=False, default=160)
    status         = db.Column(db.Enum(StatusPraktyki, name='internship_status', values_callable=lambda e: [x.value for x in e]), nullable=False, default=StatusPraktyki.INACTIVE)
    created_at     = db.Column(db.DateTime, default=db.func.current_timestamp())

    def __repr__(self):
        return f'<Praktyka {self.rok_uczelniany} {self.semestr}>'


class ZapisPraktyki(db.Model):
    __tablename__ = 'internship_enrollments'

    id                        = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    internship_id             = db.Column(UUID(as_uuid=True), db.ForeignKey('internships.id', ondelete='CASCADE'), nullable=False)
    student_id                = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    uopz_id                   = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    status                    = db.Column(db.Enum(StatusZapisu, name='enrollment_status', values_callable=lambda e: [x.value for x in e]), nullable=False, default=StatusZapisu.PENDING)
    track_type                = db.Column(db.Enum(SciezkaPraktyki, name='internship_track', values_callable=lambda e: [x.value for x in e]), nullable=False, default=SciezkaPraktyki.STANDARD)

    # Terminy i ogólne
    termin_od                 = db.Column(db.Date)
    termin_do                 = db.Column(db.Date)
    specjalnosc               = db.Column(db.String(255))
    ubezpieczenie_nw          = db.Column(db.Boolean, default=False)

    # Dane o firmie
    firma_nazwa               = db.Column(db.String(255))
    firma_adres               = db.Column(db.String(255))
    firma_miasto              = db.Column(db.String(255))
    firma_nip_krs             = db.Column(db.String(50))
    firma_upowazniony_osoba   = db.Column(db.String(255))
    firma_upowazniony_stanowisko = db.Column(db.String(255))

    # Dane ZOPZ
    zopz_imie_nazwisko        = db.Column(db.String(255))
    zopz_stanowisko           = db.Column(db.String(255))
    zopz_telefon              = db.Column(db.String(50))
    zopz_email                = db.Column(db.String(255))

    # Dodatki dla ścieżek
    uzasadnienie_sciezki      = db.Column(db.Text)
    zalaczniki_sciezki        = db.Column(db.Text)

    # Oceny
    ocena_sprawozdania        = db.Column(db.Numeric(3, 1))
    ocena_uopz                = db.Column(db.Numeric(3, 1))
    ocena_zopz                = db.Column(db.Numeric(3, 1))
    ocena_opisowa_uopz        = db.Column(db.Text)
    ocena_opisowa_zopz        = db.Column(db.Text)

    # Sprawdzian
    sprawdzian_pytanie_1      = db.Column(db.Text)
    sprawdzian_ocena_1        = db.Column(db.Numeric(3, 1))
    sprawdzian_pytanie_2      = db.Column(db.Text)
    sprawdzian_ocena_2        = db.Column(db.Numeric(3, 1))
    sprawdzian_pytanie_3      = db.Column(db.Text)
    sprawdzian_ocena_3        = db.Column(db.Numeric(3, 1))

    total_hours_logged        = db.Column(db.Integer, default=0)
    enrolled_at               = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relacje
    praktyka = db.relationship('Praktyka', backref='zapisy')
    student = db.relationship('Uzytkownik', foreign_keys=[student_id], backref='zapisy_studenta')
    uopz = db.relationship('Uzytkownik', foreign_keys=[uopz_id], backref='zapisy_uopz')

    __table_args__ = (db.UniqueConstraint('internship_id', 'student_id', name='_internship_student_uc'),)

    def __repr__(self):
        return f'<ZapisPraktyki {self.student.last_name if self.student else "?"} -> {self.praktyka.rok_uczelniany if self.praktyka else "?"}>'


class HarmonogramPraktyki(db.Model):
    __tablename__ = 'internship_schedule'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)
    nazwa_dzialu        = db.Column(db.String(255), nullable=False)
    przykladowe_prace   = db.Column(db.Text, nullable=False)
    liczba_dni          = db.Column(db.Integer, nullable=False, default=0)

    # Relacje
    zapis = db.relationship('ZapisPraktyki', backref='harmonogram')
    efekt_uczenia = db.relationship('EfektUczenia')


class SprawozdaniePraktyki(db.Model):
    __tablename__ = 'internship_reports'

    id                      = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id           = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False, unique=True)
    charakterystyka_miejsca = db.Column(db.Text)
    opis_i_analiza          = db.Column(db.Text)
    updated_at              = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Relacje
    zapis = db.relationship('ZapisPraktyki', backref=db.backref('sprawozdanie', uselist=False))


class WpisDziennika(db.Model):
    __tablename__ = 'journal_entries'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    entry_date          = db.Column(db.Date, nullable=False)
    duration_hours      = db.Column(db.Integer, nullable=False)
    description         = db.Column(db.Text, nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)

    # Relacje
    zapis = db.relationship('ZapisPraktyki', backref='wpisy_dziennika')
    efekt_uczenia = db.relationship('EfektUczenia')

    __table_args__ = (db.UniqueConstraint('enrollment_id', 'entry_date', name='_enrollment_date_uc'),)

    def __repr__(self):
        return f'<WpisDziennika {self.entry_date} - {self.duration_hours}h>'


class OcenaEfektu(db.Model):
    __tablename__ = 'internship_evaluations'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)
    result              = db.Column(db.Enum(WynikOceny, name='evaluation_result', values_callable=lambda e: [x.value for x in e]), nullable=False)
    evaluator_notes     = db.Column(db.Text)

    # Relacje
    zapis = db.relationship('ZapisPraktyki', backref='oceny_efektow')
    efekt_uczenia = db.relationship('EfektUczenia')