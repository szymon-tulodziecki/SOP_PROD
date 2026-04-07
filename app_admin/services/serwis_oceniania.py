"""
app_admin/services/serwis_oceniania.py
Logika biznesowa oceniania praktyk.
Przemianowano z evaluation_service.py.
"""
from datetime import date, timedelta
from core.extensions import db
from core.modele import ZapisPraktyki, StatusZapisu


class SerwisOceniania:
    @staticmethod
    def get_pilne_oceny(uopz_id=None):
        """Zwraca listę praktyk z pilnymi ocenami dla danego UOPZ lub wszystkich."""
        q = db.session.query(ZapisPraktyki).filter_by(status=StatusZapisu.COMPLETED)
        if uopz_id:
            q = q.filter_by(uopz_id=uopz_id)

        pilne_oceny = []
        for zapis in q.all():
            if zapis.termin_do:
                deadline = zapis.termin_do + timedelta(days=7)
                dni_do_deadline = (deadline - date.today()).days
                if dni_do_deadline <= 3:
                    pilne_oceny.append({
                        'zapis':           zapis,
                        'deadline':        deadline,
                        'dni_do_deadline': dni_do_deadline,
                        'przekroczony':    dni_do_deadline < 0,
                    })

        return sorted(pilne_oceny, key=lambda x: x['dni_do_deadline'])

    @staticmethod
    def auto_complete_internships():
        """Automatycznie przenosi praktyki z przekroczonym terminem do statusu COMPLETED."""
        do_zakonczenia = db.session.query(ZapisPraktyki).filter(
            ZapisPraktyki.status == StatusZapisu.IN_PROGRESS,
            ZapisPraktyki.termin_do < date.today()
        ).all()

        for praktyka in do_zakonczenia:
            praktyka.status = StatusZapisu.COMPLETED

        if do_zakonczenia:
            db.session.commit()


# Alias dla kompatybilności wstecznej
EvaluationService = SerwisOceniania
