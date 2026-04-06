from datetime import date, timedelta
from core.extensions import db
from core.models import ZapisPraktyki, StatusZapisu

class EvaluationService:
    @staticmethod
    def get_pilne_oceny(uopz_id=None):
        """Zwraca listę praktyk z pilnymi ocenami dla danego UOPZ lub wszystkich."""
        q = db.session.query(ZapisPraktyki).filter_by(status=StatusZapisu.COMPLETED)
        if uopz_id:
            q = q.filter_by(uopz_id=uopz_id)

        zapisy = q.all()
        pilne_oceny = []

        for zapis in zapisy:
            if zapis.termin_do:
                deadline = zapis.termin_do + timedelta(days=7)  # 7 dni na ocenę
                dni_do_deadline = (deadline - date.today()).days

                # Tylko pilne (3 dni lub mniej) lub przekroczone
                if dni_do_deadline <= 3:
                    pilne_oceny.append({
                        'zapis': zapis,
                        'deadline': deadline,
                        'dni_do_deadline': dni_do_deadline,
                        'przekroczony': dni_do_deadline < 0
                    })

        return sorted(pilne_oceny, key=lambda x: x['dni_do_deadline'])

    @staticmethod
    def auto_complete_internships():
        """Automatycznie przenosi praktyki z przekroczonym terminem do statusu COMPLETED."""
        praktyki_do_zakonczenia = db.session.query(ZapisPraktyki).filter(
            ZapisPraktyki.status == StatusZapisu.IN_PROGRESS,
            ZapisPraktyki.termin_do < date.today()
        ).all()

        for praktyka in praktyki_do_zakonczenia:
            praktyka.status = StatusZapisu.COMPLETED

        if praktyki_do_zakonczenia:
            db.session.commit()
