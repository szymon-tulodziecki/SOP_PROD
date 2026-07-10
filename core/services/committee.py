"""core/uslugi/komisja.py

Logika biznesowa weryfikacji komisji.
"""

from __future__ import annotations


class CommitteeService:

    @staticmethod
    def validate_outcome_grades(outcomes, form_data: dict) -> tuple[list[str], list[tuple]]:
        """Waliduje oceny efektów uczenia się z danych formularza.

        Args:
            outcomes:  lista obiektów LearningOutcome
            form_data: słownik z danymi formularza (request.form)

        Returns:
            (errors, evaluations) gdzie evaluations to lista krotek
            (outcome_id, result_val, notes_val) dla wierszy bez błędów.
        """
        errors: list[str] = []
        evaluations: list[tuple] = []

        for outcome in outcomes:
            result_val = form_data.get(f"outcome_{outcome.id}")
            if not result_val:
                errors.append(f"Efekt {outcome.code}: brak oceny")
                continue
            notes_val = form_data.get(f"notes_{outcome.id}", "").strip()
            if result_val == "PARTIALLY_ACHIEVED" and not notes_val:
                errors.append(
                    f"Efekt {outcome.code}: wymagane uzasadnienie dla wyniku „Uzyskał/a częściowo”"
                )
            evaluations.append((outcome.id, result_val, notes_val))

        return errors, evaluations
