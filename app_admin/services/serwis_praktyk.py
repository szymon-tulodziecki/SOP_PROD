"""
app_admin/services/serwis_praktyk.py
Logika biznesowa zarządzania praktykantami i zgłoszeniami.
Przemianowano z internship_service.py.
"""
import uuid
from werkzeug.security import generate_password_hash
from core.extensions import db
from core.modele import Uzytkownik, RolaUzytkownika, ZapisPraktyki, StatusZapisu


class SerwisPraktyk:
    @staticmethod
    def create_student(imie, nazwisko, email, numer_albumu,
                       plec=None, kierunek=None, specjalnosc=None, tryb_studiow=None):
        u = Uzytkownik(
            id                    = uuid.uuid4(),
            first_name            = imie.strip(),
            last_name             = nazwisko.strip(),
            email                 = email.lower().strip(),
            album_number          = numer_albumu.strip(),
            gender                = plec or None,
            field_of_study        = kierunek or None,
            specialization        = specjalnosc or None,
            study_mode            = tryb_studiow or None,
            role                  = RolaUzytkownika.STUDENT,
            password_hash         = generate_password_hash(numer_albumu.strip()),
            require_password_change = True,
            is_active             = True,
        )
        db.session.add(u)
        return u

    @staticmethod
    def approve_enrollment(enrollment_id, current_user):
        """Zatwierdza zgłoszenie, opcjonalnie przypisując opiekuna UOPZ."""
        zapis = db.session.get(ZapisPraktyki, enrollment_id)
        if not zapis:
            raise ValueError("Zapis nie istnieje.")
        zapis.status = StatusZapisu.IN_PROGRESS
        if current_user.role == RolaUzytkownika.UOPZ:
            zapis.supervisor_id = current_user.id
        db.session.commit()
        return zapis

    @staticmethod
    def assign_supervisor(enrollment_id, supervisor_id):
        zapis = db.session.get(ZapisPraktyki, enrollment_id)
        if not zapis:
            raise ValueError("Zapis nie istnieje.")
        zapis.supervisor_id = supervisor_id
        zapis.status  = StatusZapisu.AWAITING_APPROVAL
        db.session.commit()
        return zapis

    @staticmethod
    def approve_company(enrollment_id):
        zapis = db.session.get(ZapisPraktyki, enrollment_id)
        if not zapis:
            raise ValueError("Zapis nie istnieje.")
        zapis.status = StatusZapisu.IN_PROGRESS
        db.session.commit()
        return zapis


# Alias dla kompatybilności wstecznej
InternshipService = SerwisPraktyk
