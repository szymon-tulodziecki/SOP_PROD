"""core/modele/uzytkownicy.py

Domain models: System users.
Joined Table Inheritance (JTI): shared `users` table extended by
Student, Administrator, and UniversityMentor subclasses.
"""
import uuid
import enum

from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import UUID

from core.extensions import db


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(enum.Enum):
    STUDENT = 'STUDENT'
    UOPZ    = 'UOPZ'
    ADMIN   = 'ADMIN'


# ── Base model ────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    """Shared table for all system accounts.

    Discriminator: `role` column — SQLAlchemy automatically returns
    the correct subclass when querying through the base class.
    """
    __tablename__ = 'users'
    __mapper_args__ = {
        'polymorphic_on':       'role',
        'polymorphic_identity': None,
    }

    id                       = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email                    = db.Column(db.String(255), unique=True, nullable=False)
    password_hash            = db.Column(db.String(255), nullable=False)
    first_name               = db.Column(db.String(100), nullable=False)
    last_name                = db.Column(db.String(100), nullable=False)
    role                     = db.Column(
        db.Enum(UserRole, name='user_role', values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    is_active                = db.Column(db.Boolean, default=True)
    require_password_change  = db.Column(db.Boolean, default=True)
    created_at               = db.Column(db.DateTime, server_default=db.func.now())

    def get_id(self) -> str:
        return str(self.id)

    # Flask-Login requires `is_active` as a property — already a column, works fine.

    @property
    def imie(self):
        return self.first_name

    @property
    def nazwisko(self):
        return self.last_name

    @property
    def rola(self):
        return self.role

    def __repr__(self) -> str:
        return f'<User {self.email} ({self.role})>'


# ── JTI subclasses ────────────────────────────────────────────────────────────

class Student(User):
    """Student-specific data — `students` table."""
    __tablename__ = 'students'

    id             = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    album_number   = db.Column(db.String(20),  nullable=True)
    gender         = db.Column(db.String(1),   nullable=True)   # 'M' or 'F'
    field_of_study = db.Column(db.String(100), nullable=True)
    specialization = db.Column(db.String(100), nullable=True)
    study_mode     = db.Column(db.String(20),  nullable=True)   # 'full-time'/'part-time'
    supervisor_id  = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    __mapper_args__ = {
        'polymorphic_identity': UserRole.STUDENT,
        'inherit_condition': id == User.__table__.c.id,
    }

    # Backward-compat shims used in routes/templates that haven't been updated yet
    @property
    def numer_albumu(self):
        return self.album_number

    @property
    def plec(self):
        return self.gender

    @property
    def kierunek(self):
        return self.field_of_study

    @property
    def specjalnosc(self):
        return self.specialization

    @property
    def tryb_studiow(self):
        return self.study_mode

    @property
    def uopz_id(self):
        return self.supervisor_id

    def __repr__(self) -> str:
        return f'<Student {self.email} album={self.album_number}>'


class Administrator(User):
    """Administrator account."""
    __tablename__ = 'administrators'
    __mapper_args__ = {'polymorphic_identity': UserRole.ADMIN}

    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)

    def __repr__(self) -> str:
        return f'<Administrator {self.email}>'


class UniversityMentor(User):
    """University Internship Supervisor (UOPZ)."""
    __tablename__ = 'university_mentors'
    __mapper_args__ = {'polymorphic_identity': UserRole.UOPZ}

    id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)

    def __repr__(self) -> str:
        return f'<UniversityMentor {self.email}>'


# ── Backward-compat aliases (remove after all routes migrated) ────────────────
Uzytkownik        = User
RolaUzytkownika   = UserRole
OpikunUczelniany  = UniversityMentor
