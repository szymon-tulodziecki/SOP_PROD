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
def generate_pdf_dziennik(self, enrollment_id: str, app_type: str = 'student') -> dict:
    import uuid
    from pathlib import Path

    try:
        self.update_state(state='STARTED', meta={'progress': 0})

        if app_type == 'admin':
            from app_admin.extensions import db
            from app_admin.models import ZapisPraktyki, WpisDziennika
            from app_admin import create_app
        else:
            from app_student.extensions import db
            from app_student.models import ZapisPraktyki, WpisDziennika
            from app_student import create_app

        app = create_app()

        with app.app_context():
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

            from tex_engine.pdf_service import pdf_service
            pdf_bytes = pdf_service.get_dziennik(zapis)

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
        return {'status': 'error', 'message': str(exc)}


@celery.task(bind=True, name='compile_raw_tex_task')
def compile_raw_tex_task(self, tex_source: str, filename_prefix: str) -> dict:
    import uuid
    from pathlib import Path

    try:
        self.update_state(state='STARTED', meta={'progress': 10})
        from tex_engine.compiler import compile_raw_tex
        
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


@celery.task(bind=True, name='generate_zip_task')
def generate_zip_task(self, enrollment_id: str) -> dict:
    import uuid
    import zipfile
    from pathlib import Path
    
    try:
        from app_admin.extensions import db
        from app_admin.models import ZapisPraktyki
        from app_admin import create_app
        from tex_engine.compiler import render_tex, compile_raw_tex
        from tex_engine.pdf_service import pdf_service
        from app_admin.routes.documents import DOCUMENTS
        
        self.update_state(state='STARTED', meta={'progress': 5})
        
        app = create_app()
        with app.app_context():
            zapis = db.session.get(ZapisPraktyki, uuid.UUID(enrollment_id))
            if not zapis: raise ValueError('Zapis nie istnieje')
            
            output_dir = Path('/app/pdf_output')
            output_dir.mkdir(exist_ok=True)
            
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                
                total_docs = len(DOCUMENTS)
                for idx, (doc_type, (template_name, title)) in enumerate(DOCUMENTS.items()):
                    if doc_type == 'ZAL_6':
                        context = pdf_service._build_context_dziennik(zapis)
                    elif doc_type == 'ZAL_4':
                        context = pdf_service._build_context_efekty(zapis)
                    elif doc_type == 'ZAL_7':
                        tresc = {'charakterystyka_miejsca': zapis.sprawozdanie.charakterystyka_miejsca if zapis.sprawozdanie else '',
                                 'opis_prac': zapis.sprawozdanie.opis_i_analiza if zapis.sprawozdanie else '',
                                 'efekty_opisy': ['' for _ in range(13)]}
                        context = pdf_service._build_context_sprawozdanie(zapis, tresc)
                    else:
                        context = {'student': zapis.student, 'firma': zapis.zaklad, 'zapis': zapis}
                    
                    try:
                        raw_tex = render_tex(template_name, context)
                        pdf_bytes = compile_raw_tex(raw_tex)
                        pdf_file_path = tmp_path / f"{doc_type}.pdf"
                        pdf_file_path.write_bytes(pdf_bytes)
                    except Exception as e:
                        err_file = tmp_path / f"{doc_type}_ERROR.txt"
                        err_file.write_text(f"Blad kompilacji {doc_type}: {str(e)}")
                    
                    self.update_state(state='STARTED', meta={'progress': 10 + int(80 * (idx + 1) / total_docs)})
                
                zip_filename = f"komplet_{zapis.student.last_name}_{zapis.student.first_name}_{uuid.uuid4().hex[:6]}.zip"
                zip_path = output_dir / zip_filename
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for f in tmp_path.iterdir():
                        zipf.write(f, arcname=f.name)
                        
            self.update_state(state='STARTED', meta={'progress': 100})
            return {
                'status': 'success',
                'path': str(zip_path),
                'filename': zip_filename,
            }
            
    except Exception as exc:
        return {'status': 'error', 'message': str(exc)}
