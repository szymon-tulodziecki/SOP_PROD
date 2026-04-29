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
from core.modele import (
    AssessmentResult,
    EnrollmentStatus,
    Examination,
    FinalGrades,
    InternshipEnrollment,
    OutcomeAssessment,
)

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


class EvaluationService:
    @staticmethod
    def parse_grade(value: str) -> float | None:
        if not value or not value.strip():
            return None
        try:
            return float(value.strip().replace(',', '.'))
        except (ValueError, AttributeError):
            raise ValueError(f'Nieprawidłowa wartość oceny: {value!r}')

    @staticmethod
    def upsert_assessment(outcome, result_str, notes, existing_assessments, enrollment_id) -> None:
        if not result_str:
            return
        try:
            result = AssessmentResult[result_str]
        except KeyError:
            return

        assessment = existing_assessments.get(str(outcome.id))
        if assessment:
            assessment.result = result
            assessment.notes = notes or None
            return

        import uuid
        from core.repozytoria import AssessmentRepository

        AssessmentRepository().zapisz(OutcomeAssessment(
            id=uuid.uuid4(),
            enrollment_id=enrollment_id,
            learning_outcome_id=outcome.id,
            result=result,
            notes=notes or None,
        ))

    @staticmethod
    def calculate_final_grade(enrollment: InternshipEnrollment) -> float | None:
        return enrollment.final_grade


class SerwisOceniania(EvaluationService):

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
        ok = zapis.final_grades or FinalGrades(enrollment_id=zapis.id)
        if ok not in db.session:
            db.session.add(ok)

        ok.report_grade                 = dane.report_grade
        ok.supervisor_grade             = dane.supervisor_grade
        ok.workplace_grade              = dane.workplace_grade
        ok.supervisor_grade_description = dane.supervisor_grade_description
        ok.workplace_grade_description  = dane.workplace_grade_description

        sp = zapis.examination or Examination(enrollment_id=zapis.id)
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
            from core.modele.internships import InternshipPath
            is_path_b = zapis.path_type in (InternshipPath.EMPLOYMENT, InternshipPath.OWN_BUSINESS)
            missing = SerwisOceniania._waliduj_kompletnosc(ok, sp, is_path_b=is_path_b)
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
    def _waliduj_kompletnosc(ok, sp, is_path_b: bool = False) -> list[str]:
        """Zwraca listę brakujących ocen. Pusta lista = komplet."""
        missing = []
        if ok.report_grade is None:
            missing.append('ocena sprawozdania (S)')
        if not is_path_b:
            if ok.supervisor_grade is None: missing.append('ocena UOPZ (U)')
            if ok.workplace_grade  is None: missing.append('ocena ZOPZ (Z)')
        if sp.grade_1 is None and sp.grade_2 is None and sp.grade_3 is None:
            missing.append('co najmniej jedna ocena ze sprawdzianu')
        return missing


    @staticmethod
    def deadline_info(enrollment) -> dict:
        """Zwraca słownik z informacjami o terminie oceny dla danego zapisu."""
        deadline = days_to_deadline = None
        overdue = False
        if enrollment.end_date and enrollment.status == EnrollmentStatus.COMPLETED:
            deadline         = enrollment.end_date + timedelta(days=7)
            days_to_deadline = (deadline - date.today()).days
            overdue          = days_to_deadline < 0
        return {
            'deadline':         deadline,
            'dni_do_deadline':  days_to_deadline,
            'przekroczony':     overdue,
            'deadline_is_today': days_to_deadline == 0 if days_to_deadline is not None else False,
        }

    @staticmethod
    def get_pilne_oceny(uopz_id=None) -> list[dict]:
        """Zwraca listę praktyk z pilnymi ocenami (termin ≤ 3 dni)."""
        q = db.session.query(InternshipEnrollment).filter_by(status=EnrollmentStatus.COMPLETED)
        if uopz_id:
            q = q.filter_by(supervisor_id=uopz_id)

        pilne = []
        for zapis in q.all():
            info = SerwisOceniania.deadline_info(zapis)
            if info['dni_do_deadline'] is not None and info['dni_do_deadline'] <= 3:
                pilne.append({'zapis': zapis, **info})
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

    @staticmethod
    def przygotuj_liste_ocen(supervisor_id=None, filtr: str | None = None) -> dict:
        """Zwraca dane do widoku listy ocen.

        Returns:
            {'widoczne': [...], 'zakonczone': [...], 'filtr': filtr}
        """
        from core.repozytoria import EnrollmentRepository
        enrollments = EnrollmentRepository().aktywne_i_zakonczone(supervisor_id=supervisor_id)

        def _ma_oceny(enrollment) -> bool:
            fg = enrollment.final_grades
            if not fg:
                return False
            if enrollment.is_path_b:
                return fg.report_grade is not None and enrollment.exam_grade is not None
            return (fg.supervisor_grade is not None
                    and fg.report_grade is not None and fg.workplace_grade is not None)

        enriched = [
            {
                'zapis':      e,
                'w_trakcie':  e.status == EnrollmentStatus.IN_PROGRESS,
                'zakonczona': e.status == EnrollmentStatus.COMPLETED,
                'is_path_b':  e.is_path_b,
                **SerwisOceniania.deadline_info(e),
            }
            for e in enrollments
        ]

        completed_list = [z for z in enriched
                          if z['zakonczona'] or (z['w_trakcie'] and z['is_path_b'])]

        for z in completed_list:
            z['oceniony'] = _ma_oceny(z['zapis'])

        completed_list.sort(key=lambda z: z['oceniony'])

        if filtr == 'nieocenione':
            visible = [z for z in completed_list if not z['oceniony']]
        elif filtr == 'ocenione':
            visible = [z for z in completed_list if z['oceniony']]
        else:
            visible = completed_list

        return {'widoczne': visible, 'zakonczone': completed_list, 'filtr': filtr}
