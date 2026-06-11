"""User account management service."""
from __future__ import annotations

import csv
import io
import uuid
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash

from core.extensions import db
from core.i18n import t
from core.models.users import (
    Administrator,
    DyrektorUser,
    KomisjaUser,
    Student,
    UniversityMentor,
    User,
    UserRole,
)
from core.repositories.users import UserRepository


class UserService:
    """Logika biznesowa kont użytkowników."""

    def __init__(self, repository: Optional[UserRepository] = None) -> None:
        self._repo = repository or UserRepository()

    def authenticate(self, email: str, password: str) -> Optional[User]:
        """Returns user if credentials are valid, None otherwise."""
        user = self._repo.find_by_email(email)
        if user is None or not user.is_active:
            return None
        if not check_password_hash(user.password_hash, password):
            return None
        return user

    def change_password(self, user: User, new_password: str) -> None:
        user.password_hash = generate_password_hash(new_password)
        user.require_password_change = False
        db.session.commit()

    def create_student(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        album_number: Optional[str] = None,
        commit: bool = True,
        **student_data,
    ) -> Student:
        if self._repo.email_exists(email):
            raise ValueError(t('Konto z adresem {email} już istnieje.', email=email))
        student = Student(
            email=email,
            password_hash=generate_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            role=UserRole.STUDENT,
            album_number=album_number,
            **student_data,
        )
        student.roles.add(UserRole.STUDENT)
        self._repo.save(student)
        if commit:
            db.session.commit()
        return student

    def create_administrator(self, email: str, password: str, first_name: str, last_name: str) -> Administrator:
        if self._repo.email_exists(email):
            raise ValueError(t('Konto z adresem {email} już istnieje.', email=email))
        admin = Administrator(
            email=email,
            password_hash=generate_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            role=UserRole.ADMIN,
        )
        self._repo.save(admin)
        db.session.commit()
        return admin

    # Priorytet wyboru głównej roli (JTI discriminator) gdy pracownik ma kilka.
    _STAFF_ROLE_PRIORITY = (UserRole.ADMIN, UserRole.DYREKTOR, UserRole.KOMISJA, UserRole.UOPZ)
    _STAFF_JTI_CLASS = {
        UserRole.ADMIN: Administrator,
        UserRole.DYREKTOR: DyrektorUser,
        UserRole.KOMISJA: KomisjaUser,
        UserRole.UOPZ: UniversityMentor,
    }

    def create_staff(
        self,
        email: str,
        first_name: str,
        last_name: str,
        roles: list[UserRole],
    ) -> User:
        """Tworzy konto pracownika z 1+ rolami. ADMIN i STUDENT są wyłączne;
        UOPZ/KOMISJA/DYREKTOR mogą się łączyć dowolnie."""
        if not roles:
            raise ValueError(t('Musisz wybrać co najmniej jedną rolę.'))
        if UserRole.STUDENT in roles:
            raise ValueError(t('Rola STUDENT nie jest dostępna w formularzu pracownika.'))
        if UserRole.ADMIN in roles and len(roles) > 1:
            raise ValueError(t('Rola ADMIN nie może być łączona z innymi rolami.'))
        if self._repo.email_exists(email):
            raise ValueError(t('Konto z adresem {email} już istnieje.', email=email))

        primary = next(r for r in self._STAFF_ROLE_PRIORITY if r in roles)
        cls = self._STAFF_JTI_CLASS[primary]
        user = cls(
            email=email,
            password_hash='',
            first_name=first_name,
            last_name=last_name,
            role=primary,
            is_active=True,
            require_password_change=False,
        )
        for r in roles:
            user.roles.add(r)
        self._repo.save(user)
        db.session.commit()
        return user

    def create_mentor(self, email: str, password: str, first_name: str, last_name: str) -> UniversityMentor:
        if self._repo.email_exists(email):
            raise ValueError(t('Konto z adresem {email} już istnieje.', email=email))
        mentor = UniversityMentor(
            email=email,
            password_hash=generate_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            role=UserRole.UOPZ,
        )
        self._repo.save(mentor)
        db.session.commit()
        return mentor

    def update(self, user: User, **fields) -> User:
        """Updates arbitrary model fields and commits."""
        if 'password' in fields:
            user.password_hash = generate_password_hash(fields.pop('password'))
        for key, value in fields.items():
            setattr(user, key, value)
        db.session.commit()
        return user

    def deactivate(self, user: User) -> None:
        user.is_active = False
        db.session.commit()

    def activate(self, user: User) -> None:
        user.is_active = True
        db.session.commit()

    @staticmethod
    def _sanitize_csv_field(value: str) -> str:
        """Prevents CSV Formula Injection by neutralizing dangerous leading characters."""
        if value and value[0] in ('=', '+', '-', '@', '\t', '\r'):
            return "'" + value
        return value

    @staticmethod
    def _parse_csv_row(row_number: int, row: dict) -> tuple[dict | None, str | None]:
        """Parses one CSV row. Returns (parsed_dict, None) or (None, error_msg)."""
        _s = UserService._sanitize_csv_field
        first_name = _s((row.get('imie') or row.get('Imię') or '').strip())
        last_name = _s((row.get('nazwisko') or row.get('Nazwisko') or '').strip())
        email = (row.get('email') or row.get('Email') or '').strip().lower()
        album_number = (row.get('numer_albumu') or row.get('Nr albumu') or '').strip()
        _gender_raw = (row.get('plec') or row.get('Płeć') or '').strip().upper()
        gender = 'F' if _gender_raw == 'K' else (_gender_raw or None)
        field_of_study = _s((row.get('kierunek') or row.get('Kierunek') or '').strip()) or None
        specialization = _s((row.get('specjalizacja') or row.get('specialization') or row.get('Specjalność') or '').strip()) or None
        _study_mode_raw = (row.get('tryb_studiow') or row.get('Tryb') or '').strip().lower()
        study_mode = {'stacjonarne': 'full-time', 'niestacjonarne': 'part-time'}.get(_study_mode_raw, _study_mode_raw) or None

        if not all([first_name, last_name, email, album_number, gender, field_of_study, study_mode]):
            return None, t(
                'Wiersz {numer}: brakujące dane '
                '(wymagane: imie, nazwisko, email, numer_albumu, plec, kierunek, tryb_studiow)',
                numer=row_number,
            )
        return {
            'row_number': row_number,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'album_number': album_number,
            'gender': gender,
            'field_of_study': field_of_study,
            'specialization': specialization,
            'study_mode': study_mode,
        }, None

    def _create_student_from_row(
        self,
        parsed_row: dict,
        supervisor_id,
        existing_emails: set,
        existing_albums: set,
    ) -> str | None:
        """Creates one student from parsed row. Returns error string or None on success."""
        if parsed_row['email'] in existing_emails or parsed_row['album_number'] in existing_albums:
            return t(
                'Wiersz {numer}: {email} lub nr {album} już istnieje',
                numer=parsed_row['row_number'], email=parsed_row['email'],
                album=parsed_row['album_number'],
            )
        try:
            self.create_student(
                email=parsed_row['email'],
                password='',
                first_name=parsed_row['first_name'],
                last_name=parsed_row['last_name'],
                album_number=parsed_row['album_number'],
                gender=parsed_row['gender'],
                field_of_study=parsed_row['field_of_study'],
                specialization=parsed_row['specialization'],
                study_mode=parsed_row['study_mode'],
                supervisor_id=uuid.UUID(supervisor_id) if supervisor_id else None,
                require_password_change=False,
                commit=False,
            )
            existing_emails.add(parsed_row['email'])
            existing_albums.add(parsed_row['album_number'])
            return None
        except Exception as exc:
            return t('Wiersz {numer}: {blad}', numer=parsed_row['row_number'], blad=exc)

    _REQUIRED_CSV_COLUMNS = (
        ('imie', 'Imię'),
        ('nazwisko', 'Nazwisko'),
        ('email', 'Email'),
        ('numer_albumu', 'Nr albumu'),
        ('plec', 'Płeć'),
        ('kierunek', 'Kierunek'),
        ('tryb_studiow', 'Tryb'),
    )

    def import_from_csv(self, content: str, supervisor_id, commit: bool = True) -> dict:
        """Parses CSV, validates rows, and creates student accounts."""
        reader = csv.DictReader(io.StringIO(content))
        created = skipped = 0
        errors: list[str] = []
        csv_rows: list[dict] = []

        # Validate CSV header before processing rows — prevents wasting work on a wrong file.
        header = set(reader.fieldnames or [])
        missing = [
            aliases[0] for aliases in self._REQUIRED_CSV_COLUMNS
            if not any(name in header for name in aliases)
        ]
        if missing:
            return {
                'created': 0,
                'skipped': 0,
                'errors': [t('Brakujące kolumny w nagłówku CSV: {kolumny}', kolumny=', '.join(missing))],
            }

        for row_number, row in enumerate(reader, start=2):
            parsed, error = self._parse_csv_row(row_number, row)
            if error:
                errors.append(error)
                skipped += 1
            else:
                csv_rows.append(parsed)

        if csv_rows:
            all_emails = [row['email'] for row in csv_rows]
            all_albums = [row['album_number'] for row in csv_rows]
            existing = self._repo.find_existing_by_email_or_album(all_emails, all_albums)
            existing_emails = {user.email for user in existing}
            existing_albums = {user.album_number for user in existing if user.album_number}

            for parsed_row in csv_rows:
                error = self._create_student_from_row(parsed_row, supervisor_id, existing_emails, existing_albums)
                if error:
                    errors.append(error)
                    skipped += 1
                else:
                    created += 1

            if commit and created:
                db.session.commit()

        return {'created': created, 'skipped': skipped, 'errors': errors}

    @property
    def repository(self) -> UserRepository:
        return self._repo
