"""
app_student/routes/documents.py
"""

import io
import logging
import os
from datetime import date, datetime

import httpx
from flask import Blueprint, abort, send_file, jsonify, request, current_app
from flask_login import login_required, current_user

from app_student.extensions import db
from app_student.models import ZapisPraktyki, StatusZapisu

logger = logging.getLogger(__name__)
documents_bp = Blueprint('documents', __name__)

DOC_CONFIG = {
    'ZAL_4': ('zal4_efekty.tex.j2',       'zal4_efekty.pdf'),
    'ZAL_6': ('zal6_dziennik.tex.j2',     'zal6_dziennik.pdf'),
    'ZAL_7': ('zal7_sprawozdanie.tex.j2', 'zal7_sprawozdanie.pdf'),
}

def get_tex_service_url():
    """Pobiera URL tex service z konfiguracji aplikacji."""
    return current_app.config.get('TEX_SERVICE_URL', 'http://tex-service:5002')


# ─────────────────────────────────────────────────────────────
# BEZPIECZNE GETTERY (Pancerz zapobiegający AttributeError)
# ─────────────────────────────────────────────────────────────

def g(obj, attr, default=''):
    """Zwraca wartość atrybutu lub default, jeśli atrybut nie istnieje w modelu."""
    try:
        val = getattr(obj, attr, default)
        return val if val is not None else default
    except AttributeError:
        return default

def _d(value) -> str:
    if value is None: return ''
    if isinstance(value, (date, datetime)): return value.isoformat()
    return str(value)

def _rok_akademicki(termin_od) -> str:
    if not isinstance(termin_od, (date, datetime)): return '—'
    y = termin_od.year
    return f"{y-1}/{y}" if termin_od.month <= 7 else f"{y}/{y+1}"

def _sciezka_label(path_type) -> str:
    mapping = {
        'STANDARD': 'standardowa',
        'EMPLOYMENT': 'zatrudnienie',
        'OWN_BUSINESS': 'własna działalność',
        'ERASMUS_PLUS': 'Erasmus+',
    }
    val = getattr(path_type, 'value', str(path_type))
    return mapping.get(val, val)

# ─────────────────────────────────────────────────────────────
# SERIALIZACJA (Dopasowana do Twojego app_admin/models.py)
# ─────────────────────────────────────────────────────────────

def _serialize_context(doc_type: str, zapis: ZapisPraktyki) -> dict:
    p = getattr(zapis, 'praktyka', None)
    s = getattr(zapis, 'student', None)

    context = {
        'student': {
            'first_name':   g(s, 'first_name'),
            'last_name':    g(s, 'last_name'),
            'album_number': g(s, 'album_number'),
            'imie':         g(s, 'first_name'),
            'nazwisko':     g(s, 'last_name'),
            'numer_albumu': g(s, 'album_number'),
        },
        'firma': {
            # UWAGA: Te pola są w ZAPISIE, a nie w Praktyce!
            'name':    g(zapis, 'firma_nazwa', 'Brak danych w bazie'),
            'nazwa':   g(zapis, 'firma_nazwa', 'Brak danych w bazie'),
            'address': g(zapis, 'firma_adres', '—'),
            'adres':   g(zapis, 'firma_adres', '—'),
            'city':    g(zapis, 'firma_miasto', '—'),
            'miasto':  g(zapis, 'firma_miasto', '—'),
        },
        # Termin od/do i specjalność też masz w Zapisie!
        'rok_akademicki': _rok_akademicki(getattr(zapis, 'termin_od', None)),
        'specjalnosc':    g(zapis, 'specjalnosc', 'Informatyka'),
        'lacznie_godzin': g(zapis, 'total_hours_logged', 0),
    }

    if doc_type == 'ZAL_6':
        context.update({
            'zapis': {
                'total_hours_logged': g(zapis, 'total_hours_logged', 0),
                'praktyka': {
                    'rok_uczelniany': g(p, 'rok_uczelniany'),
                    'semestr':        g(p, 'semestr'),
                },
            },
            'sciezka':          _sciezka_label(getattr(zapis, 'track_type', 'STANDARD')),
            'data_rozpoczecia': _d(getattr(zapis, 'termin_od', None)),
            'data_zakonczenia': _d(getattr(zapis, 'termin_do', None)),
            'wpisy': [
                {
                    'entry_date':     _d(w.entry_date),
                    'duration_hours': g(w, 'duration_hours', 0),
                    'description':    g(w, 'description'),
                    # Używamy w.efekt_uczenia.id
                    'efekt': {'kod': f"{w.efekt_uczenia.id:02d}" if getattr(w, 'efekt_uczenia', None) else '--'},
                }
                for w in sorted(getattr(zapis, 'wpisy_dziennika', []), key=lambda x: getattr(x, 'entry_date', date.min))
            ]
        })
    
    elif doc_type == 'ZAL_7':
        spr = getattr(zapis, 'sprawozdanie', None)
        context.update({
            'charakterystyka_miejsca': g(spr, 'charakterystyka_miejsca'),
            'opis_prac':              g(spr, 'opis_i_analiza'),
            'efekty_opisy':           [''] * 13,
        })
        
    elif doc_type == 'ZAL_4':
        context.update({
            'lacznie_godzin': g(zapis, 'total_hours_logged', 0),
            'oceny': [
                {
                    'learning_outcome_id': g(o, 'learning_outcome_id'),
                    'grade':               o.result.value if getattr(o, 'result', None) else 'uzyskał/a',
                }
                for o in sorted(getattr(zapis, 'oceny_efektow', []), key=lambda x: g(x, 'learning_outcome_id', 0))
            ],
            'uwagi_uopz': g(zapis, 'ocena_opisowa_uopz'),
        })

    return context


# ─────────────────────────────────────────────────────────────
# ROUTE
# ─────────────────────────────────────────────────────────────

@documents_bp.route('/generuj/<doc_type>', methods=['POST'])
@login_required
def generuj(doc_type: str):
    if doc_type not in DOC_CONFIG:
        abort(403)

    force = request.args.get('force') == 'true'

    # Pobranie zapisu
    zapis = db.session.query(ZapisPraktyki).filter_by(
        student_id=current_user.id, status=StatusZapisu.IN_PROGRESS
    ).first() or db.session.query(ZapisPraktyki).filter_by(
        student_id=current_user.id
    ).order_by(ZapisPraktyki.id.desc()).first()

    if not zapis:
        return jsonify({'error': 'Nie znaleziono zapisu na praktykę.'}), 404

    # --- WALIDACJA ---
    warnings = []
    # Sprawdzamy zapis (bo tam jest firma_nazwa), a nie p!
    if not g(zapis, 'firma_nazwa'): warnings.append("Nazwa firmy")
    if not g(zapis, 'firma_adres'): warnings.append("Adres firmy")
    
    if doc_type == 'ZAL_6' and not getattr(zapis, 'wpisy_dziennika', None):
        warnings.append("Brak wpisów w dzienniku")

    if warnings and not force:
        return jsonify({
            'requires_confirmation': True,
            'warnings': warnings,
            'message': 'Niektóre dane są puste. Dokument będzie niekompletny.'
        }), 200

    # --- GENEROWANIE ---
    template_name, filename = DOC_CONFIG[doc_type]
    try:
        context = _serialize_context(doc_type, zapis)
        resp = httpx.post(
            f"{get_tex_service_url()}/generuj",
            json={'template': template_name, 'context': context, 'filename': filename},
            timeout=30.0,
        )
        
        if resp.status_code != 200:
            err = resp.json() if 'json' in resp.headers.get('content-type', '') else {}
            return jsonify({'error': err.get('error', 'Blad serwisu PDF')}), 500

        return send_file(io.BytesIO(resp.content), mimetype='application/pdf', 
                         as_attachment=True, download_name=filename)

    except Exception as e:
        logger.error(f"Blad krytyczny: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500