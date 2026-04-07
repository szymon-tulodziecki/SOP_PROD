"""
core/uslugi/ocenianie.py

Usługa oceniania praktyk — przeniesiona z app_admin/services/serwis_oceniania.py.
Należy do domeny core, bo operuje na modelu domenowym ZapisPraktyki.
"""
from __future__ import annotations
from datetime import date, timedelta
from core.extensions import db
from core.modele import ZapisPraktyki, StatusZapisu


class SerwisOceniania:
    @staticmethod
    def get_pilne_oceny(uopz_id=None) -> list[dict]:
        """Zwraca listę praktyk z pilnymi ocenami (termin ≤ 3 dni)."""
        q = db.session.query(ZapisPraktyki).filter_by(status=StatusZapisu.COMPLETED)
        if uopz_id:
            q = q.filter_by(uopz_id=uopz_id)

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
    def auto_complete_internships() -> None:
        """Automatycznie zamyka praktyki z przekroczonym terminem."""
        do_zakonczenia = db.session.query(ZapisPraktyki).filter(
            ZapisPraktyki.status == StatusZapisu.IN_PROGRESS,
            ZapisPraktyki.termin_do < date.today(),
        ).all()
        for p in do_zakonczenia:
            p.status = StatusZapisu.COMPLETED
        if do_zakonczenia:
            db.session.commit()
