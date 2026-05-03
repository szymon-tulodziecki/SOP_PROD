"""core/uslugi/praktyki.py

Internship and enrollment management service.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from core.extensions import db
from core.models.internships import (
    Internship,
    InternshipStatus,
    InternshipEnrollment,
    EnrollmentStatus,
    InternshipPath,
    EventType,
    ProcessEvent,
    InternshipReport,
)
from core.repositories.internships import InternshipRepository, EnrollmentRepository


def _last_event_comment(enrollment_id, event_type, decision: str) -> str | None:
    ev = (
        db.session.query(ProcessEvent)
        .filter_by(enrollment_id=enrollment_id, event_type=event_type)
        .filter(ProcessEvent.decision == decision)
        .order_by(ProcessEvent.executed_at.desc())
        .first()
    )
    return ev.comment if ev else None


class InternshipService:
    """Business logic for internship editions and enrollment processing."""

    def __init__(
        self,
        repo_praktyk: Optional[InternshipRepository] = None,
        repo_zapisow: Optional[EnrollmentRepository] = None,
    ) -> None:
        self._praktyki = repo_praktyk or InternshipRepository()
        self._zapisy   = repo_zapisow  or EnrollmentRepository()

    # ── Internship editions ───────────────────────────────────────────────────

    def create_edition(self, rok_uczelniany: str, semestr: str, wymiar_godzin: int = 160) -> Internship:
        internship = Internship(
            academic_year=rok_uczelniany,
            semester=semestr,
            required_hours=wymiar_godzin,
            status=InternshipStatus.INACTIVE,
        )
        self._praktyki.zapisz(internship)
        db.session.commit()
        return internship

    def activate_edition(self, internship: Internship) -> None:
        internship.status = InternshipStatus.ACTIVE
        db.session.commit()

    def deactivate_edition(self, internship: Internship) -> None:
        internship.status = InternshipStatus.INACTIVE
        db.session.commit()

    # ── Student enrollments ───────────────────────────────────────────────────

    def enroll_student(
        self,
        student_id: uuid.UUID,
        internship_id: uuid.UUID,
        path: InternshipPath = InternshipPath.STANDARD,
    ) -> InternshipEnrollment:
        if self._zapisy.student_ma_aktywny_zapis(student_id, internship_id):
            raise ValueError('Student ma już aktywne zgłoszenie do tej edycji praktyk.')
        zapis = InternshipEnrollment(
            student_id=student_id,
            internship_id=internship_id,
            path_type=path,
            status=EnrollmentStatus.PENDING,
        )
        self._zapisy.zapisz(zapis)
        db.session.commit()
        return zapis

    def change_status(
        self,
        zapis: InternshipEnrollment,
        nowy_status: EnrollmentStatus,
        comment: Optional[str] = None,
        executed_by_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Changes enrollment status via FSM public methods."""
        from core.services.workflow import EnrollmentStateMachine, IllegalTransitionError
        fsm = EnrollmentStateMachine(zapis)
        _dispatch = {
            EnrollmentStatus.AWAITING_APPROVAL: fsm.submit_for_approval,
            EnrollmentStatus.COMMISSION_REVIEW: fsm.submit_to_committee,
            EnrollmentStatus.IN_PROGRESS:       fsm.approve_by_supervisor,
            EnrollmentStatus.DIRECTOR_APPROVAL:     fsm.approve_by_committee,
            EnrollmentStatus.COMPLETED:         fsm.complete,
            EnrollmentStatus.REJECTED:          fsm.reject,
        }
        method = _dispatch.get(nowy_status)
        if method is None:
            raise ValueError(f'Nieobsługiwany status docelowy: {nowy_status!r}')
        method()

        if comment is not None:
            if nowy_status in (EnrollmentStatus.REJECTED, EnrollmentStatus.AWAITING_APPROVAL):
                event_type = EventType.ADMIN_COMMENT
            elif nowy_status == EnrollmentStatus.COMMISSION_REVIEW:
                event_type = EventType.SUPERVISOR_COMMENT
            else:
                event_type = EventType.ADMIN_COMMENT
            self._dodaj_zdarzenie(zapis, event_type, comment=comment, executed_by_id=executed_by_id)

        db.session.commit()

    def approve_by_supervisor(
        self,
        enrollment_id: uuid.UUID,
        actor_id: uuid.UUID,
        comment: str = '',
        supervisor_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Zatwierdza zgłoszenie przez UOPZ (z opcjonalnym przypisaniem opiekuna). Commit w serwisie."""
        from core.services.workflow import EnrollmentStateMachine
        with EnrollmentStateMachine.lock(enrollment_id) as fsm:
            if supervisor_id is not None:
                fsm.zapis.supervisor_id = supervisor_id
            fsm.approve_by_supervisor(actor_id=actor_id, comment=comment)
            db.session.commit()

    def request_revision(
        self,
        enrollment_id: uuid.UUID,
        actor_id: uuid.UUID,
        comment: str = '',
    ) -> None:
        """Wysyła prośbę o poprawki do studenta. Commit w serwisie."""
        from core.services.workflow import EnrollmentStateMachine
        from core.models import EnrollmentStatus, EventType, User, UserRole
        with EnrollmentStateMachine.lock(enrollment_id) as fsm:
            actor = db.session.get(User, actor_id) if actor_id else None
            actor_role = actor.role if actor else None
            if actor_role == UserRole.KOMISJA or fsm.zapis.status == EnrollmentStatus.COMMISSION_REVIEW:
                event_type = EventType.COMMITTEE_DECISION
            elif actor_role == UserRole.UOPZ:
                event_type = EventType.SUPERVISOR_COMMENT
            else:
                event_type = EventType.ADMIN_COMMENT
            fsm.request_revision(actor_id=actor_id, comment=comment, event_type=event_type)
            db.session.commit()

    def submit_for_approval_with_supervisor(
        self,
        enrollment_id: uuid.UUID,
        supervisor_id: uuid.UUID,
    ) -> None:
        """Przypisuje UOPZ i wysyła zgłoszenie do zatwierdzenia. Commit w serwisie."""
        from core.services.workflow import EnrollmentStateMachine
        with EnrollmentStateMachine.lock(enrollment_id) as fsm:
            fsm.zapis.supervisor_id = supervisor_id
            fsm.submit_for_approval()
            db.session.commit()

    def apply_director_decision(
        self,
        enrollment_id: uuid.UUID,
        decision: str,
        actor_id: uuid.UUID,
        comment: str = '',
    ) -> None:
        """Wykonuje decyzję dyrektora (APPROVED/REJECTED). Commit w serwisie."""
        from core.services.workflow import EnrollmentStateMachine, IllegalTransitionError
        from core.models.internships import EventType
        with EnrollmentStateMachine.lock(enrollment_id) as fsm:
            if decision == 'APPROVED':
                fsm.approve_by_director(actor_id=actor_id, comment=comment)
            else:
                fsm.reject(actor_id=actor_id,
                           comment=f"Dyrektor nie wyraził zgody: {comment}",
                           event_type=EventType.DIRECTOR_DECISION)
            db.session.commit()

    def assign_supervisor(self, zapis: InternshipEnrollment, supervisor_id: uuid.UUID) -> None:
        zapis.supervisor_id = supervisor_id
        db.session.commit()

    def approve_by_committee(
        self,
        zapis: InternshipEnrollment,
        decision: str,
        comment: Optional[str] = None,
        executed_by_id: Optional[uuid.UUID] = None,
    ) -> None:
        from core.services.workflow import EnrollmentStateMachine
        self._dodaj_zdarzenie(
            zapis, EventType.COMMITTEE_DECISION,
            decision=decision, comment=comment,
            executed_by_id=executed_by_id,
        )
        fsm = EnrollmentStateMachine(zapis)
        if decision == 'APPROVED':
            fsm.approve_by_committee()
        else:
            fsm.reject()
        db.session.commit()

    def approve_by_director(
        self,
        zapis: InternshipEnrollment,
        decision: str,
        comment: Optional[str] = None,
        executed_by_id: Optional[uuid.UUID] = None,
    ) -> None:
        from core.services.workflow import EnrollmentStateMachine
        self._dodaj_zdarzenie(
            zapis, EventType.DIRECTOR_DECISION,
            decision=decision, comment=comment,
            executed_by_id=executed_by_id,
        )
        fsm = EnrollmentStateMachine(zapis)
        if decision == 'APPROVED':
            fsm.approve_by_director()
        else:
            fsm.reject()
        db.session.commit()

    def notify_student(
        self,
        zapis: InternshipEnrollment,
        comment: Optional[str] = None,
        executed_by_id: Optional[uuid.UUID] = None,
    ) -> None:
        self._dodaj_zdarzenie(
            zapis, EventType.STUDENT_NOTIFICATION,
            comment=comment,
            executed_by_id=executed_by_id,
        )
        db.session.commit()

    def complete(self, zapis: InternshipEnrollment) -> None:
        from core.services.workflow import EnrollmentStateMachine
        EnrollmentStateMachine(zapis).complete()
        db.session.commit()

    # ── Reports ───────────────────────────────────────────────────────────────

    def get_or_create_report(self, zapis: InternshipEnrollment) -> InternshipReport:
        if zapis.report is None:
            report = InternshipReport(enrollment_id=zapis.id)
            db.session.add(report)
            db.session.flush()
            return report
        return zapis.report

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _dodaj_zdarzenie(
        self,
        zapis: InternshipEnrollment,
        event_type: EventType,
        decision: Optional[str] = None,
        comment: Optional[str] = None,
        executed_by_id: Optional[uuid.UUID] = None,
    ) -> ProcessEvent:
        zdarzenie = ProcessEvent(
            enrollment_id=zapis.id,
            event_type=event_type,
            decision=decision,
            comment=comment,
            executed_by_id=executed_by_id,
            executed_at=datetime.now(timezone.utc),
        )
        db.session.add(zdarzenie)
        return zdarzenie

    # ── Student-facing helpers ────────────────────────────────────────────────

    @staticmethod
    def validate_completion_allowed(zapis) -> tuple[bool, str]:
        """Sprawdza czy praktykę STANDARD można zakończyć.

        Returns:
            (True, '') jeśli można zakończyć,
            (False, komunikat) jeśli warunek nie jest spełniony.
        """
        wymagane      = zapis.internship.required_hours if zapis.internship else 0
        zalogowane    = zapis.total_hours_logged or 0
        liczba_wpisow = len(zapis.journal_entries)

        if liczba_wpisow == 0:
            return False, 'Nie można zakończyć praktyki bez wpisów w dzienniku.'
        if zalogowane < wymagane:
            return (
                False,
                f'Nie można zakończyć praktyki — zalogowano {zalogowane} z wymaganych {wymagane} godzin.',
            )
        return True, ''

    @staticmethod
    def student_status(zapis) -> dict:
        """Analizuje zapis i zwraca gotowy dict do widoku listy praktyk studenta."""
        komentarz_admina = zapis.admin_comments
        supervisor_comment   = zapis.supervisor_comments
        path = zapis.path_type.value if zapis.path_type else None

        zwrocone_a = (
            zapis.status == EnrollmentStatus.PENDING
            and bool(komentarz_admina or supervisor_comment)
        )
        zwrocone_bc = (
            zapis.status == EnrollmentStatus.AWAITING_APPROVAL
            and bool(supervisor_comment)
            and path in ('EMPLOYMENT', 'OWN_BUSINESS')
        )
        zwrocone_komisja = (zapis.status == EnrollmentStatus.REVISION_REQUIRED)
        in_review = zapis.status in (EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.DIRECTOR_APPROVAL)
        zwrocone = (zwrocone_a or zwrocone_bc or zwrocone_komisja) and not in_review

        komentarz_komisji = (
            _last_event_comment(zapis.id, EventType.COMMITTEE_DECISION, 'PARTIALLY_APPROVED')
            if zwrocone_komisja else None
        )
        komentarz_odrzucenia = (
            _last_event_comment(zapis.id, EventType.COMMITTEE_DECISION, 'REJECTED')
            if zapis.status == EnrollmentStatus.REJECTED else None
        )

        jest_odrzucone = zapis.status == EnrollmentStatus.REJECTED
        border_alert   = zwrocone or jest_odrzucone

        return {
            'id':                   str(zapis.id),
            'status':               zapis.status.value,
            'status_css_class':     zapis.status_css_class,
            'status_label':         zapis.status_label,
            'path':              path,
            'is_standard':          path == 'STANDARD',
            'zwrocone':             zwrocone,
            'jest_odrzucone':       jest_odrzucone,
            'border_alert':         border_alert,
            'komentarz_zwrotny':    komentarz_komisji or komentarz_admina or supervisor_comment or '',
            'komentarz_odrzucenia': komentarz_odrzucenia or '',
            'wymaga_uwagi': zwrocone or jest_odrzucone,
        }

    # ── Repository access ─────────────────────────────────────────────────────

    @property
    def praktyki(self) -> InternshipRepository:
        return self._praktyki

    @property
    def zapisy(self) -> EnrollmentRepository:
        return self._zapisy
