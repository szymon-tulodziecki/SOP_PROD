"""core/repozytoria/uzytkownicy.py

Repozytorium użytkowników — jedyne miejsce zapytań ORM
dotyczących tabeli `uzytkownicy` i jej podtabel JTI.
"""
from __future__ import annotations

from typing import Optional
import uuid

from core.extensions import db
from core.modele.uzytkownicy import RolaUzytkownika, Uzytkownik, Student, Administrator, OpikunUczelniany


class RepozytoriumUzytkownikow:
    """Dostęp do danych użytkowników systemu."""

    # ── Wyszukiwanie ──────────────────────────────────────────────────────────

    def znajdz_po_id(self, uzytkownik_id: uuid.UUID) -> Optional[Uzytkownik]:
        return db.session.get(Uzytkownik, uzytkownik_id)

    def znajdz_po_emailu(self, email: str) -> Optional[Uzytkownik]:
        return db.session.query(Uzytkownik).filter_by(email=email).first()

    def wszyscy(self) -> list[Uzytkownik]:
        return db.session.query(Uzytkownik).order_by(Uzytkownik.last_name, Uzytkownik.first_name).all()

    def aktywni(self) -> list[Uzytkownik]:
        return db.session.query(Uzytkownik).filter_by(is_active=True).order_by(Uzytkownik.last_name).all()

    # ── Według roli ───────────────────────────────────────────────────────────

    def wszyscy_studenci(self) -> list[Student]:
        return db.session.query(Student).order_by(Uzytkownik.last_name, Uzytkownik.first_name).all()

    def wszyscy_administratorzy(self) -> list[Administrator]:
        return db.session.query(Administrator).order_by(Uzytkownik.last_name).all()

    def wszyscy_opiekunowie(self) -> list[OpikunUczelniany]:
        return db.session.query(OpikunUczelniany).order_by(Uzytkownik.last_name).all()

    def opiekunowie_aktywni(self) -> list[OpikunUczelniany]:
        return (
            db.session.query(OpikunUczelniany)
            .filter(Uzytkownik.is_active.is_(True))
            .order_by(Uzytkownik.last_name)
            .all()
        )

    # ── Zapis / usunięcie ─────────────────────────────────────────────────────

    def zapisz(self, uzytkownik: Uzytkownik) -> Uzytkownik:
        db.session.add(uzytkownik)
        db.session.flush()
        return uzytkownik

    def usun(self, uzytkownik: Uzytkownik) -> None:
        db.session.delete(uzytkownik)

    # ── Pomocnicze ────────────────────────────────────────────────────────────

    def istnieje_email(self, email: str, pominij_id: Optional[uuid.UUID] = None) -> bool:
        q = db.session.query(Uzytkownik).filter_by(email=email)
        if pominij_id is not None:
            q = q.filter(Uzytkownik.id != pominij_id)
        return db.session.query(q.exists()).scalar()
