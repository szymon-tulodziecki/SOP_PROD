"""core/repozytoria/wpisy.py — Repozytorium wpisów dziennika praktyk."""
from __future__ import annotations

from typing import Optional
from sqlalchemy import func

from core.extensions import db
from core.modele.dziennik import JournalEntry


class JournalRepository:
    """Jedyne miejsce zapytań ORM dotyczących tabeli wpisów dziennika."""

    def dla_zapisu(self, enrollment_id, malejaco: bool = True,
                   data_od=None, data_do=None) -> list[JournalEntry]:
        """Wszystkie wpisy dla danego zapisu, posortowane po dacie.

        data_od / data_do — opcjonalne filtry zakresu dat (obiekty date lub None).
        """
        order = JournalEntry.entry_date.desc() if malejaco else JournalEntry.entry_date
        q = db.session.query(JournalEntry).filter_by(enrollment_id=enrollment_id)
        if data_od:
            q = q.filter(JournalEntry.entry_date >= data_od)
        if data_do:
            q = q.filter(JournalEntry.entry_date <= data_do)
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
                func.max(JournalEntry.entry_date).label('ostatni'),
                func.count(JournalEntry.id).label('liczba'),
            )
            .filter(JournalEntry.enrollment_id.in_(ids))
            .group_by(JournalEntry.enrollment_id)
            .all()
        )
        return {r.enrollment_id: (r.ostatni, r.liczba) for r in rows}

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
