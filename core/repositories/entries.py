"""core/repozytoria/wpisy.py — Repozytorium wpisów dziennika praktyk."""

from __future__ import annotations

from typing import Optional
from sqlalchemy import func

from core.extensions import db
from core.models.journal import JournalEntry


class JournalRepository:
    """Jedyne miejsce zapytań ORM dotyczących tabeli wpisów dziennika."""

    def get_by_enrollment(
        self, enrollment_id, descending: bool = True, start_date=None, end_date=None
    ) -> list[JournalEntry]:
        """Wszystkie wpisy dla danego zapisu, posortowane po dacie.

        data_od / data_do — opcjonalne filtry zakresu dat (obiekty date lub None).
        """
        order = JournalEntry.entry_date.desc() if descending else JournalEntry.entry_date
        q = db.session.query(JournalEntry).filter_by(enrollment_id=enrollment_id)
        if start_date:
            q = q.filter(JournalEntry.entry_date >= start_date)
        if end_date:
            q = q.filter(JournalEntry.entry_date <= end_date)
        return q.order_by(order).all()

    def statystyki_dla_zapisow(self, ids: list) -> dict:
        """Zwraca {enrollment_id: (max_date, count)} dla listy zapisów — jedno zapytanie SQL.

        Eliminuje pętlę N+1 w widoku listy dzienników.
        """
        if not ids:
            return {}
        rows = (
            db.session.query(
                JournalEntry.enrollment_id,
                func.max(JournalEntry.entry_date).label("ostatni"),
                func.count(JournalEntry.id).label("liczba"),
            )
            .filter(JournalEntry.enrollment_id.in_(ids))
            .group_by(JournalEntry.enrollment_id)
            .all()
        )
        return {r.enrollment_id: (r.ostatni, r.liczba) for r in rows}

    def statystyki_dla_zapisu(self, enrollment_id) -> tuple[int, int]:
        """Zwraca (liczba_wpisow, suma_godzin) dla całego dziennika zapisu."""
        row = (
            db.session.query(
                func.count(JournalEntry.id).label("liczba"),
                func.coalesce(func.sum(JournalEntry.duration_hours), 0).label("godziny"),
            )
            .filter_by(enrollment_id=enrollment_id)
            .one()
        )
        return row.liczba, row.godziny

    def znajdz_duplikat(self, enrollment_id, data) -> Optional[JournalEntry]:
        """Sprawdza czy wpis na dany dzień już istnieje."""
        return (
            db.session.query(JournalEntry)
            .filter_by(enrollment_id=enrollment_id, entry_date=data)
            .first()
        )

    def znajdz_po_id(self, wpis_id) -> Optional[JournalEntry]:
        return db.session.get(JournalEntry, wpis_id)

    def usun(self, wpis: JournalEntry) -> None:
        db.session.delete(wpis)

    def zapisz(self, wpis: JournalEntry) -> JournalEntry:
        db.session.add(wpis)
        db.session.flush()
        return wpis
