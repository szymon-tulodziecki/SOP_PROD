"""core/modele/uzytkownicy.py

Domain models: System users.
Joined Table Inheritance (JTI): shared `users` table extended by
Student, Administrator, and UniversityMentor subclasses.
"""
import uuid
import enum

from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.associationproxy import association_proxy

from core.extensions import db

_FK_USERS = 'users.id'

# ─── Enums ──────────────────────────────────────────────────────────────────────

class UserRole(enum.Enum):
    STUDENT   = 'STUDENT'
    UOPZ      = 'UOPZ'
    KOMISJA   = 'KOMISJA'    # Przewodniczący komisji ds. praktyk
    DYREKTOR  = 'DYREKTOR'   # Dyrektor Instytutu — ostateczna akceptacja
    DZIEKANAT = 'DZIEKANAT'  # Dziekanat — porozumienia z zakładami pracy
    ADMIN     = 'ADMIN'


# ─── User ↔ Role association (M:N) ────────────────────────────────────────────

class UserRoleAssoc(db.Model):
    """Mapowanie wielu ról na jednego użytkownika (pracownicy)."""
    __tablename__ = 'user_roles'

    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey(_FK_USERS, ondelete='CASCADE'),
        primary_key=True,
    )
    role = db.Column(
        db.Enum(UserRole, name='user_role', values_callable=lambda e: [x.value for x in e],
                create_type=False),
        primary_key=True,
    )

    def __init__(self, role=None, **kw):
        super().__init__(**kw)
        if role is not None:
            self.role = role if isinstance(role, UserRole) else UserRole[role]


# ─── Base model ──────────────────────────────────────────────────────────────────

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

    _role_assocs = db.relationship(
        'UserRoleAssoc',
        cascade='all, delete-orphan',
        lazy='joined',
        collection_class=set,
    )
    roles = association_proxy(
        '_role_assocs', 'role',
        creator=lambda r: UserRoleAssoc(role=r),
    )

    def has_role(self, role) -> bool:
        if role is None:
            return False
        if isinstance(role, str):
            try:
                role = UserRole[role]
            except KeyError:
                return False
        if role in self.roles:
            return True
        return self.role == role

    def has_any_role(self, *roles) -> bool:
        return any(self.has_role(r) for r in roles)

    @property
    def is_supervisor_only(self) -> bool:
        """True gdy widoczność jest ograniczona do własnych studentów (jako UOPZ).
        ADMIN zawsze widzi wszystko; każdy inny user z rolą UOPZ — tylko swoje."""
        return self.has_role(UserRole.UOPZ) and not self.has_role(UserRole.ADMIN)

    @property
    def role_label(self) -> str:
        """Human-friendly label, połączone ' + ' dla użytkowników z wieloma rolami."""
        from core.translations import translate_role
        values = {r.value for r in self.roles} or ({self.role.value} if self.role else set())
        order = ['ADMIN', 'DYREKTOR', 'KOMISJA', 'DZIEKANAT', 'UOPZ', 'STUDENT']
        ordered = sorted(values, key=lambda v: order.index(v) if v in order else 99)
        return ' + '.join(translate_role(v) for v in ordered if v)

    def get_id(self) -> str:
        return str(self.id)

    def __repr__(self) -> str:
        return f'<User {self.email} ({self.role})>'

# ── JTI subclasses ────────────────────────────────────────────────────────────

class Student(User):
    """Student-specific data — `students` table."""
    __tablename__ = 'students'

    id             = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_USERS, ondelete='CASCADE'), primary_key=True)
    album_number   = db.Column(db.String(20),  nullable=True)
    gender         = db.Column(db.String(1),   nullable=True)   # 'M' or 'F'
    field_of_study = db.Column(db.String(100), nullable=True)
    specialization = db.Column(db.String(100), nullable=True)
    study_mode     = db.Column(db.String(20),  nullable=True)   # 'full-time'/'part-time'
    supervisor_id  = db.Column(UUID(as_uuid=True), db.ForeignKey(_FK_USERS, ondelete='SET NULL'), nullable=True)

    __mapper_args__ = {
        'polymorphic_identity': UserRole.STUDENT,
        'inherit_condition': id == User.__table__.c.id,
    }

    def __repr__(self) -> str:
        return f'<Student {self.email} album={self.album_number}>'


# STI subclasses dla pracowników — istnieją tylko po to, żeby SQLAlchemy
# miał polymorphic_identity dla każdej wartości w `users.role`. Wiele ról
# jednocześnie żyje w `user_roles`.

class Administrator(User):
    __mapper_args__ = {'polymorphic_identity': UserRole.ADMIN}


class UniversityMentor(User):
    __mapper_args__ = {'polymorphic_identity': UserRole.UOPZ}


class KomisjaUser(User):
    __mapper_args__ = {'polymorphic_identity': UserRole.KOMISJA}


class DyrektorUser(User):
    __mapper_args__ = {'polymorphic_identity': UserRole.DYREKTOR}


class DziekanatUser(User):
    __mapper_args__ = {'polymorphic_identity': UserRole.DZIEKANAT}
