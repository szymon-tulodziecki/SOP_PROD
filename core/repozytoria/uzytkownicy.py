"""core/repozytoria/uzytkownicy.py

Repozytorium użytkowników — jedyne miejsce zapytań ORM
dotyczących tabeli `uzytkownicy` i jej podtabel JTI.
"""
from __future__ import annotations

from typing import Optional
import uuid

from core.extensions import db
from core.modele.uzytkownicy import UserRole, User, Student, Administrator, UniversityMentor

# Potrzebne do metod pomocniczych
import uuid as _uuid


class RepozytoriumUzytkownikow:
    """Dostęp do danych użytkowników systemu."""

    # ── Wyszukiwanie ──────────────────────────────────────────────────────────

    def znajdz_po_id(self, uzytkownik_id: uuid.UUID) -> Optional[User]:
        return db.session.get(User, uzytkownik_id)

    def znajdz_po_emailu(self, email: str) -> Optional[User]:
        return db.session.query(User).filter_by(email=email).first()

    def wszyscy(self) -> list[User]:
        return db.session.query(User).order_by(User.last_name, User.first_name).all()

    def aktywni(self) -> list[User]:
        return db.session.query(User).filter_by(is_active=True).order_by(User.last_name).all()

    # ── Według roli ───────────────────────────────────────────────────────────

    def wszyscy_studenci(self) -> list[Student]:
        return db.session.query(Student).order_by(User.last_name, User.first_name).all()

    def wszyscy_administratorzy(self) -> list[Administrator]:
        return db.session.query(Administrator).order_by(User.last_name).all()

    def wszyscy_opiekunowie(self) -> list[UniversityMentor]:
        return db.session.query(UniversityMentor).order_by(User.last_name).all()

    def opiekunowie_aktywni(self) -> list[UniversityMentor]:
        return (
            db.session.query(UniversityMentor)
            .filter(User.is_active.is_(True))
            .order_by(User.last_name)
            .all()
        )

    # ── Zapis / usunięcie ─────────────────────────────────────────────────────

    def zapisz(self, uzytkownik: User) -> User:
        db.session.add(uzytkownik)
        db.session.flush()
        return uzytkownik

    def usun(self, uzytkownik: User) -> None:
        db.session.delete(uzytkownik)

    def aktywni_uopz(self) -> list[User]:
        """Lista aktywnych opiekunów uczelnianych posortowana po nazwisku."""
        return (
            db.session.query(User)
            .filter_by(role=UserRole.UOPZ, is_active=True)
            .order_by(User.last_name, User.first_name)
            .all()
        )

    def liczba_aktywnych_studentow(self) -> int:
        return db.session.query(User).filter_by(
            role=UserRole.STUDENT, is_active=True
        ).count()

    def szukaj_strona(self, szukaj: str = '', filtr_rola: str = '',
                       strona: int = 1, na_strone: int = 25):
        """Paginowana lista użytkowników z opcjonalnym wyszukiwaniem i filtrem roli."""
        q = db.session.query(User)
        if szukaj:
            studenci_ids = db.session.query(Student.id).filter(
                Student.album_number.ilike(f'%{szukaj}%')
            ).subquery()
            q = q.filter(db.or_(
                User.first_name.ilike(f'%{szukaj}%'),
                User.last_name.ilike(f'%{szukaj}%'),
                User.email.ilike(f'%{szukaj}%'),
                User.id.in_(studenci_ids),
            ))
        if filtr_rola:
            try:
                q = q.filter(User.role == UserRole[filtr_rola])
            except KeyError:
                pass
        return q.order_by(User.last_name, User.first_name).paginate(
            page=strona, per_page=na_strone, error_out=False
        )

    def studenci_strona(self, szukaj: str = '', supervisor_id=None,
                         strona: int = 1, na_strone: int = 25):
        """Paginowana lista studentów z opcjonalnym filtrem UOPZ i wyszukiwaniem."""
        q = db.session.query(Student)
        if supervisor_id is not None:
            q = q.filter(Student.supervisor_id == supervisor_id)
        if szukaj:
            album_sub = db.session.query(Student.id).filter(
                Student.album_number.ilike(f'%{szukaj}%')
            ).subquery()
            q = q.filter(db.or_(
                Student.first_name.ilike(f'%{szukaj}%'),
                Student.last_name.ilike(f'%{szukaj}%'),
                Student.id.in_(album_sub),
            ))
        return q.order_by(Student.last_name, Student.first_name).paginate(
            page=strona, per_page=na_strone, error_out=False
        )

    def znajdz_studenta_po_albumie(self, album_number: str) -> Optional[Student]:
        return db.session.query(Student).filter_by(album_number=album_number).first()

    def znajdz_istniejace_po_email_lub_albumie(self, emails: list, albums: list):
        """Batch-lookup emaili i numerów albumów — eliminuje N+1 przy imporcie CSV."""
        return (
            db.session.query(User.email, Student.album_number)
            .outerjoin(Student, User.id == Student.id)
            .filter(db.or_(
                User.email.in_(emails),
                Student.album_number.in_(albums)
            ))
            .all()
        )

    # ── Pomocnicze ────────────────────────────────────────────────────────────

    def istnieje_email(self, email: str, pominij_id: Optional[uuid.UUID] = None) -> bool:
        q = db.session.query(User).filter_by(email=email)
        if pominij_id is not None:
            q = q.filter(User.id != pominij_id)
        return db.session.query(q.exists()).scalar()
