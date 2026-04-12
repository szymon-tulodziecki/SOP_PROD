"""celery_app.py
Konfiguracja Celery i taski generowania PDF.

WZORZEC: minimalna aplikacja Flask dla workera.

Różnica względem naiwnego podejścia (ContextTask + pełny create_app):
- Worker NIE ładuje blueprintów, szablonów ani rozszerzeń bezpieczeństwa.
- SQLAlchemy używa NullPool: po każdym zadaniu gniazdo TCP jest zamykane,
  co eliminuje problem "server has gone away" w środowisku wieloprocesowym.
- Kontekst aplikacji jest tworzony JEDNORAZOWO przy starcie workera i
  pozostaje aktywny przez cały czas życia procesu (nie per-task).
"""
import os
import logging

from celery import Celery, signals
from flask import Flask
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

BROKER_URL    = os.environ['CELERY_BROKER_URL']
RESULT_URL    = os.environ['CELERY_RESULT_BACKEND']
PDF_OUTPUT_DIR = os.environ.get('PDF_OUTPUT_DIR', '/app/pdf_output')
TEX_SERVICE_URL = os.environ.get('TEX_SERVICE_URL', 'http://tex-service:5002')

# ── 1. Celery — konfiguracja ──────────────────────────────────────────────────
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
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    beat_schedule={
        'cleanup-old-pdfs': {
            'task': 'cleanup_old_pdfs',
            'schedule': 3600.0,   # co godzinę
        },
    },
)


# ── 2. Minimalna aplikacja Flask dla workera ──────────────────────────────────
def _create_worker_app() -> Flask:
    """
    Tworzy odchudzoną aplikację Flask bez żadnych blueprintów ani rozszerzeń
    webowych. Jedynym celem jest dostarczenie kontekstu aplikacji i puli
    połączeń SQLAlchemy z NullPool (bezpiecznej w środowisku wieloprocesowym).
    """
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL',
        'postgresql+psycopg2://ans_admin:secure_password_123@localhost:5432/ans_praktyki',
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # NullPool: każde zapytanie otwiera i natychmiast zamyka gniazdo TCP.
    # Eliminuje błędy "server has gone away" po fork() i zakleszczenia puli.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'poolclass': NullPool}
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'worker-only')
    app.config['TEX_SERVICE_URL'] = TEX_SERVICE_URL

    from core.extensions import db
    db.init_app(app)

    return app


_worker_app: Flask | None = None


@signals.worker_process_init.connect
def _init_worker(**_kwargs):
    """Inicjuje aplikację Flask i pushuje kontekst przy starcie procesu workera."""
    global _worker_app
    _worker_app = _create_worker_app()
    ctx = _worker_app.app_context()
    ctx.push()
    logger.info("Worker process initialized (NullPool, no web blueprints)")


@signals.worker_process_shutdown.connect
def _shutdown_worker(**_kwargs):
    """Sprząta połączenia przy zamykaniu procesu workera."""
    from core.extensions import db
    try:
        db.session.remove()
        db.engine.dispose()
    except Exception:
        pass
    logger.info("Worker process shut down cleanly")


def _get_app() -> Flask:
    """Zwraca aplikację workera; fallback dla wywołań spoza kontekstu Celery (np. testy)."""
    global _worker_app
    if _worker_app is None:
        _worker_app = _create_worker_app()
        _worker_app.app_context().push()
    return _worker_app


# ── Wyjątki domenowe (nie ponawiamy) ─────────────────────────────────────────
class ZapisNieIstnieje(Exception):
    """Brak rekordu w bazie — błąd stały, retry bez sensu."""


# ── 3. Taski ──────────────────────────────────────────────────────────────────

@celery.task(bind=True, name='generate_pdf_dziennik',
             max_retries=3, default_retry_delay=10)
def generate_pdf_dziennik(self, enrollment_id: str) -> dict:
    import uuid
    from pathlib import Path
    import httpx

    from core.extensions import db
    from core.modele import ZapisPraktyki
    from core.modele.dziennik import WpisDziennika

    zapis = db.session.get(ZapisPraktyki, uuid.UUID(enrollment_id))
    if not zapis:
        raise ZapisNieIstnieje(f'Zapis {enrollment_id} nie istnieje')

    wpisy = (
        db.session.query(WpisDziennika)
        .filter_by(enrollment_id=zapis.id)
        .order_by(WpisDziennika.entry_date)
        .all()
    )

    context = {
        'student': {
            'first_name':   zapis.student.first_name,
            'last_name':    zapis.student.last_name,
            'album_number': zapis.student.album_number,
        },
        'zapis': {
            'total_hours_logged': zapis.total_hours_logged,
            'praktyka': {
                'rok_uczelniany': zapis.internship.academic_year if zapis.internship else '',
                'semestr':        zapis.internship.semester      if zapis.internship else '',
            },
        },
        'wpisy': [
            {
                'data':     w.entry_date.isoformat() if w.entry_date else '',
                'godziny':  w.duration_hours,
                'opis':     w.description,
                'efekt_nr': ', '.join(f"{e.id:02d}" for e in w.learning_outcomes) if w.learning_outcomes else '--',
            }
            for w in wpisy
        ],
    }

    tex_url = _get_app().config.get('TEX_SERVICE_URL', TEX_SERVICE_URL)
    try:
        resp = httpx.post(
            f"{tex_url}/generuj",
            json={'template': 'zal6_dziennik.tex.j2', 'context': context},
            timeout=60.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Tex-service error (retry %d/%d): %s",
                       self.request.retries, self.max_retries, exc)
        raise self.retry(exc=exc, countdown=10 * (self.request.retries + 1))

    output_dir = Path(PDF_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename    = f"dziennik_{enrollment_id}.pdf"
    output_path = output_dir / filename
    output_path.write_bytes(resp.content)

    return {
        'status':   'success',
        'path':     str(output_path),
        'filename': f"dziennik_{zapis.student.last_name}_{zapis.student.first_name}.pdf",
    }


@celery.task(name='cleanup_old_pdfs')
def cleanup_old_pdfs(max_age_hours: int = 24) -> dict:
    """Usuwa pliki PDF starsze niż max_age_hours z katalogu PDF_OUTPUT_DIR."""
    import time
    from pathlib import Path

    output_dir = Path(PDF_OUTPUT_DIR)
    if not output_dir.exists():
        return {'deleted': 0, 'errors': 0}

    cutoff = time.time() - max_age_hours * 3600
    deleted = errors = 0
    for f in output_dir.glob('*.pdf'):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        except Exception as exc:
            logger.warning("Nie udało się usunąć %s: %s", f, exc)
            errors += 1

    logger.info("Czyszczenie PDF: usunięto %d, błędy %d (próg: %dh)", deleted, errors, max_age_hours)
    return {'deleted': deleted, 'errors': errors}


@celery.task(bind=True, name='compile_raw_tex_task',
             max_retries=3, default_retry_delay=10)
def compile_raw_tex_task(self, tex_source: str, filename_prefix: str) -> dict:
    import uuid
    from pathlib import Path

    try:
        from tex_service.compiler import compile_raw_tex
        pdf_bytes = compile_raw_tex(tex_source)
    except Exception as exc:
        logger.warning("LaTeX compile error (retry %d/%d): %s",
                       self.request.retries, self.max_retries, exc)
        raise self.retry(exc=exc, countdown=10 * (self.request.retries + 1))

    output_dir = Path(PDF_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename    = f"{filename_prefix}_{uuid.uuid4().hex[:8]}.pdf"
    output_path = output_dir / filename
    output_path.write_bytes(pdf_bytes)

    return {
        'status':   'success',
        'path':     str(output_path),
        'filename': filename,
    }
