"""core/modele/uzytkownicy.py

Modele domenowe: Użytkownicy systemu.
Joined Table Inheritance (JTI): wspólna tabela uzytkownicy,
rozszerzona przez Studenta, Administratora i OpikunaUczelnianego.
"""
import uuid
import enum

from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import UUID

from core.extensions import db


# ── Enumy dziedziny użytkowników ─────────────────────────────────────────────

class RolaUzytkownika(enum.Enum):
    STUDENT      = 'STUDENT'
    UOPZ         = 'UOPZ'
    ADMIN        = 'ADMIN'


# ── Klasa bazowa ─────────────────────────────────────────────────────────────

class Uzytkownik(UserMixin, db.Model):
    """Wspólna tabela wszystkich kont w systemie.

    Discriminator: kolumna `rola` — SQLAlchemy automatycznie
    zwraca właściwą podklasę przy zapytaniu przez klasę bazową.
    """
    __tablename__ = 'uzytkownicy'
    __mapper_args__ = {
        'polymorphic_on':       'rola',
        'polymorphic_identity': None,
    }

    id                    = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email                 = db.Column(db.String(255), unique=True, nullable=False)
    hash_hasla            = db.Column('hash_hasla', db.String(255), nullable=False)
    imie                  = db.Column('imie', db.String(100), nullable=False)
    nazwisko              = db.Column('nazwisko', db.String(100), nullable=False)
    rola                  = db.Column(
        'rola',
        db.Enum(RolaUzytkownika, name='rola_uzytkownika', values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    aktywny               = db.Column('aktywny', db.Boolean, default=True)
    wymagana_zmiana_hasla = db.Column(db.Boolean, default=True)
    utworzono             = db.Column('utworzono', db.DateTime, server_default=db.func.now())

    # ── Compat z istniejącym kodem (Flask-Login, szablony) ───────────────────

    @property
    def password_hash(self):
        return self.hash_hasla

    @password_hash.setter
    def password_hash(self, v):
        self.hash_hasla = v

    @property
    def first_name(self):
        return self.imie

    @first_name.setter
    def first_name(self, v):
        self.imie = v

    @property
    def last_name(self):
        return self.nazwisko

    @last_name.setter
    def last_name(self, v):
        self.nazwisko = v

    @property
    def role(self):
        return self.rola

    @role.setter
    def role(self, v):
        self.rola = v

    @property
    def is_active(self):
        return self.aktywny

    @is_active.setter
    def is_active(self, v):
        self.aktywny = v

    @property
    def created_at(self):
        return self.utworzono

    def get_id(self) -> str:
        return str(self.id)

    def __repr__(self) -> str:
        return f'<Uzytkownik {self.email} ({self.rola})>'


# ── Podklasy per rola — JTI ──────────────────────────────────────────────────

class Student(Uzytkownik):
    """Dane specyficzne dla studenta — tabela studenci."""
    __tablename__ = 'studenci'
    __mapper_args__ = {'polymorphic_identity': RolaUzytkownika.STUDENT}

    id           = db.Column(UUID(as_uuid=True), db.ForeignKey('uzytkownicy.id', ondelete='CASCADE'), primary_key=True)
    numer_albumu = db.Column('numer_albumu', db.String(20),  nullable=True)
    plec         = db.Column('plec',         db.String(1),   nullable=True)   # 'M' lub 'K'
    kierunek     = db.Column('kierunek',     db.String(100), nullable=True)
    specjalnosc  = db.Column('specjalnosc',  db.String(100), nullable=True)
    tryb_studiow = db.Column('tryb_studiow', db.String(20),  nullable=True)   # 'stacjonarne'/'niestacjonarne'

    # Compat
    @property
    def album_number(self):
        return self.numer_albumu

    @album_number.setter
    def album_number(self, v):
        self.numer_albumu = v

    def __repr__(self) -> str:
        return f'<Student {self.email} nr={self.numer_albumu}>'


class Administrator(Uzytkownik):
    """Konto administratora systemu."""
    __tablename__ = 'administratorzy'
    __mapper_args__ = {'polymorphic_identity': RolaUzytkownika.ADMIN}

    id = db.Column(UUID(as_uuid=True), db.ForeignKey('uzytkownicy.id', ondelete='CASCADE'), primary_key=True)

    def __repr__(self) -> str:
        return f'<Administrator {self.email}>'


class OpikunUczelniany(Uzytkownik):
    """Uczelniany Opiekun Praktyk Zawodowych (UOPZ)."""
    __tablename__ = 'opiekunowie_uczelniani'
    __mapper_args__ = {'polymorphic_identity': RolaUzytkownika.UOPZ}

    id = db.Column(UUID(as_uuid=True), db.ForeignKey('uzytkownicy.id', ondelete='CASCADE'), primary_key=True)

    def __repr__(self) -> str:
        return f'<OpikunUczelniany {self.email}>'
