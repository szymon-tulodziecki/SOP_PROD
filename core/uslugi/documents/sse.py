"""Server-Sent Events generator for Celery PDF generation status."""
from __future__ import annotations


def _pdf_status_payload(task, download_url: str) -> tuple[dict, bool]:
    if task.state == 'SUCCESS':
        res = task.result
        if isinstance(res, dict) and res.get('status') == 'error':
            return {'status': 'FAILURE', 'error': res.get('message', 'Nieznany błąd')}, True
        return {'status': 'SUCCESS', 'download_url': download_url}, True
    if task.state == 'FAILURE':
        return {'status': 'FAILURE', 'error': str(task.info)}, True
    return {'status': task.state}, False


def sse_pdf_status(task_id: str, download_url: str, celery_app, max_seconds: int = 30):
    """Yields SSE-formatted Celery task status events until completion or timeout."""
    import json
    import logging
    import time

    try:
        from gevent import sleep as _sleep
    except ImportError:
        from time import sleep as _sleep  # type: ignore[assignment]

    logger = logging.getLogger(__name__)
    deadline = time.monotonic() + max_seconds

    while time.monotonic() < deadline:
        try:
            task = celery_app.AsyncResult(task_id)
            data, finished = _pdf_status_payload(task, download_url)
            yield f"data: {json.dumps(data)}\n\n"
            if finished:
                return
        except GeneratorExit:
            return
        except Exception as exc:
            logger.error("SSE stream error for task %s: %s", task_id, exc)
            yield f"data: {json.dumps({'status': 'FAILURE', 'error': 'Internal error'})}\n\n"
            return
        _sleep(1)

    yield f"data: {json.dumps({'status': 'TIMEOUT'})}\n\n"
