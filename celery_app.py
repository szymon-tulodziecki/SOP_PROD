"""celery_app.py
Konfiguracja Celery i taski generowania PDF.

WZORZEC: ContextTask — aplikacja Flask inicjowana RAZ przy starcie workera.
Każde zadanie jest automatycznie owijane w istniejący app_context,
zamiast tworzyć go od nowa (co niszczyło pulę połączeń do bazy).
"""
import os
import logging

from celery import Celery

logger = logging.getLogger(__name__)

BROKER_URL = os.environ.get('CELERY_BROKER_URL',  'redis://localhost:6379/0')
RESULT_URL  = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

# ── 1. Inicjalizacja Celery ──────────────────────────────────────────────────
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

# ── 2. Flask app — jedno wywołanie create_app() dla całego workera ────────────
# Celery-worker budowany jest na bazie app_admin/Dockerfile,
# więc importujemy fabrykę stamtąd. Baza danych jest współdzielona
# i modele (ZapisPraktyki, WpisDziennika) są identyczne w obu aplikacjach.
from app_admin import create_app as _create_flask_app

flask_app = _create_flask_app()
logger.info("Flask app initialized once for Celery worker (ContextTask pattern)")


# ── 3. ContextTask — automatyczne opakowanie każdego taska w app_context ──────
class ContextTask(celery.Task):
    """Nadpisana klasa bazowa Celery Task.

    Każde zadanie jest wykonywane wewnątrz istniejącego app.app_context(),
    eliminując potrzebę tworzenia nowego kontekstu (i nowej puli połączeń DB)
    przy każdym wywołaniu taska.
    """
    abstract = True

    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)


celery.Task = ContextTask


# ── 4. Taski ─────────────────────────────────────────────────────────────────

@celery.task(bind=True, name='generate_pdf_dziennik', base=ContextTask)
def generate_pdf_dziennik(self, enrollment_id: str) -> dict:
    import uuid
    from pathlib import Path

    try:
        self.update_state(state='STARTED', meta={'progress': 0})

        # Importy modeli — baza jest wspólna, importujemy z app_admin
        from core.extensions import db
        from core.modele import ZapisPraktyki, WpisDziennika

        zapis = db.session.get(ZapisPraktyki, uuid.UUID(enrollment_id))
        if not zapis:
            raise ValueError(f'Zapis {enrollment_id} nie istnieje')
        wpisy = (
            db.session.query(WpisDziennika)
            .filter_by(enrollment_id=zapis.id)
            .order_by(WpisDziennika.entry_date)
            .all()
        )

        self.update_state(state='STARTED', meta={'progress': 30})

        import httpx

        context = {
            'student': {
                'first_name': zapis.student.first_name,
                'last_name': zapis.student.last_name,
                'album_number': zapis.student.album_number,
            },
            'zapis': {
                'total_hours_logged': zapis.total_hours_logged,
                'praktyka': {
                    'rok_uczelniany': zapis.praktyka.rok_uczelniany,
                    'semestr': zapis.praktyka.semestr,
                },
            },
            'wpisy': [
                {
                    'entry_date': w.entry_date.isoformat(),
                    'duration_hours': w.duration_hours,
                    'description': w.description,
                    'efekt': {'kod': f"{w.learning_outcome_id:02d}"},
                }
                for w in sorted(wpisy, key=lambda x: x.entry_date)
            ]
        }

        tex_service_url = flask_app.config.get('TEX_SERVICE_URL', 'http://tex-service:5002')
        resp = httpx.post(
            f"{tex_service_url}/generuj",
            json={'template': 'zal6_dziennik.tex.j2', 'context': context},
            timeout=60.0
        )
        if resp.status_code != 200:
            raise Exception(f"Tex service error: {resp.text}")
        pdf_bytes = resp.content

        self.update_state(state='STARTED', meta={'progress': 80})

        output_dir = Path('/app/pdf_output')
        output_dir.mkdir(exist_ok=True)
        filename = f"dziennik_{enrollment_id}.pdf"
        output_path = output_dir / filename
        output_path.write_bytes(pdf_bytes)

        self.update_state(state='STARTED', meta={'progress': 100})
        return {
            'status': 'success',
            'path': str(output_path),
            'filename': f"dziennik_{zapis.student.last_name}_{zapis.student.first_name}.pdf",
        }

    except Exception as exc:
        logger.error("Task generate_pdf_dziennik failed: %s", str(exc), exc_info=True)
        return {'status': 'error', 'message': str(exc)}


@celery.task(bind=True, name='compile_raw_tex_task', base=ContextTask)
def compile_raw_tex_task(self, tex_source: str, filename_prefix: str) -> dict:
    import uuid
    from pathlib import Path

    try:
        self.update_state(state='STARTED', meta={'progress': 10})
        from tex_service.compiler import compile_raw_tex

        pdf_bytes = compile_raw_tex(tex_source)
        self.update_state(state='STARTED', meta={'progress': 80})

        output_dir = Path('/app/pdf_output')
        output_dir.mkdir(exist_ok=True)
        filename = f"{filename_prefix}_{uuid.uuid4().hex[:8]}.pdf"
        output_path = output_dir / filename
        output_path.write_bytes(pdf_bytes)

        self.update_state(state='STARTED', meta={'progress': 100})
        return {
            'status': 'success',
            'path': str(output_path),
            'filename': filename,
        }
    except Exception as exc:
        logger.error("Task compile_raw_tex_task failed: %s", str(exc), exc_info=True)
        return {'status': 'error', 'message': str(exc)}


@celery.task(bind=True, name='generate_zip_task', base=ContextTask,
             max_retries=3, default_retry_delay=5)
def generate_zip_task(self, enrollment_id: str) -> dict:
    import uuid
    import zipfile
    from pathlib import Path

    try:
        from core.extensions import db
        from core.modele import ZapisPraktyki
        from tex_service.compiler import render_tex, compile_raw_tex
        from tex_service.pdf_service import pdf_service
        from app_admin.routes.dokumenty import DOCUMENTS

        self.update_state(state='STARTED', meta={'progress': 5})

        zapis = db.session.get(ZapisPraktyki, uuid.UUID(enrollment_id))
        if not zapis:
            raise ValueError('Zapis nie istnieje')

        output_dir = Path('/app/pdf_output')
        output_dir.mkdir(exist_ok=True)

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            total_docs = len(DOCUMENTS)
            doc_errors = []   # śledzenie błędów poszczególnych dokumentów
            docs_ok = 0
            for idx, (doc_type, (template_name, title)) in enumerate(DOCUMENTS.items()):
                if doc_type == 'ZAL_6':
                    context = pdf_service._build_context_dziennik(zapis)
                elif doc_type == 'ZAL_4':
                    context = pdf_service._build_context_efekty(zapis)
                elif doc_type == 'ZAL_7':
                    tresc = {
                        'charakterystyka_miejsca': zapis.sprawozdanie.charakterystyka_miejsca if zapis.sprawozdanie else '',
                        'opis_prac': zapis.sprawozdanie.opis_i_analiza if zapis.sprawozdanie else '',
                        'efekty_opisy': ['' for _ in range(13)]
                    }
                    context = pdf_service._build_context_sprawozdanie(zapis, tresc)
                else:
                    context = {'student': zapis.student, 'firma': zapis.zaklad, 'zapis': zapis}

                try:
                    raw_tex = render_tex(template_name, context)
                    pdf_bytes = compile_raw_tex(raw_tex)
                    pdf_file_path = tmp_path / f"{doc_type}.pdf"
                    pdf_file_path.write_bytes(pdf_bytes)
                    docs_ok += 1
                except Exception as e:
                    error_msg = f"{doc_type}: {str(e)}"
                    logger.warning("ZIP task: błąd generowania %s: %s", doc_type, e)
                    doc_errors.append(error_msg)
                    err_file = tmp_path / f"{doc_type}_ERROR.txt"
                    err_file.write_text(f"Blad kompilacji {doc_type}: {str(e)}")

                self.update_state(state='STARTED', meta={
                    'progress': 10 + int(80 * (idx + 1) / total_docs),
                    'docs_ok': docs_ok,
                    'docs_failed': len(doc_errors),
                })

            zip_filename = f"komplet_{zapis.student.last_name}_{zapis.student.first_name}_{uuid.uuid4().hex[:6]}.zip"
            zip_path = output_dir / zip_filename

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for f in tmp_path.iterdir():
                    zipf.write(f, arcname=f.name)

        self.update_state(state='STARTED', meta={'progress': 100})

        # Raportowanie częściowego sukcesu zamiast cichego "SUCCESS"
        if doc_errors:
            return {
                'status': 'partial_success',
                'path': str(zip_path),
                'filename': zip_filename,
                'docs_ok': docs_ok,
                'docs_failed': len(doc_errors),
                'errors': doc_errors,
                'message': f'Wygenerowano {docs_ok}/{total_docs} dokumentów. '
                           f'Błędy: {"; ".join(doc_errors[:3])}'
                           f'{"..." if len(doc_errors) > 3 else ""}',
            }

        return {
            'status': 'success',
            'path': str(zip_path),
            'filename': zip_filename,
        }

    except (ConnectionError, OSError) as exc:
        # Błędy przejściowe (sieć, I/O) — ponów zadanie
        logger.warning("ZIP task transient error, retry %d/%d: %s",
                       self.request.retries, self.max_retries, exc)
        raise self.retry(exc=exc, countdown=5 * (self.request.retries + 1))
    except Exception as exc:
        logger.error("Task generate_zip_task failed: %s", str(exc), exc_info=True)
        return {'status': 'error', 'message': str(exc)}
