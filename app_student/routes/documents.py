"""
app_student/blueprints/documents.py

Generowanie PDF przez mikroserwis tex-service.
Zero Celery, zero Redis, zero pollingu.
"""

import io
import logging
import os
from datetime import date, datetime

import httpx
from flask import Blueprint, abort, send_file, jsonify
from flask_login import login_required, current_user

from app_student.extensions import db
from app_student.models import ZapisPraktyki, StatusZapisu

logger = logging.getLogger(__name__)
documents_bp = Blueprint('documents', __name__)

TEX_SERVICE_URL = os.environ.get('TEX_SERVICE_URL', 'http://tex-service:5002')

DOC_CONFIG = {
    'ZAL_4': ('zal4_efekty.tex.j2',       'zal4_efekty.pdf'),
    'ZAL_6': ('zal6_dziennik.tex.j2',     'zal6_dziennik.pdf'),
    'ZAL_7': ('zal7_sprawozdanie.tex.j2', 'zal7_sprawozdanie.pdf'),
}


# ─────────────────────────────────────────────────────────────
# Serializacja kontekstu do czystego JSON
# (ORM-obiekty i daty nie są serializowalne przez json.dumps)
# ─────────────────────────────────────────────────────────────

def _d(value) -> str:
    """date/datetime → 'YYYY-MM-DD', None → ''"""
    if value is None:
        return ''
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _serialize_context(doc_type: str, zapis: ZapisPraktyki) -> dict:
    praktyka = zapis.praktyka
    student  = zapis.student

    if doc_type == 'ZAL_6':
        return {
            'student': {
                'first_name':   student.first_name  or '',
                'last_name':    student.last_name   or '',
                'album_number': student.album_number or '',
            },
            'zapis': {
                'total_hours_logged': zapis.total_hours_logged or 0,
                'praktyka': {
                    'rok_uczelniany': praktyka.rok_uczelniany or '',
                    'semestr':        praktyka.semestr        or '',
                },
            },
            'firma': {
                'name':    praktyka.firma_nazwa  or '',
                'address': praktyka.firma_adres  or '',
                'city':    praktyka.firma_miasto or '',
            },
            'sciezka':          _sciezka_label(praktyka.track_type),
            'rok_akademicki':   _rok_akademicki(praktyka.termin_od),
            'data_rozpoczecia': _d(praktyka.termin_od),
            'data_zakonczenia': _d(praktyka.termin_do),
            'lacznie_godzin':   zapis.total_hours_logged or 0,
            'wpisy': [
                {
                    'entry_date':     _d(w.entry_date),
                    'duration_hours': w.duration_hours or 0,
                    'description':    w.description   or '',
                    'efekt': {
                        'kod': w.efekt.kod if w.efekt else '',
                    },
                }
                for w in sorted(zapis.wpisy_dziennika, key=lambda w: w.entry_date)
            ],
        }

    if doc_type == 'ZAL_7':
        return {
            'student': {
                'imie':          student.first_name   or '',
                'nazwisko':      student.last_name    or '',
                'numer_albumu':  student.album_number or '',
            },
            'firma': {
                'nazwa':  praktyka.firma_nazwa  or '',
                'adres':  praktyka.firma_adres  or '',
                'miasto': praktyka.firma_miasto or '',
            },
            'specjalnosc':            getattr(praktyka, 'specjalnosc', '') or '',
            'rok_akademicki':         _rok_akademicki(praktyka.termin_od),
            'charakterystyka_miejsca': (
                zapis.sprawozdanie.charakterystyka_miejsca
                if zapis.sprawozdanie else ''
            ),
            'opis_prac': (
                zapis.sprawozdanie.opis_i_analiza
                if zapis.sprawozdanie else ''
            ),
            'efekty_opisy': [''] * 13,
        }

    if doc_type == 'ZAL_4':
        return {
            'student': {
                'imie':         student.first_name   or '',
                'nazwisko':     student.last_name    or '',
                'numer_albumu': student.album_number or '',
            },
            'specjalnosc':    getattr(praktyka, 'specjalnosc', '') or '',
            'lacznie_godzin': zapis.total_hours_logged or 0,
            'oceny': [
                {
                    'learning_outcome_id': o.learning_outcome_id,
                    'grade':               o.grade or '',
                }
                for o in sorted(zapis.oceny, key=lambda o: o.learning_outcome_id)
            ],
            'uwagi_uopz': zapis.grade_descriptive or '',
        }

    raise ValueError(f'Nieznany doc_type: {doc_type}')


def _rok_akademicki(termin_od) -> str:
    if not isinstance(termin_od, (date, datetime)):
        return '—'
    y = termin_od.year
    return f"{y-1}/{y}" if termin_od.month <= 7 else f"{y}/{y+1}"


def _sciezka_label(path_type) -> str:
    mapping = {
        'STANDARD':      'standardowa',
        'EMPLOYMENT':    'zatrudnienie',
        'OWN_BUSINESS':  'własna działalność',
        'ERASMUS_PLUS':  'Erasmus+',
    }
    val = path_type.value if hasattr(path_type, 'value') else str(path_type)
    return mapping.get(val, val)


# ─────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────

@documents_bp.route('/generuj/<doc_type>', methods=['POST'])
@login_required
def generuj(doc_type: str):
    if doc_type not in DOC_CONFIG:
        logger.warning("Nieobsługiwany typ dokumentu: %s", doc_type)
        abort(403)

    # Szukamy aktywnej praktyki studenta
    zapis = db.session.query(ZapisPraktyki).filter_by(
        student_id=current_user.id,
        status=StatusZapisu.IN_PROGRESS,
    ).first()

    # Jeśli nie ma aktywnej, bierzemy ostatnią (podgląd archiwalnych)
    if not zapis:
        zapis = db.session.query(ZapisPraktyki).filter_by(
            student_id=current_user.id,
        ).order_by(ZapisPraktyki.id.desc()).first()

    if not zapis:
        return jsonify({'error': 'Nie znaleziono zapisu na praktykę.'}), 404

    template_name, filename = DOC_CONFIG[doc_type]

    try:
        context = _serialize_context(doc_type, zapis)
    except Exception as e:
        logger.error("Błąd serializacji kontekstu dla %s: %s", doc_type, e)
        return jsonify({'error': str(e)}), 500

    try:
        resp = httpx.post(
            f"{TEX_SERVICE_URL}/generuj",
            json={'template': template_name, 'context': context, 'filename': filename},
            timeout=30.0,
        )
    except httpx.ConnectError:
        logger.error("Nie można połączyć się z tex-service (%s)", TEX_SERVICE_URL)
        return jsonify({'error': 'Serwis PDF jest niedostępny.'}), 503
    except httpx.TimeoutException:
        return jsonify({'error': 'Przekroczono czas oczekiwania na PDF.'}), 504

    if resp.status_code != 200:
        err = {}
        if 'application/json' in resp.headers.get('content-type', ''):
            err = resp.json()
        logger.error("tex-service błąd %d dla %s: %s", resp.status_code, doc_type, err)
        return jsonify({'error': err.get('error', 'Błąd generowania PDF.')}), 500

    return send_file(
        io.BytesIO(resp.content),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename,
    )