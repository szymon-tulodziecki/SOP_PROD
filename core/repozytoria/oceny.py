"""core/repozytoria/oceny.py — Repozytorium ocen efektów uczenia się praktyk."""
from __future__ import annotations

import uuid

from core.extensions import db
from core.modele import OutcomeAssessment


class RepozytoriumOcen:
    """Jedyne miejsce zapytań ORM dotyczących tabeli ocen efektów uczenia się."""

    def dla_zapisu(self, enrollment_id: uuid.UUID) -> list[OutcomeAssessment]:
        return db.session.execute(
            db.select(OutcomeAssessment).filter_by(enrollment_id=enrollment_id)
        ).scalars().all()

    def zapisz(self, ocena: OutcomeAssessment) -> OutcomeAssessment:
        db.session.add(ocena)
        db.session.flush()
        return ocena
