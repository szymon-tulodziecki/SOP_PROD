"""core/uslugi/workflow.py

Maszyna Stanów (FSM) dla InternshipEnrollment.

Każda metoda publiczna reprezentuje jedno legalne przejście między stanami.
Nielegalne przejście rzuca IllegalTransitionError — kontrolery łapią ten
wyjątek i tłumaczą na flash/HTTP 400, nigdy nie modyfikując statusu
bezpośrednio.

Diagram przejść:
  PENDING
    → wyslij_do_akceptacji()       → AWAITING_APPROVAL  (ścieżka A)
    → wyslij_do_komisji()          → COMMISSION_REVIEW   (ścieżki B/C)

  AWAITING_APPROVAL
    → zatwierdz_przez_uopz()       → IN_PROGRESS         (ścieżka A)
    → odrzuc()                     → REJECTED
    → wyslij_do_komisji()          → COMMISSION_REVIEW   (ścieżki B/C, po komentarzu UOPZ)

  COMMISSION_REVIEW | REVISION_REQUIRED
    → zatwierdz_przez_komisje()    → DIRECTOR_APPROVAL
    → zadaj_poprawki()             → REVISION_REQUIRED
    → odrzuc()                     → REJECTED

  DIRECTOR_APPROVAL
    → zatwierdz_przez_dyrektora()  → IN_PROGRESS
    → odrzuc()                     → REJECTED

  IN_PROGRESS
    → zakoncz()                    → COMPLETED

  COMPLETED  (terminal — brak wyjść)
  REJECTED   (terminal — brak wyjść)
"""
from __future__ import annotations

from core.modele.internships import EnrollmentStatus as S

# ---------------------------------------------------------------------------
# Wyjątek dziedziny
# ---------------------------------------------------------------------------

class IllegalTransitionError(ValueError):
    """Próba nielegalnego przejścia między stanami."""
    def __init__(self, current: S, attempted: S, reason: str = ''):
        msg = (
            f"Niedozwolone przejście: {current.value} → {attempted.value}"
            + (f" ({reason})" if reason else "")
        )
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

class ZapisFSM:
    """Kontroler przejść stanu dla instancji InternshipEnrollment.

    Nie wykonuje commit — wywołujący odpowiada za transakcję.

    Preferowane użycie (z blokadą pesymistyczną):
        with ZapisFSM.lock(enrollment_id) as fsm:
            fsm.zatwierdz_przez_komisje()
            db.session.commit()

    Fallback gdy obiekt jest już załadowany:
        fsm = ZapisFSM(zapis)
        fsm.zatwierdz_przez_uopz()
        db.session.commit()
    """

    def __init__(self, zapis) -> None:
        self._zapis = zapis

    # ── Blokada pesymistyczna (SELECT ... FOR UPDATE) ──────────────────────

    @classmethod
    def lock(cls, enrollment_id) -> 'ZapisFSM':
        """Ładuje InternshipEnrollment z blokadą FOR UPDATE i zwraca FSM.

        Blokada wierszowa w PostgreSQL gwarantuje, że żaden inny proces
        Gunicorn nie zmodyfikuje statusu między odczytem a commitem.
        Blokada jest utrzymana do końca transakcji (db.session.commit/rollback).

        Użycie jako context manager (zalecane):
            with ZapisFSM.lock(id) as fsm:
                fsm.zatwierdz_przez_komisje()
                db.session.commit()

        Użycie bez context managera:
            fsm = ZapisFSM.lock(id)
            fsm.zatwierdz_przez_dyrektora()
            db.session.commit()
        """
        from core.modele.internships import InternshipEnrollment
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
    def __enter__(self) -> 'ZapisFSM':
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
        from core.modele.internships import ProcessEvent, EventType
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

    def wyslij_do_akceptacji(self) -> None:
        """PENDING → AWAITING_APPROVAL. Auto-przypisuje UOPZ jeśli brak."""
        if not self.zapis.supervisor_id:
            self._auto_przypisz_uopz()
        self._przejdz(S.AWAITING_APPROVAL)

    def _auto_przypisz_uopz(self) -> None:
        """Przypisuje opiekuna uczelnianego z najmniejszą liczbą aktywnych zapisów."""
        from core.extensions import db
        from core.modele.users import UniversityMentor
        from core.modele.internships import InternshipEnrollment
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

    def wyslij_do_komisji(self) -> None:
        """PENDING / AWAITING_APPROVAL → COMMISSION_REVIEW (ścieżki B/C)."""
        if not self.zapis.supervisor_id:
            self._auto_przypisz_uopz()
        self._przejdz(S.COMMISSION_REVIEW)

    def wyslij_ponownie_po_poprawkach(self) -> None:
        """REVISION_REQUIRED → AWAITING_APPROVAL (ścieżka A) lub COMMISSION_REVIEW (B/C).

        Rozróżnia ścieżkę na podstawie path_type zapisu — student po poprawkach
        wraca do recenzenta, który zadał poprawki, a nie zawsze do komisji.
        """
        from core.modele.internships import InternshipPath
        if self.zapis.path_type == InternshipPath.STANDARD:
            self._przejdz(S.AWAITING_APPROVAL)
        else:
            self._przejdz(S.COMMISSION_REVIEW)

    def zatwierdz_przez_uopz(self, actor_id=None, comment: str = '') -> None:
        """AWAITING_APPROVAL → IN_PROGRESS. Opcjonalnie zapisuje komentarz UOPZ."""
        from core.modele.internships import EventType
        self._przejdz(S.IN_PROGRESS, 'decyzja UOPZ')
        if comment:
            self._dodaj_zdarzenie(EventType.SUPERVISOR_COMMENT, actor_id=actor_id,
                                  comment=comment)

    def wyslij_do_dyrektora(self, decision: str, actor_id=None, comment: str = '') -> None:
        """COMMISSION_REVIEW / AWAITING_APPROVAL / REVISION_REQUIRED → DIRECTOR_APPROVAL.

        decision: 'APPROVED' | 'PARTIALLY_APPROVED' | 'REJECTED'
        """
        from core.modele.internships import EventType
        self._przejdz(S.DIRECTOR_APPROVAL, 'opinia komisji')
        self._dodaj_zdarzenie(EventType.COMMITTEE_DECISION, actor_id=actor_id,
                              comment=comment, decision=decision)

    def zatwierdz_przez_komisje(self, actor_id=None, comment: str = '') -> None:
        """COMMISSION_REVIEW / REVISION_REQUIRED → DIRECTOR_APPROVAL (backward compat)."""
        self.wyslij_do_dyrektora(decision='APPROVED', actor_id=actor_id, comment=comment)

    def zadaj_poprawki(self, actor_id=None, comment: str = '') -> None:
        """COMMISSION_REVIEW / REVISION_REQUIRED → REVISION_REQUIRED."""
        from core.modele.internships import EventType
        self._przejdz(S.REVISION_REQUIRED, 'komisja: wymaga uzupełnień')
        self._dodaj_zdarzenie(EventType.COMMITTEE_DECISION, actor_id=actor_id,
                              comment=comment, decision='PARTIALLY_APPROVED')

    def zatwierdz_przez_dyrektora(self, actor_id=None, comment: str = '') -> None:
        """DIRECTOR_APPROVAL → IN_PROGRESS."""
        from core.modele.internships import EventType
        self._przejdz(S.IN_PROGRESS, 'decyzja dyrektora')
        self._dodaj_zdarzenie(EventType.DIRECTOR_DECISION, actor_id=actor_id,
                              comment=comment, decision='APPROVED')


    def odrzuc(self, actor_id=None, comment: str = '',
               event_type=None) -> None:
        """Dowolny aktywny stan → REJECTED."""
        from core.modele.internships import EventType
        self._przejdz(S.REJECTED)
        et = event_type or EventType.SUPERVISOR_COMMENT
        self._dodaj_zdarzenie(et, actor_id=actor_id,
                              comment=comment, decision='REJECTED')

    def zakoncz(self) -> None:
        """IN_PROGRESS → COMPLETED."""
        self._przejdz(S.COMPLETED)
