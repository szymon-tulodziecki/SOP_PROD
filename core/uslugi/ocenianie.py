"""
core/uslugi/ocenianie.py

Usługa oceniania praktyk.
Zawiera całą logikę domenową procesu oceniania — kontrolery tras
delegują tutaj i nie zawierają własnej logiki biznesowej.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from core.extensions import db
from core.modele import InternshipEnrollment, EnrollmentStatus

log = logging.getLogger(__name__)


# ── DTO ───────────────────────────────────────────────────────────────────────

@dataclass
class GradeFormData:
    """Transfer Object — dane z formularza ocen, niezależny od HTTP."""
    report_grade:                  Optional[float]
    supervisor_grade:              Optional[float]
    workplace_grade:               Optional[float]
    supervisor_grade_description:  Optional[str]
    workplace_grade_description:   Optional[str]
    exam_question_1:               Optional[str]
    exam_grade_1:                  Optional[float]
    exam_question_2:               Optional[str]
    exam_grade_2:                  Optional[float]
    exam_question_3:               Optional[str]
    exam_grade_3:                  Optional[float]
    commission_chair:              Optional[str] = None
    commission_member_2:           Optional[str] = None
    commission_member_3:           Optional[str] = None
    finalize: bool = False         # True → zmień status na COMPLETED


@dataclass
class GradeResult:
    """Wynik operacji zapisu ocen."""
    success: bool
    missing_fields: list[str]      # niepuste gdy success=False i finalize=True

    @property
    def error_message(self) -> str | None:
        if not self.success and self.missing_fields:
            return f"Nie można zakończyć — brakuje: {', '.join(self.missing_fields)}."
        return None


class SerwisOceniania:

    # ── Zapis ocen ────────────────────────────────────────────────────────────

    @staticmethod
    def zapisz_oceny(zapis: InternshipEnrollment, dane: GradeFormData) -> GradeResult:
        """Zapisuje oceny końcowe i sprawdzian dla zapisu praktyki.

        Jeśli dane.finalize=True, weryfikuje kompletność przed zamknięciem.
        Nie wykonuje commit — wywołujący decyduje o transakcji.

        Returns:
            GradeResult(success=False, missing_fields=[...]) gdy finalize=True
            i brakuje ocen. W przeciwnym razie GradeResult(success=True).
        """
        from core.modele import OcenyKoncowe, Sprawdzian as SprawdzianModel

        ok = zapis.oceny_koncowe or OcenyKoncowe(enrollment_id=zapis.id)
        if ok not in db.session:
            db.session.add(ok)

        ok.report_grade                 = dane.report_grade
        ok.supervisor_grade             = dane.supervisor_grade
        ok.workplace_grade              = dane.workplace_grade
        ok.supervisor_grade_description = dane.supervisor_grade_description
        ok.workplace_grade_description  = dane.workplace_grade_description

        sp = zapis.sprawdzian or SprawdzianModel(enrollment_id=zapis.id)
        if sp not in db.session:
            db.session.add(sp)

        sp.question_1 = dane.exam_question_1
        sp.grade_1    = dane.exam_grade_1
        sp.question_2 = dane.exam_question_2
        sp.grade_2    = dane.exam_grade_2
        sp.question_3 = dane.exam_question_3
        sp.grade_3    = dane.exam_grade_3

        sp.commission_chair    = (dane.commission_chair    or '').strip() or None
        sp.commission_member_2 = (dane.commission_member_2 or '').strip() or None
        sp.commission_member_3 = (dane.commission_member_3 or '').strip() or None

        if dane.finalize:
            missing = SerwisOceniania._waliduj_kompletnosc(ok, sp)
            if missing:
                db.session.rollback()
                return GradeResult(success=False, missing_fields=missing)
            from core.uslugi.workflow import ZapisFSM, IllegalTransitionError
            try:
                ZapisFSM(zapis).zakoncz()
            except IllegalTransitionError:
                pass

        return GradeResult(success=True, missing_fields=[])

    @staticmethod
    def _waliduj_kompletnosc(ok, sp) -> list[str]:
        """Zwraca listę brakujących ocen. Pusta lista = komplet."""
        missing = []
        if ok.report_grade    is None: missing.append('ocena sprawozdania')
        if ok.supervisor_grade is None: missing.append('ocena UOPZ')
        if ok.workplace_grade  is None: missing.append('ocena ZOPZ')
        if sp.grade_1 is None and sp.grade_2 is None and sp.grade_3 is None:
            missing.append('co najmniej jedna ocena ze sprawdzianu')
        return missing


    @staticmethod
    def get_pilne_oceny(uopz_id=None) -> list[dict]:
        """Zwraca listę praktyk z pilnymi ocenami (termin ≤ 3 dni)."""
        q = db.session.query(InternshipEnrollment).filter_by(status=EnrollmentStatus.COMPLETED)
        if uopz_id:
            q = q.filter_by(supervisor_id=uopz_id)

        pilne = []
        for zapis in q.all():
            if zapis.termin_do:
                deadline       = zapis.termin_do + timedelta(days=7)
                dni_do_konca   = (deadline - date.today()).days
                if dni_do_konca <= 3:
                    pilne.append({
                        'zapis':           zapis,
                        'deadline':        deadline,
                        'dni_do_deadline': dni_do_konca,
                        'przekroczony':    dni_do_konca < 0,
                    })
        return sorted(pilne, key=lambda x: x['dni_do_deadline'])

    @staticmethod
    def auto_complete_internships() -> dict:
        """Automatycznie zamyka praktyki z przekroczonym terminem.

        Warunek zamknięcia: data końcowa minęła ORAZ student zarejestrował
        co najmniej tyle godzin, ile wymaga edycja praktyki (required_hours).
        Praktyki bez wymaganego wymiaru godzin są pomijane — pozostają
        w statusie IN_PROGRESS i wymagają ręcznej interwencji opiekuna.

        Returns:
            dict z kluczami 'completed' (zamknięte) i 'skipped' (pominięte
            z powodu niewystarczających godzin).
        """
        kandydaci = db.session.query(InternshipEnrollment).filter(
            InternshipEnrollment.status == EnrollmentStatus.IN_PROGRESS,
            InternshipEnrollment.end_date < date.today(),
        ).all()

        completed = skipped = 0
        for p in kandydaci:
            required = p.internship.required_hours if p.internship else 0
            if p.total_hours_logged >= required:
                from core.uslugi.workflow import ZapisFSM
                ZapisFSM(p).zakoncz()
                completed += 1
            else:
                skipped += 1
                import logging
                logging.getLogger(__name__).warning(
                    "auto_complete: pominięto zapis %s — %d/%d h (student: %s %s)",
                    p.id, p.total_hours_logged, required,
                    p.student.first_name if p.student else '?',
                    p.student.last_name  if p.student else '?',
                )

        if completed:
            db.session.commit()
        return {'completed': completed, 'skipped': skipped}
