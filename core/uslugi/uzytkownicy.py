"""core/uslugi/uzytkownicy.py

User account management service.
"""
from __future__ import annotations

import csv
import io
import uuid
from typing import Optional

from werkzeug.security import generate_password_hash, check_password_hash

from core.extensions import db
from core.modele.uzytkownicy import UserRole, User, Student, Administrator, UniversityMentor
from core.repozytoria.uzytkownicy import UserRepository


class UslugaUzytkownikow:
    """Business logic for user accounts."""

    def __init__(self, repozytorium: Optional[UserRepository] = None) -> None:
        self._repo = repozytorium or UserRepository()

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

    # ── Bulk import ──────────────────────────────────────────────────────────

    def importuj_z_csv(self, content: str, uopz_id, commit: bool = True) -> dict:
        """Parsuje CSV, waliduje wiersze, tworzy konta studentów.

        Returns:
            {'created': N, 'skipped': N, 'errors': [...]}
        """
        reader   = csv.DictReader(io.StringIO(content))
        created  = skipped = 0
        errors: list[str] = []
        csv_rows: list[dict] = []

        for row_number, row in enumerate(reader, start=2):
            first_name     = (row.get('imie')         or row.get('Imię')        or '').strip()
            last_name      = (row.get('nazwisko')      or row.get('Nazwisko')    or '').strip()
            email          = (row.get('email')         or row.get('Email')       or '').strip().lower()
            album_number   = (row.get('numer_albumu')  or row.get('Nr albumu')   or '').strip()
            gender         = (row.get('plec')          or row.get('Płeć')        or '').strip().upper() or None
            field_of_study = (row.get('kierunek')      or row.get('Kierunek')    or '').strip() or None
            specialization = (row.get('specjalnosc')   or row.get('Specjalność') or '').strip() or None
            study_mode     = (row.get('tryb_studiow')  or row.get('Tryb')        or '').strip().lower() or None

            if not all([first_name, last_name, email, album_number, gender, field_of_study, study_mode]):
                errors.append(
                    f'Wiersz {row_number}: brakujące dane '
                    f'(wymagane: imie, nazwisko, email, numer_albumu, plec, kierunek, tryb_studiow)'
                )
                skipped += 1
                continue

            csv_rows.append({
                'row_number': row_number,
                'first_name': first_name, 'last_name': last_name,
                'email': email, 'album_number': album_number, 'gender': gender,
                'field_of_study': field_of_study, 'specialization': specialization,
                'study_mode': study_mode,
            })

        if csv_rows:
            all_emails = [r['email'] for r in csv_rows]
            all_albums = [r['album_number'] for r in csv_rows]
            existing   = self._repo.znajdz_istniejace_po_email_lub_albumie(all_emails, all_albums)

            existing_emails = {row.email for row in existing}
            existing_albums = {row.album_number for row in existing if row.album_number}

            for r in csv_rows:
                if r['email'] in existing_emails or r['album_number'] in existing_albums:
                    errors.append(
                        f"Wiersz {r['row_number']}: {r['email']} lub nr {r['album_number']} już istnieje"
                    )
                    skipped += 1
                    continue
                try:
                    self.utworz_studenta(
                        email          = r['email'],
                        haslo          = '',
                        imie           = r['first_name'],
                        nazwisko       = r['last_name'],
                        numer_albumu   = r['album_number'],
                        gender         = r['gender'],
                        field_of_study = r['field_of_study'],
                        specialization = r['specialization'],
                        study_mode     = r['study_mode'],
                        supervisor_id  = uuid.UUID(uopz_id) if uopz_id else None,
                        require_password_change=False,
                        commit=False,
                    )
                    existing_emails.add(r['email'])
                    existing_albums.add(r['album_number'])
                    created += 1
                except Exception as e:
                    errors.append(f"Wiersz {r['row_number']}: {e}")
                    skipped += 1

            if commit and created:
                from core.extensions import db as _db
                _db.session.commit()

        return {'created': created, 'skipped': skipped, 'errors': errors}

    # ── Repository access ─────────────────────────────────────────────────────

    @property
    def repozytorium(self) -> UserRepository:
        return self._repo
