import uuid
import enum
from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import UUID
from app_admin.extensions import db


# ── Enums ─────────────────────────────────────────────────────────────────────

class RolaUzytkownika(enum.Enum):
    STUDENT = 'STUDENT'
    UOPZ    = 'UOPZ'
    ADMIN   = 'ADMIN'


class StatusPraktyki(enum.Enum):
    ACTIVE   = 'ACTIVE'
    INACTIVE = 'INACTIVE'


class StatusZapisu(enum.Enum):
    PENDING     = 'PENDING'
    IN_PROGRESS = 'IN_PROGRESS'
    COMPLETED   = 'COMPLETED'


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
    created_at            = db.Column(db.DateTime, server_default=db.func.now())

    # Aliasy
    @property
    def imie(self): return self.first_name
    @imie.setter
    def imie(self, v): self.first_name = v

    @property
    def nazwisko(self): return self.last_name
    @nazwisko.setter
    def nazwisko(self, v): self.last_name = v

    @property
    def numer_albumu(self): return self.album_number
    @numer_albumu.setter
    def numer_albumu(self, v): self.album_number = v

    @property
    def rola(self): return self.role
    @rola.setter
    def rola(self, v): self.role = v

    @property
    def aktywny(self): return self.is_active
    @aktywny.setter
    def aktywny(self, v): self.is_active = v

    @property
    def hash_hasla(self): return self.password_hash
    @hash_hasla.setter
    def hash_hasla(self, v): self.password_hash = v

    def get_id(self):
        return str(self.id)


class Praktyka(db.Model):
    __tablename__ = 'internships'

    id             = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rok_uczelniany = db.Column(db.String(9), nullable=False)   # np. '2023/2024'
    semestr        = db.Column(db.String(10), nullable=False)  # 'zimowy' / 'letni'
    wymiar_godzin  = db.Column(db.Integer, nullable=False, default=160)
    status         = db.Column(db.Enum(StatusPraktyki, name='internship_status', values_callable=lambda e: [x.value for x in e]), nullable=False, default=StatusPraktyki.INACTIVE)
    created_at     = db.Column(db.DateTime, server_default=db.func.now())

    # Relacja do zapisów
    zapisy = db.relationship('ZapisPraktyki', backref='praktyka', lazy='select',
                             cascade='all, delete-orphan')


class ZapisPraktyki(db.Model):
    __tablename__ = 'internship_enrollments'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    internship_id = db.Column(UUID(as_uuid=True), db.ForeignKey('internships.id', ondelete='CASCADE'), nullable=False)
    student_id    = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    uopz_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    status        = db.Column(db.Enum(StatusZapisu, name='enrollment_status', values_callable=lambda e: [x.value for x in e]), nullable=False, default=StatusZapisu.PENDING)
    total_hours_logged = db.Column(db.Integer, default=0)
    enrolled_at   = db.Column(db.DateTime, server_default=db.func.now())

    # Relacje
    student = db.relationship('Uzytkownik', foreign_keys=[student_id], lazy='select')
    uopz    = db.relationship('Uzytkownik', foreign_keys=[uopz_id],    lazy='select')
    wpisy_dziennika = db.relationship('WpisDziennika', backref='zapis', lazy='select',
                                      cascade='all, delete-orphan')
    oceny = db.relationship('OcenaPraktyki', backref='zapis', lazy='select',
                            cascade='all, delete-orphan')

    @property
    def lacznie_godzin(self): return self.total_hours_logged


class EfektUczenia(db.Model):
    __tablename__ = 'learning_outcomes'

    id          = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)

    @property
    def opis(self): return self.description

    @property
    def kod(self): return str(self.id).zfill(2)


class WpisDziennika(db.Model):
    __tablename__ = 'journal_entries'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    entry_date          = db.Column(db.Date, nullable=False)
    duration_hours      = db.Column(db.Integer, nullable=False)
    description         = db.Column(db.Text, nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)

    efekt = db.relationship('EfektUczenia', lazy='select')

    @property
    def data_wpisu(self): return self.entry_date

    @property
    def liczba_godzin(self): return self.duration_hours

    @property
    def opis(self): return self.description

    @property
    def efekt_uczenia(self): return self.efekt


class OcenaPraktyki(db.Model):
    __tablename__ = 'internship_evaluations'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)
    result              = db.Column(db.Enum(WynikOceny, name='evaluation_result', values_callable=lambda e: [x.value for x in e]), nullable=False)
    evaluator_notes     = db.Column(db.Text, nullable=True)

    efekt = db.relationship('EfektUczenia', lazy='select')

    @property
    def wynik(self): return self.result
    @wynik.setter
    def wynik(self, v): self.result = v

    @property
    def uwagi_oceniajacego(self): return self.evaluator_notes
    @uwagi_oceniajacego.setter
    def uwagi_oceniajacego(self, v): self.evaluator_notes = v