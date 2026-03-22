"""celery_app.py
Konfiguracja Celery i taski generowania PDF.
"""
import os
from celery import Celery

BROKER_URL  = os.environ.get('CELERY_BROKER_URL',  'redis://localhost:6379/0')
RESULT_URL  = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

celery = Celery(
    'ans_praktyki',
    broker=BROKER_URL,
    backend=RESULT_URL,
    include=['celery_app'],
)

celery.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='Europe/Warsaw',
    enable_utc=True,
    task_track_started=True,
    result_expires=3600,  # wyniki trzymamy 1h
)


@celery.task(bind=True, name='generate_pdf_dziennik')
def generate_pdf_dziennik(self, enrollment_id: str) -> dict:
    """
    Task Celery: generuje PDF dziennika dla danego zapisu.
    Zwraca słownik z kluczem 'path' — ścieżką do pliku PDF.
    """
    import uuid
    from pathlib import Path
    from datetime import date

    try:
        self.update_state(state='STARTED', meta={'progress': 0})

        # Import modeli wewnątrz taska (worker ma własny kontekst)
        from app_admin.extensions import db
        from app_admin.models import ZapisPraktyki, WpisDziennika

        # Musimy mieć kontekst aplikacji Flask
        from app_admin import create_app
        app = create_app()

        with app.app_context():
            zapis = db.session.get(ZapisPraktyki, uuid.UUID(enrollment_id))
            if not zapis:
                raise ValueError(f'Zapis {enrollment_id} nie istnieje')

            wpisy = db.session.query(WpisDziennika)\
                      .filter_by(enrollment_id=zapis.id)\
                      .order_by(WpisDziennika.entry_date)\
                      .all()

            self.update_state(state='STARTED', meta={'progress': 30})

            from tex_engine.pdf_service import pdf_service

            class _FakePraktyka:
                def __init__(self, z, w):
                    self.id                 = z.id
                    self.student            = z.student
                    self.zaklad             = None
                    self.start_date         = z.enrolled_at.date() if z.enrolled_at else date.today()
                    self.end_date           = date.today()
                    self.path_type          = None
                    self.total_hours_logged = z.total_hours_logged
                    self.wpisy_dziennika    = w

            fake      = _FakePraktyka(zapis, wpisy)
            pdf_bytes = pdf_service.get_dziennik(fake)

            self.update_state(state='STARTED', meta={'progress': 80})

            # Zapis do wolumenu
            output_dir = Path('/app/pdf_output')
            output_dir.mkdir(exist_ok=True)
            filename = f"dziennik_{enrollment_id}.pdf"
            output_path = output_dir / filename
            output_path.write_bytes(pdf_bytes)

            self.update_state(state='STARTED', meta={'progress': 100})

            return {
                'path': str(output_path),
                'filename': f"dziennik_{zapis.student.last_name}_{zapis.student.first_name}.pdf",
            }

    except Exception as exc:
        self.update_state(state='FAILURE', meta={'error': str(exc)})
        raise
