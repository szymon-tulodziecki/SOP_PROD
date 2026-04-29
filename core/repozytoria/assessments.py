"""core/repozytoria/oceny.py — Repozytorium ocen efektów uczenia się praktyk."""
from __future__ import annotations

import uuid

from core.extensions import db
from core.modele import OutcomeAssessment, CommitteeOutcomeEvaluation, AssessmentResult


class AssessmentRepository:
    """Jedyne miejsce zapytań ORM dotyczących tabeli ocen efektów uczenia się."""

    def get_by_enrollment(self, enrollment_id: uuid.UUID) -> list[OutcomeAssessment]:
        return db.session.execute(
            db.select(OutcomeAssessment).filter_by(enrollment_id=enrollment_id)
        ).scalars().all()

    def zapisz(self, ocena: OutcomeAssessment) -> OutcomeAssessment:
        db.session.add(ocena)
        db.session.flush()
        return ocena

    def dla_komisji(self, enrollment_id: uuid.UUID) -> list[CommitteeOutcomeEvaluation]:
        return (db.session.query(CommitteeOutcomeEvaluation)
                .filter_by(enrollment_id=enrollment_id).all())

    def dla_komisji_dict(self, enrollment_id: uuid.UUID) -> dict:
        return {e.learning_outcome_id: e for e in self.dla_komisji(enrollment_id)}

    def zapisz_ocene_komisji(self, enrollment_id, outcome_id,
                              result: AssessmentResult, notes: str | None) -> None:
        existing = (db.session.query(CommitteeOutcomeEvaluation)
                    .filter_by(enrollment_id=enrollment_id,
                               learning_outcome_id=outcome_id)
                    .first())
        if existing:
            existing.result = result
            existing.notes  = notes or None
        else:
            db.session.add(CommitteeOutcomeEvaluation(
                enrollment_id=enrollment_id,
                learning_outcome_id=outcome_id,
                result=result,
                notes=notes or None,
            ))
