"""User repository."""

from __future__ import annotations

from typing import Optional
import uuid

from core.extensions import db
from core.models.internships import InternshipEnrollment
from core.models.users import (
    Administrator,
    Student,
    UniversityMentor,
    User,
    UserRole,
    UserRoleAssoc,
)


class UserRepository:
    """Data access for system users."""

    def find_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        return db.session.get(User, user_id)

    def find_by_email(self, email: str) -> Optional[User]:
        return db.session.query(User).filter_by(email=email).first()

    def all(self) -> list[User]:
        return db.session.query(User).order_by(User.last_name, User.first_name).all()

    def active(self) -> list[User]:
        return db.session.query(User).filter_by(is_active=True).order_by(User.last_name).all()

    def all_students(self) -> list[Student]:
        return db.session.query(Student).order_by(User.last_name, User.first_name).all()

    def all_administrators(self) -> list[Administrator]:
        return db.session.query(Administrator).order_by(User.last_name).all()

    def all_mentors(self) -> list[UniversityMentor]:
        return db.session.query(UniversityMentor).order_by(User.last_name).all()

    def active_mentors(self) -> list[UniversityMentor]:
        return (
            db.session.query(UniversityMentor)
            .filter(User.is_active.is_(True))
            .order_by(User.last_name)
            .all()
        )

    def save(self, user: User) -> User:
        db.session.add(user)
        db.session.flush()
        return user

    def delete(self, user: User) -> None:
        db.session.delete(user)

    def active_uopz(self) -> list[User]:
        """Active university internship supervisors ordered by name."""
        return (
            db.session.query(User)
            .filter_by(role=UserRole.UOPZ, is_active=True)
            .order_by(User.last_name, User.first_name)
            .all()
        )

    def active_university_mentors(self) -> list[UniversityMentor]:
        """Active UniversityMentor records ordered by name."""
        return (
            db.session.execute(
                db.select(UniversityMentor)
                .filter_by(is_active=True)
                .order_by(UniversityMentor.last_name, UniversityMentor.first_name)
            )
            .scalars()
            .all()
        )

    def count_active_students(self) -> int:
        return db.session.query(User).filter_by(role=UserRole.STUDENT, is_active=True).count()

    def search_page(
        self, search: str = "", role_filter: str = "", page: int = 1, per_page: int = 25
    ):
        """Paginated user list with optional search and role filter."""
        q = db.session.query(User)
        if search:
            student_ids = (
                db.session.query(Student.id)
                .filter(Student.album_number.ilike(f"%{search}%"))
                .subquery()
            )
            q = q.filter(
                db.or_(
                    User.first_name.ilike(f"%{search}%"),
                    User.last_name.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                    User.id.in_(student_ids),
                )
            )
        if role_filter:
            try:
                role = UserRole[role_filter]
            except KeyError:
                pass
            else:
                # Pracownicy mogą mieć wiele ról naraz (user_roles).
                q = (
                    q.outerjoin(UserRoleAssoc, UserRoleAssoc.user_id == User.id)
                    .filter(db.or_(User.role == role, UserRoleAssoc.role == role))
                    .distinct()
                )
        return q.order_by(User.last_name, User.first_name).paginate(
            page=page, per_page=per_page, error_out=False
        )

    def students_page(
        self, search: str = "", supervisor_id=None, page: int = 1, per_page: int = 25, paths=None
    ):
        """Paginated student list with optional UOPZ and path filters."""
        q = db.session.query(Student)
        if supervisor_id is not None:
            q = q.filter(Student.supervisor_id == supervisor_id)
        if paths:
            q = q.filter(
                Student.id.in_(
                    db.session.query(InternshipEnrollment.student_id)
                    .filter(InternshipEnrollment.path_type.in_(paths))
                    .distinct()
                )
            )
        if search:
            album_subquery = (
                db.session.query(Student.id)
                .filter(Student.album_number.ilike(f"%{search}%"))
                .subquery()
            )
            q = q.filter(
                db.or_(
                    Student.first_name.ilike(f"%{search}%"),
                    Student.last_name.ilike(f"%{search}%"),
                    Student.id.in_(album_subquery),
                )
            )
        return q.order_by(Student.last_name, Student.first_name).paginate(
            page=page, per_page=per_page, error_out=False
        )

    def find_student_by_album(self, album_number: str) -> Optional[Student]:
        return db.session.query(Student).filter_by(album_number=album_number).first()

    def find_existing_by_email_or_album(self, emails: list, albums: list):
        """Batch lookup for CSV import; avoids N+1 checks."""
        return (
            db.session.query(User.email, Student.album_number)
            .outerjoin(Student, User.id == Student.id)
            .filter(
                db.or_(
                    User.email.in_(emails),
                    Student.album_number.in_(albums),
                )
            )
            .all()
        )

    def email_exists(self, email: str, exclude_id: Optional[uuid.UUID] = None) -> bool:
        q = db.session.query(User).filter_by(email=email)
        if exclude_id is not None:
            q = q.filter(User.id != exclude_id)
        return db.session.query(q.exists()).scalar()
