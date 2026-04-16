"""celery_app.py
Konfiguracja Celery i taski generowania PDF.

WZORZEC: minimalna aplikacja Flask dla workera z QueuePool + dispose po fork().

Zamiast NullPool (które otwiera nowe TCP przy każdym zapytaniu) stosujemy:
1. Standardowy QueuePool w procesie macierzystym.
2. Sygnał worker_process_init: db.engine.dispose(close=False) — porzuca
   odziedziczone deskryptory bez wysyłania QUIT do bazy, więc każdy
   podproces workera buduje własną, czystą pulę od pierwszego zapytania.
3. Sygnał worker_process_shutdown: db.session.remove() + db.engine.dispose()
   — czyste zamknięcie po zatrzymaniu procesu.

Parametry puli (pool_size=2, max_overflow=3, pool_timeout=10) dobrane pod
typowe obciążenie Celery: 2 równoległe zapytania na worker + krótki overflow
dla spiętrzonych tasków.
"""
import os
import logging

from celery import Celery, signals
from flask import Flask

logger = logging.getLogger(__name__)

BROKER_URL      = os.environ['CELERY_BROKER_URL']
RESULT_URL      = os.environ['CELERY_RESULT_BACKEND']
PDF_OUTPUT_DIR  = os.environ.get('PDF_OUTPUT_DIR', '/app/pdf_output')
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
    Tworzy odchudzoną aplikację Flask bez blueprintów ani rozszerzeń webowych.
    Używa QueuePool (domyślna pula SQLAlchemy) z parametrami dopasowanymi do
    środowiska Celery. Właściwa izolacja połączeń po fork() realizowana jest
    przez sygnał worker_process_init.
    """
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # QueuePool: pula utrzymywana per-proces, odbudowywana po fork() via dispose.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size':     2,      # stałe połączenia na worker
        'max_overflow':  3,      # dodatkowe przy spiętrzeniu tasków
        'pool_timeout':  10,     # sekund oczekiwania na wolne połączenie
        'pool_pre_ping': True,   # wykrywa martwe połączenia przed użyciem
    }
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
    app.config['TEX_SERVICE_URL'] = TEX_SERVICE_URL

    from core.extensions import db
    db.init_app(app)

    return app


_worker_app: Flask | None = None


@signals.worker_process_init.connect
def _init_worker(**_kwargs):
    """
    Wywoływany w każdym nowo sforkowanym podprocesie workera.

    db.engine.dispose(close=False) porzuca odziedziczone po procesie
    macierzystym deskryptory socketów TCP bez wysyłania komendy zamykającej
    do PostgreSQL. Pierwsze zapytanie w tym podprocesie otworzy świeże,
    wyłącznie mu przynależące połączenia — bez ryzyka kolizji protokołu.
    """
    global _worker_app
    _worker_app = _create_worker_app()
    ctx = _worker_app.app_context()
    ctx.push()

    from core.extensions import db
    db.engine.dispose(close=False)

    logger.info("Worker process initialized (QueuePool, dispose after fork)")


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
        from core.extensions import db
        db.engine.dispose(close=False)
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
    from core.modele import InternshipEnrollment
    from core.uslugi.dokumenty import buduj_kontekst

    zapis = db.session.get(InternshipEnrollment, uuid.UUID(enrollment_id))
    if not zapis:
        raise ZapisNieIstnieje(f'Zapis {enrollment_id} nie istnieje')

    context = buduj_kontekst(zapis, 'ZAL_6')

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
    """Usuwa pliki PDF starsze niż max_age_hours z katalogu PDF_OUTPUT_DIR.

    Przeszukuje rekursywnie całe drzewo katalogów (łącznie z podkatalogami
    wg schematu rok/miesiąc/dzień generowanymi przez generuj_pdf_z_szablonu).
    Puste podkatalogi są usuwane po wyczyszczeniu plików.
    """
    import time
    from pathlib import Path

    output_dir = Path(PDF_OUTPUT_DIR)
    if not output_dir.exists():
        return {'deleted': 0, 'errors': 0}

    cutoff = time.time() - max_age_hours * 3600
    deleted = errors = 0

    for f in output_dir.rglob('*.pdf'):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        except Exception as exc:
            logger.warning("Nie udało się usunąć %s: %s", f, exc)
            errors += 1

    # Usuń puste podkatalogi (od najgłębszych w górę)
    for d in sorted(output_dir.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir() and d != output_dir:
            try:
                d.rmdir()  # rmdir usuwa tylko puste katalogi — bezpieczne
            except OSError:
                pass  # katalog nie jest pusty — ignoruj

    logger.info("Czyszczenie PDF: usunięto %d, błędy %d (próg: %dh)", deleted, errors, max_age_hours)
    return {'deleted': deleted, 'errors': errors}


@celery.task(bind=True, name='generuj_pdf_z_szablonu',
             max_retries=3, default_retry_delay=10)
def generuj_pdf_z_szablonu(self, template_name: str, context: dict,
                            filename_prefix: str) -> dict:
    """Kompiluje PDF z nazwanego szablonu Jinja2 i słownika danych.

    Jedyna dozwolona ścieżka asynchronicznej kompilacji — nie przyjmuje
    surowego kodu TeX, eliminując wektor Command Injection.

    Args:
        template_name:   nazwa pliku szablonu z katalogu templates/
                         (np. 'zal6_dziennik.tex.j2')
        context:         słownik danych domenowych (JSON-serializowalny)
        filename_prefix: prefiks nazwy pliku wynikowego
    """
    import uuid
    from datetime import date
    from pathlib import Path

    try:
        from tex_service.compiler import compile_pdf
        pdf_bytes = compile_pdf(template_name, context)
    except Exception as exc:
        logger.warning("LaTeX compile error (retry %d/%d): %s",
                       self.request.retries, self.max_retries, exc)
        raise self.retry(exc=exc, countdown=10 * (self.request.retries + 1))

    today = date.today()
    output_dir = Path(PDF_OUTPUT_DIR) / str(today.year) / f"{today.month:02d}" / f"{today.day:02d}"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename    = f"{filename_prefix}_{uuid.uuid4().hex[:8]}.pdf"
    output_path = output_dir / filename
    output_path.write_bytes(pdf_bytes)

    return {
        'status':   'success',
        'path':     str(output_path),
        'filename': filename,
    }
