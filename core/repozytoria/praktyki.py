"""core/repozytoria/praktyki.py

Repozytoria edycji praktyk i zapisów studentów.
"""
from __future__ import annotations

from typing import Optional
import uuid

from core.extensions import db
from core.modele.praktyki import (
    Praktyka,
    StatusPraktyki,
    ZapisPraktyki,
    StatusZapisu,
)


class RepozytoriumPraktyk:
    """Dostęp do edycji praktyk (rok akademicki / semestr)."""

    def znajdz_po_id(self, praktyka_id: uuid.UUID) -> Optional[Praktyka]:
        return db.session.get(Praktyka, praktyka_id)

    def wszystkie(self) -> list[Praktyka]:
        return db.session.query(Praktyka).order_by(Praktyka.academic_year.desc(), Praktyka.semester).all()

    def aktywne(self) -> list[Praktyka]:
        return (
            db.session.query(Praktyka)
            .filter_by(status=StatusPraktyki.ACTIVE)
            .order_by(Praktyka.academic_year.desc())
            .all()
        )

    def aktywna_edycja(self) -> Optional[Praktyka]:
        """Zwraca pierwszą aktywną edycję praktyk lub None."""
        return (
            db.session.query(Praktyka)
            .filter_by(status=StatusPraktyki.ACTIVE)
            .order_by(Praktyka.academic_year.desc())
            .first()
        )

    def zapisz(self, praktyka: Praktyka) -> Praktyka:
        db.session.add(praktyka)
        db.session.flush()
        return praktyka

    def usun(self, praktyka: Praktyka) -> None:
        db.session.delete(praktyka)


class RepozytoriumZapisow:
    """Dostęp do zapisów studentów na edycje praktyk."""

    def znajdz_po_id(self, zapis_id: uuid.UUID) -> Optional[ZapisPraktyki]:
        return db.session.get(ZapisPraktyki, zapis_id)

    def wszystkie(self) -> list[ZapisPraktyki]:
        return db.session.query(ZapisPraktyki).order_by(ZapisPraktyki.enrolled_at.desc()).all()

    def dla_studenta(self, student_id: uuid.UUID) -> list[ZapisPraktyki]:
        return (
            db.session.query(ZapisPraktyki)
            .filter_by(student_id=student_id)
            .order_by(ZapisPraktyki.enrolled_at.desc())
            .all()
        )

    def dla_praktyki(self, praktyka_id: uuid.UUID) -> list[ZapisPraktyki]:
        return (
            db.session.query(ZapisPraktyki)
            .filter_by(internship_id=praktyka_id)
            .order_by(ZapisPraktyki.enrolled_at.desc())
            .all()
        )

    def dla_opiekuna(self, uopz_id: uuid.UUID) -> list[ZapisPraktyki]:
        return (
            db.session.query(ZapisPraktyki)
            .filter_by(supervisor_id=uopz_id)
            .order_by(ZapisPraktyki.enrolled_at.desc())
            .all()
        )

    def po_statusie(self, status: StatusZapisu) -> list[ZapisPraktyki]:
        return (
            db.session.query(ZapisPraktyki)
            .filter_by(status=status)
            .order_by(ZapisPraktyki.enrolled_at.desc())
            .all()
        )

    def student_ma_aktywny_zapis(self, student_id: uuid.UUID, praktyka_id: uuid.UUID) -> bool:
        """Sprawdza czy student ma już zapis do danej edycji (inny niż ODRZUCONY)."""
        q = (
            db.session.query(ZapisPraktyki)
            .filter_by(student_id=student_id, internship_id=praktyka_id)
            .filter(ZapisPraktyki.status != StatusZapisu.REJECTED)
        )
        return db.session.query(q.exists()).scalar()

    def zapisz(self, zapis: ZapisPraktyki) -> ZapisPraktyki:
        db.session.add(zapis)
        db.session.flush()
        return zapis

    def usun(self, zapis: ZapisPraktyki) -> None:
        db.session.delete(zapis)
