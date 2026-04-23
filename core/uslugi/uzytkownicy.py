"""core/uslugi/uzytkownicy.py

User account management service.
"""
from __future__ import annotations

from typing import Optional
import uuid

from werkzeug.security import generate_password_hash, check_password_hash

from core.extensions import db
from core.modele.uzytkownicy import UserRole, User, Student, Administrator, UniversityMentor
from core.repozytoria.uzytkownicy import RepozytoriumUzytkownikow


class UslugaUzytkownikow:
    """Business logic for user accounts."""

    def __init__(self, repozytorium: Optional[RepozytoriumUzytkownikow] = None) -> None:
        self._repo = repozytorium or RepozytoriumUzytkownikow()

    # ── Authentication ────────────────────────────────────────────────────────

    def uwierzytelnij(self, email: str, haslo: str) -> Optional[User]:
        """Returns user if credentials are valid, None otherwise."""
        user = self._repo.znajdz_po_emailu(email)
        if user is None or not user.is_active:
            return None
        if not check_password_hash(user.password_hash, haslo):
            return None
        return user

    def zmien_haslo(self, user: User, nowe_haslo: str) -> None:
        user.password_hash = generate_password_hash(nowe_haslo)
        user.require_password_change = False
        db.session.commit()

    # ── Account creation ──────────────────────────────────────────────────────

    def utworz_studenta(
        self,
        email: str,
        haslo: str,
        imie: str,
        nazwisko: str,
        numer_albumu: Optional[str] = None,
        commit: bool = True,
        **dane_studenta,
    ) -> Student:
        if self._repo.istnieje_email(email):
            raise ValueError(f'Konto z adresem {email} już istnieje.')
        student = Student(
            email=email,
            password_hash=generate_password_hash(haslo),
            first_name=imie,
            last_name=nazwisko,
            role=UserRole.STUDENT,
            album_number=numer_albumu,
            **dane_studenta,
        )
        self._repo.zapisz(student)
        if commit:
            db.session.commit()
        return student

    def utworz_administratora(self, email: str, haslo: str, imie: str, nazwisko: str) -> Administrator:
        if self._repo.istnieje_email(email):
            raise ValueError(f'Konto z adresem {email} już istnieje.')
        admin = Administrator(
            email=email,
            password_hash=generate_password_hash(haslo),
            first_name=imie,
            last_name=nazwisko,
            role=UserRole.ADMIN,
        )
        self._repo.zapisz(admin)
        db.session.commit()
        return admin

    def utworz_opiekuna(self, email: str, haslo: str, imie: str, nazwisko: str) -> UniversityMentor:
        if self._repo.istnieje_email(email):
            raise ValueError(f'Konto z adresem {email} już istnieje.')
        mentor = UniversityMentor(
            email=email,
            password_hash=generate_password_hash(haslo),
            first_name=imie,
            last_name=nazwisko,
            role=UserRole.UOPZ,
        )
        self._repo.zapisz(mentor)
        db.session.commit()
        return mentor

    # ── Updates ───────────────────────────────────────────────────────────────

    def aktualizuj(self, user: User, **pola) -> User:
        """Updates arbitrary model fields and commits."""
        if 'haslo' in pola:
            user.password_hash = generate_password_hash(pola.pop('haslo'))
        for klucz, wartosc in pola.items():
            setattr(user, klucz, wartosc)
        db.session.commit()
        return user

    def dezaktywuj(self, user: User) -> None:
        user.is_active = False
        db.session.commit()

    def aktywuj(self, user: User) -> None:
        user.is_active = True
        db.session.commit()

    # ── Repository access ─────────────────────────────────────────────────────

    @property
    def repozytorium(self) -> RepozytoriumUzytkownikow:
        return self._repo
