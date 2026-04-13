"""core/repozytoria/efekty.py — Repozytorium efektów uczenia się."""
from __future__ import annotations

from core.extensions import db
from core.modele.dziennik import LearningOutcome


class RepozytoriumEfektow:
    """Jedyne miejsce zapytań ORM dotyczących tabeli efektów uczenia się."""

    def wszystkie(self) -> list[LearningOutcome]:
        return db.session.execute(db.select(LearningOutcome).order_by(LearningOutcome.id)).scalars().all()

    def po_ids(self, ids: list[int]) -> list[LearningOutcome]:
        """Pobiera efekty po liście identyfikatorów (np. do przypisania M2M)."""
        if not ids:
            return []
        return db.session.execute(db.select(LearningOutcome).filter(LearningOutcome.id.in_(ids))).scalars().all()
