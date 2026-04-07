"""core/uslugi/uzytkownicy.py

Usługa zarządzania kontami użytkowników.
"""
from __future__ import annotations

from typing import Optional
import uuid

from werkzeug.security import generate_password_hash, check_password_hash

from core.extensions import db
from core.modele.uzytkownicy import RolaUzytkownika, Uzytkownik, Student, Administrator, OpikunUczelniany
from core.repozytoria.uzytkownicy import RepozytoriumUzytkownikow


class UslugaUzytkownikow:
    """Logika biznesowa kont użytkowników."""

    def __init__(self, repozytorium: Optional[RepozytoriumUzytkownikow] = None) -> None:
        self._repo = repozytorium or RepozytoriumUzytkownikow()

    # ── Uwierzytelnienie ──────────────────────────────────────────────────────

    def uwierzytelnij(self, email: str, haslo: str) -> Optional[Uzytkownik]:
        """Zwraca użytkownika jeśli dane są poprawne, None w przeciwnym razie."""
        uzytkownik = self._repo.znajdz_po_emailu(email)
        if uzytkownik is None or not uzytkownik.aktywny:
            return None
        if not check_password_hash(uzytkownik.hash_hasla, haslo):
            return None
        return uzytkownik

    def zmien_haslo(self, uzytkownik: Uzytkownik, nowe_haslo: str) -> None:
        uzytkownik.hash_hasla = generate_password_hash(nowe_haslo)
        uzytkownik.wymagana_zmiana_hasla = False
        db.session.commit()

    # ── Tworzenie kont ────────────────────────────────────────────────────────

    def utworz_studenta(
        self,
        email: str,
        haslo: str,
        imie: str,
        nazwisko: str,
        numer_albumu: Optional[str] = None,
        **dane_studenta,
    ) -> Student:
        if self._repo.istnieje_email(email):
            raise ValueError(f'Konto z adresem {email} już istnieje.')
        student = Student(
            email=email,
            hash_hasla=generate_password_hash(haslo),
            imie=imie,
            nazwisko=nazwisko,
            rola=RolaUzytkownika.STUDENT,
            numer_albumu=numer_albumu,
            **dane_studenta,
        )
        self._repo.zapisz(student)
        db.session.commit()
        return student

    def utworz_administratora(self, email: str, haslo: str, imie: str, nazwisko: str) -> Administrator:
        if self._repo.istnieje_email(email):
            raise ValueError(f'Konto z adresem {email} już istnieje.')
        admin = Administrator(
            email=email,
            hash_hasla=generate_password_hash(haslo),
            imie=imie,
            nazwisko=nazwisko,
            rola=RolaUzytkownika.ADMIN,
        )
        self._repo.zapisz(admin)
        db.session.commit()
        return admin

    def utworz_opiekuna(self, email: str, haslo: str, imie: str, nazwisko: str) -> OpikunUczelniany:
        if self._repo.istnieje_email(email):
            raise ValueError(f'Konto z adresem {email} już istnieje.')
        opiekun = OpikunUczelniany(
            email=email,
            hash_hasla=generate_password_hash(haslo),
            imie=imie,
            nazwisko=nazwisko,
            rola=RolaUzytkownika.UOPZ,
        )
        self._repo.zapisz(opiekun)
        db.session.commit()
        return opiekun

    # ── Aktualizacja ──────────────────────────────────────────────────────────

    def aktualizuj(self, uzytkownik: Uzytkownik, **pola) -> Uzytkownik:
        """Aktualizuje dowolne pola modelu i zapisuje."""
        if 'haslo' in pola:
            uzytkownik.hash_hasla = generate_password_hash(pola.pop('haslo'))
        for klucz, wartosc in pola.items():
            setattr(uzytkownik, klucz, wartosc)
        db.session.commit()
        return uzytkownik

    def dezaktywuj(self, uzytkownik: Uzytkownik) -> None:
        uzytkownik.aktywny = False
        db.session.commit()

    def aktywuj(self, uzytkownik: Uzytkownik) -> None:
        uzytkownik.aktywny = True
        db.session.commit()

    # ── Dostęp ────────────────────────────────────────────────────────────────

    @property
    def repozytorium(self) -> RepozytoriumUzytkownikow:
        return self._repo
