import uuid
import json
import time
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, abort, send_file, current_app, Response
from flask_login import login_required, current_user
from pathlib import Path

from core.modele import ZapisPraktyki, DocumentAuditLog, RolaUzytkownika
from core.extensions import db
from core.autoryzacja import wymaga_roli

import logging
logger = logging.getLogger(__name__)

documents_bp = Blueprint('documents', __name__)

DOCUMENTS = {
    'ZAL_1':  ('zal1_porozumienie.tex.j2',  'Załącznik 1 (Porozumienie)'),
    'ZAL_2a': ('zal2a_harmonogram.tex.j2',  'Załącznik 2a (Harmonogram Uczelniany)'),
    'ZAL_3':  ('zal3_skierowanie.tex.j2',   'Załącznik 3 (Skierowanie i ocena ZOPZ)'),
    'ZAL_4':  ('zal4_efekty.tex.j2',        'Załącznik 4 (Efekty Uczenia Się)'),
    'ZAL_4a': ('zal4a_komisja.tex.j2',      'Załącznik 4a (Opinia Komisji do weryfikacji)'),
    'ZAL_4b': ('zal4b_wniosek.tex.j2',      'Załącznik 4b (Wniosek o działalność gospodarczą)'),
    'ZAL_6':  ('zal6_dziennik.tex.j2',      'Załącznik 6 (Dziennik Praktyki)'),
    'ZAL_7':  ('zal7_sprawozdanie.tex.j2',  'Załącznik 7 (Sprawozdanie Instytucji)'),
    'ZAL_7a': ('zal7a_wniosek.tex.j2',      'Załącznik 7a (Wniosek o pracę zawodową)'),
    'ZAL_8':  ('zal8_protokol.tex.j2',      'Załącznik 8 (Protokół Egzaminacyjny)'),
    'ZAL_9':  ('zal9_zobowiazanie.tex.j2',  'Załącznik 9 (Zobowiązanie poufności)'),
}

def log_audit(zapis_id, doc_type, action, details=""):
    db.session.add(DocumentAuditLog(
        id=uuid.uuid4(),
        user_id=current_user.id,
        enrollment_id=zapis_id,
        document_type=doc_type,
        action=action,
        details=details
    ))
    db.session.commit()

@documents_bp.route('/zapis/<uuid:id>')
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def panel(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    logs = db.session.query(DocumentAuditLog).filter_by(enrollment_id=id).order_by(DocumentAuditLog.created_at.desc()).limit(20).all()
    return render_template('documents/panel.html', zapis=zapis, docs=DOCUMENTS, logs=logs)

@documents_bp.route('/zapis/<uuid:id>/edytuj/<doc_type>', methods=['GET'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def edytuj(id, doc_type):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    if doc_type not in DOCUMENTS: abort(404)

    template_name, doc_title = DOCUMENTS[doc_type]

    from tex_service.compiler import render_tex
    from tex_service.pdf_service import pdf_service

    context = {}
    if doc_type == 'ZAL_6':
        context = pdf_service.build_context_dziennik(zapis)
    elif doc_type == 'ZAL_4':
        context = pdf_service.build_context_efekty(zapis)
    elif doc_type == 'ZAL_7':
        tresc = {'charakterystyka_miejsca': zapis.sprawozdanie.charakterystyka_miejsca if zapis.sprawozdanie else '',
                 'opis_prac': zapis.sprawozdanie.opis_i_analiza if zapis.sprawozdanie else '',
                 'efekty_opisy': ['' for _ in range(13)]}
        context = pdf_service.build_context_sprawozdanie(zapis, tresc)
    else:
        context = {'student': zapis.student, 'firma': zapis.dane_miejsca, 'zapis': zapis}

    try:
        raw_tex = render_tex(template_name, context)
    except Exception as e:
        raw_tex = f"% BŁĄD RENDEROWANIA SZABLONU: {str(e)}\n\n% Edytuj dokument od zera jeśli wymagane.\n"

    log_audit(zapis.id, doc_type, 'VIEWED_MANUAL', 'Otwarto edytor ręczny LaTeX')
    return render_template('documents/edytor.html', zapis=zapis, raw_tex=raw_tex, doc_type=doc_type, doc_title=doc_title)

@documents_bp.route('/zapis/<uuid:id>/generuj_auto/<doc_type>', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def generuj_auto(id, doc_type):
    from tex_service.compiler import render_tex
    from tex_service.pdf_service import pdf_service
    from celery_app import compile_raw_tex_task
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    if doc_type not in DOCUMENTS: abort(404)

    template_name, doc_title = DOCUMENTS[doc_type]

    context = {}
    if doc_type == 'ZAL_6':
        context = pdf_service.build_context_dziennik(zapis)
    elif doc_type == 'ZAL_4':
        context = pdf_service.build_context_efekty(zapis)
    elif doc_type == 'ZAL_7':
        tresc = {'charakterystyka_miejsca': zapis.sprawozdanie.charakterystyka_miejsca if zapis.sprawozdanie else '',
                 'opis_prac': zapis.sprawozdanie.opis_i_analiza if zapis.sprawozdanie else '',
                 'efekty_opisy': ['' for _ in range(13)]}
        context = pdf_service.build_context_sprawozdanie(zapis, tresc)
    else:
        context = {'student': zapis.student, 'firma': zapis.dane_miejsca, 'zapis': zapis}

    try:
        raw_tex = render_tex(template_name, context)
        task = compile_raw_tex_task.delay(raw_tex, doc_type.lower())
        log_audit(zapis.id, doc_type, 'GENERATED_AUTO', f'Wygenerowano {doc_type}')
        return jsonify({'task_id': task.id, 'status': 'PENDING'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@documents_bp.route('/zapis/<uuid:id>/kompiluj/<doc_type>', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN)
def kompiluj_recznie(id, doc_type):
    tex_source = request.form.get('tex_source')
    if not tex_source: abort(400)
    log_audit(id, doc_type, 'COMPILED_MANUAL', f'Rozpoczęto kompilację ręczną {doc_type}')
    try:
        from celery_app import compile_raw_tex_task
        task = compile_raw_tex_task.delay(tex_source, doc_type.lower())
        return jsonify({'task_id': task.id, 'status': 'PENDING'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@documents_bp.route('/status/<task_id>')
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def status_pdf(task_id):
    """Legacy polling endpoint — zachowany dla kompatybilności wstecznej."""
    try:
        from celery_app import celery
        task = celery.AsyncResult(task_id)
        if task.state == 'SUCCESS':
            res = task.result
            if isinstance(res, dict) and res.get('status') == 'error':
                return jsonify({'status': 'FAILURE', 'error': res.get('message')})
            return jsonify({'status': 'SUCCESS', 'download_url': url_for('documents.pobierz_pdf', task_id=task_id)})
        elif task.state == 'FAILURE':
            return jsonify({'status': 'FAILURE', 'error': str(task.info)})
        else:
            return jsonify({'status': task.state})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

_SSE_MAX_SECONDS = 120   # po tym czasie strumień jest zamykany niezależnie od stanu

@documents_bp.route('/stream/<task_id>')
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def stream_status(task_id):
    """Server-Sent Events — status generowania PDF.

    Strumień jest automatycznie zamykany po _SSE_MAX_SECONDS sekund,
    co chroni wątki serwera przed blokadą przez osierocone połączenia
    (np. po zamknięciu karty przez użytkownika).
    """
    from celery_app import celery

    def generate():
        deadline = time.monotonic() + _SSE_MAX_SECONDS
        try:
            while time.monotonic() < deadline:
                try:
                    task = celery.AsyncResult(task_id)
                    if task.state == 'SUCCESS':
                        res = task.result
                        if isinstance(res, dict) and res.get('status') == 'error':
                            data = {'status': 'FAILURE', 'error': res.get('message', 'Nieznany błąd')}
                        else:
                            data = {'status': 'SUCCESS',
                                    'download_url': url_for('documents.pobierz_pdf', task_id=task_id)}
                        yield f"data: {json.dumps(data)}\n\n"
                        return
                    elif task.state == 'FAILURE':
                        yield f"data: {json.dumps({'status': 'FAILURE', 'error': str(task.info)})}\n\n"
                        return
                    else:
                        yield f"data: {json.dumps({'status': task.state})}\n\n"
                except GeneratorExit:
                    return
                except Exception as exc:
                    logger.error("SSE stream error for task %s: %s", task_id, exc)
                    yield f"data: {json.dumps({'status': 'FAILURE', 'error': str(exc)})}\n\n"
                    return
                time.sleep(1)
        finally:
            # Wysyłamy zamknięcie — klient może zareagować komunikatem timeout
            yield f"data: {json.dumps({'status': 'TIMEOUT'})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@documents_bp.route('/pobierz/<task_id>')
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def pobierz_pdf(task_id):
    try:
        from celery_app import celery
        task = celery.AsyncResult(task_id)
        if task.state != 'SUCCESS':
            abort(404)
        result = task.result
        if isinstance(result, dict) and result.get('status') == 'error':
            abort(500)
        pdf_path = Path(result['path'])
        if not pdf_path.exists():
            abort(404)
        return send_file(pdf_path, mimetype='application/pdf', as_attachment=True, download_name=result['filename'])
    except Exception:
        abort(500)
