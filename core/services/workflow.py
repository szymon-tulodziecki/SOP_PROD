"""core/uslugi/workflow.py

Maszyna Stanów (FSM) dla InternshipEnrollment.

Każda metoda publiczna reprezentuje jedno legalne przejście między stanami.
Nielegalne przejście rzuca IllegalTransitionError — kontrolery łapią ten
wyjątek i tłumaczą na flash/HTTP 400, nigdy nie modyfikując statusu
bezpośrednio.

Diagram przejść:
  PENDING
    → submit_for_approval()       → AWAITING_APPROVAL  (ścieżka A)
    → submit_to_committee()          → COMMISSION_REVIEW   (ścieżki B/C)

  AWAITING_APPROVAL
    → approve_by_supervisor()       → IN_PROGRESS         (ścieżka A)
    → reject()                     → REJECTED
    → submit_to_committee()          → COMMISSION_REVIEW   (ścieżki B/C, po komentarzu UOPZ)

  COMMISSION_REVIEW | REVISION_REQUIRED
    → approve_by_committee()    → DIRECTOR_APPROVAL
    → request_revision()             → REVISION_REQUIRED
    → reject()                     → REJECTED

  DIRECTOR_APPROVAL
    → approve_by_director()  → IN_PROGRESS
    → reject()                     → REJECTED

  IN_PROGRESS
    → complete()                    → COMPLETED

  COMPLETED  (terminal — brak wyjść)
  REJECTED   (terminal — brak wyjść)
"""
from __future__ import annotations

from core.models.internships import EnrollmentStatus as S

# ---------------------------------------------------------------------------
# Wyjątek dziedziny
# ---------------------------------------------------------------------------

class IllegalTransitionError(ValueError):
    """Próba nielegalnego przejścia między stanami."""
    def __init__(self, current: S, attempted: S, reason: str = ''):
        from core.i18n import t
        msg = t('Niedozwolone przejście: {obecny} → {cel}', obecny=current.value, cel=attempted.value)
        if reason:
            msg += f" ({t(reason)})"
        super().__init__(msg)
        self.current  = current
        self.attempted = attempted


# ---------------------------------------------------------------------------
# Dozwolone przejścia (graf)
# ---------------------------------------------------------------------------

_ALLOWED: dict[S, set[S]] = {
    S.PENDING: {
        S.AWAITING_APPROVAL,
        S.COMMISSION_REVIEW,
    },
    S.AWAITING_APPROVAL: {
        S.IN_PROGRESS,
        S.COMMISSION_REVIEW,
        S.DIRECTOR_APPROVAL,
        S.REVISION_REQUIRED,
        S.REJECTED,
    },
    S.COMMISSION_REVIEW: {
        S.DIRECTOR_APPROVAL,
        S.REVISION_REQUIRED,
        S.REJECTED,
    },
    S.REVISION_REQUIRED: {
        S.AWAITING_APPROVAL,   # student ponownie składa (ścieżka A)
        S.COMMISSION_REVIEW,   # student ponownie składa (ścieżki B/C)
        S.DIRECTOR_APPROVAL,
        S.REVISION_REQUIRED,   # kolejna runda poprawek
        S.REJECTED,
    },
    S.DIRECTOR_APPROVAL: {
        S.IN_PROGRESS,
        S.REJECTED,
    },
    S.IN_PROGRESS: {
        S.COMPLETED,
    },
    S.COMPLETED: set(),
    S.REJECTED:  set(),
}


# ---------------------------------------------------------------------------
# FSM
# ---------------------------------------------------------------------------

class EnrollmentStateMachine:
    """Kontroler przejść stanu dla instancji InternshipEnrollment.

    Nie wykonuje commit — wywołujący odpowiada za transakcję.

    Preferowane użycie (z blokadą pesymistyczną):
        with EnrollmentStateMachine.lock(enrollment_id) as fsm:
            fsm.approve_by_committee()
            db.session.commit()

    Fallback gdy obiekt jest już załadowany:
        fsm = EnrollmentStateMachine(zapis)
        fsm.approve_by_supervisor()
        db.session.commit()
    """

    def __init__(self, zapis) -> None:
        self._zapis = zapis

    # ── Blokada pesymistyczna (SELECT ... FOR UPDATE) ──────────────────────

    @classmethod
    def lock(cls, enrollment_id) -> 'EnrollmentStateMachine':
        """Ładuje InternshipEnrollment z blokadą FOR UPDATE i zwraca FSM.

        Blokada wierszowa w PostgreSQL gwarantuje, że żaden inny proces
        Gunicorn nie zmodyfikuje statusu między odczytem a commitem.
        Blokada jest utrzymana do końca transakcji — wywołujący musi
        samodzielnie wywołać db.session.commit() przed wyjściem z bloku.

        Użycie jako context manager (zalecane):
            with EnrollmentStateMachine.lock(id) as fsm:
                fsm.approve_by_committee()
                db.session.commit()  # commit PRZED __exit__; rollback przy wyjątku

        Użycie bez context managera:
            fsm = EnrollmentStateMachine.lock(id)
            fsm.approve_by_director()
            db.session.commit()
        """
        from core.models.internships import InternshipEnrollment
        from core.extensions import db

        zapis = (
            db.session.query(InternshipEnrollment)
            .filter_by(id=enrollment_id)
            .with_for_update()
            .one_or_none()
        )
        if zapis is None:
            from flask import abort
            abort(404)
        return cls(zapis)

    # Context manager — dla czytelności kodu w kontrolerach
    def __enter__(self) -> 'EnrollmentStateMachine':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            from core.extensions import db
            db.session.rollback()

    @property
    def zapis(self):
        return self._zapis

    # ── Wewnętrzna zmiana stanu ────────────────────────────────────────────

    def _przejdz(self, cel: S, reason: str = '') -> None:
        obecny = self._zapis.status
        if cel not in _ALLOWED.get(obecny, set()):
            raise IllegalTransitionError(obecny, cel, reason)
        self._zapis.status = cel

    def _dodaj_zdarzenie(self, event_type, actor_id=None, comment: str = '',
                         decision: str = '') -> None:
        """Tworzy ProcessEvent i dodaje do sesji (bez commit)."""
        from datetime import datetime, timezone as _tz
        from core.models.internships import ProcessEvent, EventType
        from core.extensions import db
        db.session.add(ProcessEvent(
            enrollment_id=self._zapis.id,
            event_type=event_type,
            comment=comment or None,
            decision=decision or None,
            executed_by_id=actor_id,
            executed_at=datetime.now(_tz.utc),
        ))

    # ── Publiczne przejścia ───────────────────────────────────────────────

    def submit_for_approval(self) -> None:
        """PENDING → AWAITING_APPROVAL. Auto-przypisuje UOPZ jeśli brak."""
        if not self.zapis.supervisor_id:
            self._auto_przypisz_uopz()
        self._przejdz(S.AWAITING_APPROVAL)

    def _auto_przypisz_uopz(self) -> None:
        """Przypisuje opiekuna uczelnianego z najmniejszą liczbą aktywnych zapisów."""
        from core.extensions import db
        from core.models.users import UniversityMentor
        from core.models.internships import InternshipEnrollment
        from sqlalchemy import func
        aktywne = (S.AWAITING_APPROVAL, S.IN_PROGRESS, S.COMMISSION_REVIEW,
                   S.REVISION_REQUIRED, S.DIRECTOR_APPROVAL)
        subq = (
            db.session.query(
                InternshipEnrollment.supervisor_id,
                func.count().label('cnt'),
            )
            .filter(InternshipEnrollment.status.in_(aktywne))
            .group_by(InternshipEnrollment.supervisor_id)
            .subquery()
        )
        mentor = (
            db.session.query(UniversityMentor)
            .outerjoin(subq, UniversityMentor.id == subq.c.supervisor_id)
            .filter(UniversityMentor.is_active == True)
            .order_by(func.coalesce(subq.c.cnt, 0), UniversityMentor.last_name)
            .first()
        )
        if mentor:
            self.zapis.supervisor_id = mentor.id

    def submit_to_committee(self) -> None:
        """PENDING / AWAITING_APPROVAL → COMMISSION_REVIEW (ścieżki B/C)."""
        if not self.zapis.supervisor_id:
            self._auto_przypisz_uopz()
        self._przejdz(S.COMMISSION_REVIEW)

    def resubmit_after_revision(self) -> None:
        """REVISION_REQUIRED → AWAITING_APPROVAL (ścieżka A) lub COMMISSION_REVIEW (B/C).

        Rozróżnia ścieżkę na podstawie path_type zapisu — student po poprawkach
        wraca do recenzenta, który zadał poprawki, a nie zawsze do komisji.
        """
        from core.models.internships import InternshipPath
        if self.zapis.path_type == InternshipPath.STANDARD:
            self._przejdz(S.AWAITING_APPROVAL)
        else:
            self._przejdz(S.COMMISSION_REVIEW)

    def approve_by_supervisor(self, actor_id=None, comment: str = '') -> None:
        """AWAITING_APPROVAL → IN_PROGRESS. Opcjonalnie zapisuje comment UOPZ."""
        from core.models.internships import EventType
        self._przejdz(S.IN_PROGRESS, 'decision UOPZ')
        if comment:
            self._dodaj_zdarzenie(EventType.SUPERVISOR_COMMENT, actor_id=actor_id,
                                  comment=comment)

    def send_to_director(self, decision: str, actor_id=None, comment: str = '') -> None:
        """COMMISSION_REVIEW / AWAITING_APPROVAL / REVISION_REQUIRED → DIRECTOR_APPROVAL.

        decision: 'APPROVED' | 'PARTIALLY_APPROVED' | 'REJECTED'
        """
        from core.models.internships import EventType
        self._przejdz(S.DIRECTOR_APPROVAL, 'opinia komisji')
        self._dodaj_zdarzenie(EventType.COMMITTEE_DECISION, actor_id=actor_id,
                              comment=comment, decision=decision)

    def approve_by_committee(self, actor_id=None, comment: str = '') -> None:
        """COMMISSION_REVIEW / REVISION_REQUIRED -> DIRECTOR_APPROVAL."""
        self.send_to_director(decision='APPROVED', actor_id=actor_id, comment=comment)

    def request_revision(self, actor_id=None, comment: str = '', event_type=None) -> None:
        """Wysyła zapis do poprawek i zapisuje właściwy event_type process_events."""
        from core.models.internships import EventType
        event_type = event_type or EventType.COMMITTEE_DECISION
        opis_by_type = {
            EventType.ADMIN_COMMENT: 'admin: wymaga uzupełnień',
            EventType.SUPERVISOR_COMMENT: 'supervisor: wymaga uzupełnień',
            EventType.COMMITTEE_DECISION: 'komisja: wymaga uzupełnień',
        }
        opis = opis_by_type.get(event_type, 'wymaga uzupełnień')
        self._przejdz(S.REVISION_REQUIRED, opis)
        self._dodaj_zdarzenie(event_type, actor_id=actor_id,
                              comment=comment, decision='PARTIALLY_APPROVED')

    def approve_by_director(self, actor_id=None, comment: str = '') -> None:
        """DIRECTOR_APPROVAL → IN_PROGRESS."""
        from core.models.internships import EventType
        self._przejdz(S.IN_PROGRESS, 'decision dyrektora')
        self._dodaj_zdarzenie(EventType.DIRECTOR_DECISION, actor_id=actor_id,
                              comment=comment, decision='APPROVED')


    def reject(self, actor_id=None, comment: str = '',
               event_type=None) -> None:
        """Dowolny aktywny stan → REJECTED."""
        from core.models.internships import EventType
        self._przejdz(S.REJECTED)
        et = event_type or EventType.SUPERVISOR_COMMENT
        self._dodaj_zdarzenie(et, actor_id=actor_id,
                              comment=comment, decision='REJECTED')

    def complete(self) -> None:
        """IN_PROGRESS → COMPLETED."""
        self._przejdz(S.COMPLETED)
