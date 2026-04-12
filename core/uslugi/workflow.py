"""core/uslugi/workflow.py

Maszyna Stanów (FSM) dla ZapisPraktyki.

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
    → zatwierdz_przez_komisje()    → DEAN_APPROVAL
    → zadaj_poprawki()             → REVISION_REQUIRED
    → odrzuc()                     → REJECTED

  DEAN_APPROVAL
    → zatwierdz_przez_dziekana()   → IN_PROGRESS
    → odrzuc()                     → REJECTED

  IN_PROGRESS
    → zakoncz()                    → COMPLETED

  COMPLETED  (terminal — brak wyjść)
  REJECTED   (terminal — brak wyjść)
"""
from __future__ import annotations

from core.modele.praktyki import EnrollmentStatus as S

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
        S.REJECTED,
    },
    S.COMMISSION_REVIEW: {
        S.DEAN_APPROVAL,
        S.REVISION_REQUIRED,
        S.REJECTED,
    },
    S.REVISION_REQUIRED: {
        S.DEAN_APPROVAL,
        S.REVISION_REQUIRED,   # kolejna runda poprawek
        S.REJECTED,
    },
    S.DEAN_APPROVAL: {
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
    """Kontroler przejść stanu dla instancji ZapisPraktyki.

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
        """Ładuje ZapisPraktyki z blokadą FOR UPDATE i zwraca FSM.

        Blokada wierszowa w PostgreSQL gwarantuje, że żaden inny proces
        Gunicorn nie zmodyfikuje statusu między odczytem a commitem.
        Blokada jest utrzymana do końca transakcji (db.session.commit/rollback).

        Użycie jako context manager (zalecane):
            with ZapisFSM.lock(id) as fsm:
                fsm.zatwierdz_przez_komisje()
                db.session.commit()

        Użycie bez context managera:
            fsm = ZapisFSM.lock(id)
            fsm.zatwierdz_przez_dziekana()
            db.session.commit()
        """
        from core.modele.praktyki import InternshipEnrollment
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

    # ── Publiczne przejścia ───────────────────────────────────────────────

    def wyslij_do_akceptacji(self) -> None:
        """PENDING → AWAITING_APPROVAL (ścieżka standardowa A)."""
        self._przejdz(S.AWAITING_APPROVAL)

    def wyslij_do_komisji(self) -> None:
        """PENDING / AWAITING_APPROVAL → COMMISSION_REVIEW (ścieżki B/C)."""
        self._przejdz(S.COMMISSION_REVIEW)

    def zatwierdz_przez_uopz(self) -> None:
        """AWAITING_APPROVAL → IN_PROGRESS."""
        self._przejdz(S.IN_PROGRESS, 'decyzja UOPZ')

    def zatwierdz_przez_komisje(self) -> None:
        """COMMISSION_REVIEW / REVISION_REQUIRED → DEAN_APPROVAL."""
        self._przejdz(S.DEAN_APPROVAL, 'decyzja komisji')

    def zadaj_poprawki(self) -> None:
        """COMMISSION_REVIEW / REVISION_REQUIRED → REVISION_REQUIRED."""
        self._przejdz(S.REVISION_REQUIRED, 'komisja: wymaga uzupełnień')

    def zatwierdz_przez_dziekana(self) -> None:
        """DEAN_APPROVAL → IN_PROGRESS."""
        self._przejdz(S.IN_PROGRESS, 'decyzja dziekana')

    def zakoncz(self) -> None:
        """IN_PROGRESS → COMPLETED."""
        self._przejdz(S.COMPLETED)

    def odrzuc(self) -> None:
        """Dowolny aktywny stan → REJECTED."""
        self._przejdz(S.REJECTED)
