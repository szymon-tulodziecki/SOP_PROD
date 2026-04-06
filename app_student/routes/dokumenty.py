"""
app_student/routes/dokumenty.py
"""

import io
import logging
import os
from datetime import date, datetime

import httpx
from flask import Blueprint, abort, send_file, jsonify, request, current_app, flash, redirect, url_for, make_response, render_template
from flask_login import login_required, current_user
from core.extensions import db
from core.models import ZapisPraktyki, StatusZapisu, HarmonogramPraktyki

logger = logging.getLogger(__name__)
documents_bp = Blueprint('documents', __name__)

def _dok(nazwa, opis=None, **kw):
    """Pomocnik budujący wpis dokumentu."""
    d = {'nazwa': nazwa, 'opis': opis, 'dostepny': True}
    d.update(kw)
    return d

def _dok_dyn(nazwa, zapis_id, typ, opis=None, dostepny=True, powod=None):
    return {'nazwa': nazwa, 'opis': opis, 'zapis_id': str(zapis_id),
            'typ': typ, 'dynamiczny': True, 'dostepny': dostepny, 'powod': powod}

def _dok_staly(nazwa, klucz, opis=None):
    return {'nazwa': nazwa, 'opis': opis, 'klucz_staly': klucz, 'staly': True, 'dostepny': True}


@documents_bp.route('/moje')
@login_required
def moje_dokumenty():
    zapisy = db.session.query(ZapisPraktyki)\
        .filter_by(student_id=current_user.id)\
        .filter(ZapisPraktyki.status.in_([
            StatusZapisu.IN_PROGRESS,
            StatusZapisu.COMPLETED,
            StatusZapisu.COMMISSION_REVIEW,
            StatusZapisu.DEAN_APPROVAL,
            StatusZapisu.AWAITING_APPROVAL,
        ]))\
        .order_by(ZapisPraktyki.enrolled_at.desc())\
        .all()

    dokumenty_list = []
    for zapis in zapisy:
        sciezka = zapis.track_type.value if zapis.track_type else 'STANDARD'
        w_trakcie = zapis.status in [StatusZapisu.IN_PROGRESS, StatusZapisu.COMMISSION_REVIEW, StatusZapisu.DEAN_APPROVAL]
        zakonczona = zapis.status == StatusZapisu.COMPLETED
        # Ocena wystawiona przez UOPZ (po egzaminie komisji)
        oceniona = zakonczona and zapis.ocena_uopz is not None
        # Dziekan zatwierdził (dla ścieżki B/C)
        dziekan_zatwierdził = zapis.dean_decision == 'APPROVED'
        harmonogram_count = db.session.query(HarmonogramPraktyki)\
            .filter_by(enrollment_id=zapis.id).count()
        firma_bez_umowy = not zapis.firma or not zapis.firma.has_standing_agreement
        firma_custom = not zapis.firma_id  # własna firma, nie z bazy

        docs = []

        if sciezka == 'STANDARD':
            # Faza 1-2: Przed praktyką / start
            if firma_custom:
                docs.append(_dok_dyn('Zał. 9 – Oświadczenie instytucji',
                    zapis.id, 'ZAL_9', 'Do wypełnienia przez zakład pracy'))
            if firma_bez_umowy:
                docs.append(_dok_dyn('Zał. 1 – Porozumienie uczelnia ↔ zakład',
                    zapis.id, 'ZAL_1', 'Dla firm bez stałej umowy z ANS'))
            docs.append(_dok_dyn('Zał. 2 – Program praktyki',
                zapis.id, 'ZAL_2', 'Z danymi studenta i firmy'))
            docs.append(_dok_dyn('Zał. 2a – Indywidualny Program Praktyk',
                zapis.id, 'ZAL_2A',
                'Harmonogram efektów — student + UOPZ + ZOPZ',
                dostepny=harmonogram_count > 0,
                powod=None if harmonogram_count > 0 else 'Wymaga wypełnionego harmonogramu (krok 2)'))
            docs.append(_dok_dyn('Zał. 3 – Karta praktyki / Skierowanie',
                zapis.id, 'ZAL_3', 'Z danymi studenta, firmy i ZOPZ'))

            # Faza 5: W trakcie
            docs.append(_dok_dyn('Zał. 6 – Dziennik praktyki',
                zapis.id, 'ZAL_6', 'Generowany z wpisów dziennika',
                dostepny=w_trakcie or zakonczona,
                powod=None if (w_trakcie or zakonczona) else 'Dostępny po zatwierdzeniu praktyki'))

            # ── Faza 5: Dziennik (w trakcie) ──────────────────────────────
            # Faza 6: Pakiet końcowy (separator)
            docs.append({'separator': True, 'nazwa': 'Pakiet końcowy – złożenie do 7 dni po zakończeniu'})
            docs.append(_dok_dyn('Zał. 7 – Sprawozdanie końcowe',
                zapis.id, 'ZAL_7', 'Podpisuje student',
                dostepny=zakonczona,
                powod=None if zakonczona else 'Dostępny po zakończeniu praktyki'))
            docs.append(_dok_dyn('Zał. 4 – Potwierdzenie efektów uczenia się',
                zapis.id, 'ZAL_4', 'Podpisuje ZOPZ + UOPZ',
                dostepny=zakonczona,
                powod=None if zakonczona else 'Dostępny po zakończeniu praktyki'))
            # Faza 7: Po ocenie komisji (zał.8 i zał.5)
            docs.append({'separator': True, 'nazwa': 'Po egzaminie komisji'})
            docs.append(_dok_dyn('Zał. 8 – Protokół egzaminu komisji',
                zapis.id, 'ZAL_8', 'Generowany po wystawieniu oceny',
                dostepny=oceniona,
                powod=None if oceniona else 'Dostępny po wystawieniu oceny przez UOPZ'))
            docs.append(_dok_staly('Zał. 5 – Ankieta oceny praktyki',
                'ankieta', 'Formularz anonimowej ankiety'))

        elif sciezka in ['EMPLOYMENT', 'OWN_BUSINESS']:
            # Faza 1: Wniosek (dostępny od razu)
            docs.append(_dok_dyn('Zał. 4b – Wniosek o zaliczenie',
                zapis.id, 'ZAL_4B', 'Praca etatowa / własna działalność'))

            # Faza 3: Sprawozdanie (po decyzji komisji)
            docs.append(_dok_dyn('Zał. 7a – Sprawozdanie z pracy/działalności',
                zapis.id, 'ZAL_7A', 'Zatwierdza przełożony/UOPZ',
                dostepny=w_trakcie or zakonczona,
                powod=None if (w_trakcie or zakonczona) else 'Dostępny po decyzji komisji'))

            # Faza 4-5: Po decyzji dziekana
            docs.append(_dok_dyn('Zał. 4a – Potwierdzenie efektów (komisja)',
                zapis.id, 'ZAL_4A', '13 efektów: uzyskał / częściowo / nie',
                dostepny=dziekan_zatwierdził or zakonczona,
                powod=None if (dziekan_zatwierdził or zakonczona) else 'Dostępny po decyzji dziekana'))
            docs.append({'separator': True, 'nazwa': 'Po egzaminie komisji'})
            docs.append(_dok_staly('Zał. 5 – Ankieta', 'ankieta'))
            docs.append(_dok_dyn('Zał. 8 – Protokół egzaminu komisji',
                zapis.id, 'ZAL_8', 'Wpis do USOS',
                dostepny=dziekan_zatwierdził or zakonczona,
                powod=None if (dziekan_zatwierdził or zakonczona) else 'Dostępny po decyzji dziekana'))

        dokumenty_list.append({'zapis': zapis, 'sciezka': sciezka, 'docs': docs})

    return render_template('dokumenty/moje_dokumenty.html', dokumenty_list=dokumenty_list)


STALE_SZABLONY = {
    'ankieta': ('zal5_ankieta.tex.j2', 'zal5_ankieta.pdf'),
}

@documents_bp.route('/staly/<doc_key>')
@login_required
def pobierz_staly(doc_key):
    if doc_key not in STALE_SZABLONY:
        abort(404)
    template_name, filename = STALE_SZABLONY[doc_key]
    try:
        response = httpx.post(
            f"{get_tex_service_url()}/generuj",
            json={'template': template_name, 'context': {}, 'filename': filename},
            timeout=30
        )
        if response.status_code == 200:

            pdf_response = make_response(response.content)
            pdf_response.headers['Content-Type'] = 'application/pdf'
            pdf_response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return pdf_response
        else:
            flash('Błąd generowania dokumentu.', 'error')
    except Exception as e:
        flash(f'Błąd połączenia z serwisem PDF: {str(e)}', 'error')
    return redirect(url_for('documents.moje_dokumenty'))


@documents_bp.route('/dynamiczny/<uuid:zapis_id>/<typ>')
@login_required
def pobierz_dynamiczny(zapis_id, typ):
    """Generuje dynamiczny dokument dla danego zapisu."""
    if typ not in DOC_CONFIG:
        abort(404)

    zapis = db.session.get(ZapisPraktyki, zapis_id)
    if not zapis or zapis.student_id != current_user.id:
        abort(404)

    template_name, filename = DOC_CONFIG[typ]

    # Buduj kontekst na podstawie zapisu
    ctx = _build_context(zapis, typ)

    try:
        response = httpx.post(
            f"{get_tex_service_url()}/generuj",
            json={'template': template_name, 'context': ctx, 'filename': filename},
            timeout=60
        )
        if response.status_code == 200:
            import unicodedata
            safe = unicodedata.normalize('NFKD', zapis.student.last_name).encode('ascii', 'ignore').decode('ascii') or 'student'
            pdf_name = template_name.replace('.tex.j2', '')
            pdf_response = make_response(response.content)
            pdf_response.headers['Content-Type'] = 'application/pdf'
            pdf_response.headers['Content-Disposition'] = f'attachment; filename="{pdf_name}_{safe}.pdf"'
            return pdf_response
        else:
            flash(f'Błąd generowania dokumentu: {response.text[:200]}', 'error')
    except Exception as e:
        flash(f'Błąd połączenia z serwisem PDF: {str(e)}', 'error')
    return redirect(url_for('documents.moje_dokumenty'))


def _build_context(zapis, typ):
    """Buduje kontekst dla szablonu LaTeX na podstawie zapisu."""
    student = zapis.student
    uopz = zapis.uopz
    firma_nazwa = (zapis.firma.nazwa if zapis.firma else None) or g(zapis, 'firma_nazwa')
    firma_adres = (zapis.firma.adres if zapis.firma else None) or g(zapis, 'firma_adres')
    firma_miasto = (zapis.firma.miasto if zapis.firma else None) or g(zapis, 'firma_miasto')
    firma_nip = (zapis.firma.nip_krs if zapis.firma else None) or g(zapis, 'firma_nip_krs')

    ctx = {
        'student': {
            'first_name': g(student, 'first_name'),
            'last_name': g(student, 'last_name'),
            'album_number': g(student, 'album_number'),
            # aliasy zgodne z zalacznik_*.tex.j2
            'imie': g(student, 'first_name'),
            'nazwisko': g(student, 'last_name'),
            'nr_albumu': g(student, 'album_number'),
            'plec': g(student, 'plec', ''),
            'kierunek': g(student, 'kierunek', 'Informatyka'),
            'specjalnosc': g(student, 'specjalnosc', ''),
            'tryb_studiow': g(student, 'tryb_studiow', ''),
        },
        'praktyka': {
            'rok_uczelniany': g(zapis.praktyka, 'rok_uczelniany') if zapis.praktyka else '',
            'semestr': g(zapis.praktyka, 'semestr') if zapis.praktyka else '',
            'wymiar_godzin': g(zapis.praktyka, 'wymiar_godzin', 120) if zapis.praktyka else 120,
        },
        'firma': {
            'nazwa': firma_nazwa,
            'adres': firma_adres,
            'miasto': firma_miasto,
            'nip_krs': firma_nip,
        },
        'firma_upowazniony': g(zapis, 'firma_upowazniony_osoba', ''),
        'firma_upowazniony_stanowisko': g(zapis, 'firma_upowazniony_stanowisko', ''),
        'terminy': {
            'od': zapis.termin_od.strftime('%d.%m.%Y') if zapis.termin_od else '',
            'do': zapis.termin_do.strftime('%d.%m.%Y') if zapis.termin_do else '',
        },
        'zopz': {
            'imie_nazwisko': g(zapis, 'zopz_imie_nazwisko', ''),
            'stanowisko': g(zapis, 'zopz_stanowisko', ''),
            'telefon': g(zapis, 'zopz_telefon', ''),
            'email': g(zapis, 'zopz_email', ''),
        },
        'uopz': {
            'imie_nazwisko': f"{uopz.first_name} {uopz.last_name}" if uopz else '',
        },
        'specjalnosc': g(zapis, 'specjalnosc', ''),
        'uzasadnienie': g(zapis, 'uzasadnienie_sciezki', ''),
        'data_wniosku': '',
        # Aliasy dla szablonów używających zapis.* (stare)
        'zapis': {
            'specjalnosc': g(zapis, 'specjalnosc', ''),
            'firma_nazwa': firma_nazwa,
            'firma_adres': firma_adres,
            'firma_miasto': firma_miasto,
        },
    }
    # Dane harmonogramu dla ZAL_6
    if typ in ('ZAL_2A',):
        from core.models import HarmonogramPraktyki, EfektUczenia
        harmonogramy = db.session.query(HarmonogramPraktyki)\
            .filter_by(enrollment_id=zapis.id)\
            .order_by(HarmonogramPraktyki.learning_outcome_id)\
            .all()
        ctx['harmonogram'] = [{
            'efekt_kod': h.efekt.kod if h.efekt else str(h.learning_outcome_id),
            'efekt_opis': h.efekt.opis if h.efekt else '',
            'dzial': g(h, 'nazwa_dzialu', ''),
            'prace': g(h, 'przykladowe_prace', ''),
            'dni': g(h, 'liczba_dni', 0),
        } for h in harmonogramy]
    if typ in ('ZAL_6',):
        from core.models import WpisDziennika
        wpisy = db.session.query(WpisDziennika)\
            .filter_by(enrollment_id=zapis.id)\
            .order_by(WpisDziennika.entry_date)\
            .all()
        ctx['wpisy'] = [{
            'data':    _d(w.entry_date),
            'opis':    g(w, 'description'),
            'godziny': g(w, 'duration_hours', 0),
            'efekt_nr': ', '.join(f"{e.id:02d}" for e in w.efekty_uczenia) if w.efekty_uczenia else '--',
        } for w in wpisy]
    return ctx


DOC_CONFIG = {
    'ZAL_1':  ('zal1_porozumienie.tex.j2',     'zal1_porozumienie.pdf'),
    'ZAL_2':  ('zal2_program.tex.j2',          'zal2_program.pdf'),
    'ZAL_2A': ('zal2a_program.tex.j2',         'zal2a_program.pdf'),
    'ZAL_3':  ('zal3_karta.tex.j2',            'zal3_karta.pdf'),
    'ZAL_4':  ('zal4_efekty.tex.j2',           'zal4_efekty.pdf'),
    'ZAL_4A': ('zal4a_komisja.tex.j2',         'zal4a_komisja.pdf'),
    'ZAL_4B': ('zal4b_wniosek.tex.j2',         'zal4b_wniosek.pdf'),
    'ZAL_6':  ('zal6_dziennik.tex.j2',         'zal6_dziennik.pdf'),
    'ZAL_7':  ('zal7_sprawozdanie.tex.j2',     'zal7_sprawozdanie.pdf'),
    'ZAL_7A': ('zal7a_sprawozdanie.tex.j2',    'zal7a_sprawozdanie.pdf'),
    'ZAL_8':  ('zal8_protokol.tex.j2',         'zal8_protokol.pdf'),
    'ZAL_9':  ('zal9_oswiadczenie.tex.j2',     'zal9_oswiadczenie.pdf'),
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

    firma_nazwa  = (zapis.firma.nazwa  if zapis.firma else None) or g(zapis, 'firma_nazwa', '')
    firma_adres  = (zapis.firma.adres  if zapis.firma else None) or g(zapis, 'firma_adres', '')
    firma_miasto = (zapis.firma.miasto if zapis.firma else None) or g(zapis, 'firma_miasto', '')
    uopz = zapis.uopz

    context = {
        'student': {
            'first_name':   g(s, 'first_name'),
            'last_name':    g(s, 'last_name'),
            'album_number': g(s, 'album_number'),
            'imie':         g(s, 'first_name'),
            'nazwisko':     g(s, 'last_name'),
            'nr_albumu':    g(s, 'album_number'),
            'numer_albumu': g(s, 'album_number'),
            'plec':         g(s, 'plec', ''),
            'kierunek':     g(s, 'kierunek', 'Informatyka'),
            'tryb_studiow': g(s, 'tryb_studiow', ''),
        },
        'firma': {
            'nazwa':   firma_nazwa,
            'adres':   firma_adres,
            'miasto':  firma_miasto,
            'name':    firma_nazwa,
            'address': firma_adres,
            'city':    firma_miasto,
        },
        'terminy': {
            'od': zapis.termin_od.strftime('%d.%m.%Y') if zapis.termin_od else '',
            'do': zapis.termin_do.strftime('%d.%m.%Y') if zapis.termin_do else '',
        },
        'zopz': {
            'imie_nazwisko': g(zapis, 'zopz_imie_nazwisko', ''),
            'stanowisko':    g(zapis, 'zopz_stanowisko', ''),
            'telefon':       g(zapis, 'zopz_telefon', ''),
            'email':         g(zapis, 'zopz_email', ''),
        },
        'uopz': {
            'imie_nazwisko': f"{uopz.first_name} {uopz.last_name}" if uopz else '',
        },
        'praktyka': {
            'rok_uczelniany': g(p, 'rok_uczelniany') if p else '',
            'semestr':        g(p, 'semestr') if p else '',
            'wymiar_godzin':  g(p, 'wymiar_godzin', 120) if p else 120,
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
                    'efekt': {'kod': ', '.join(f"{e.id:02d}" for e in w.efekty_uczenia) if w.efekty_uczenia else '--'},
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