"""
app_admin/routes/ocenianie.py
Oceny efektów uczenia się — operuje na ZapisPraktyki (enrollment).
Przemianowano z evaluation.py.
"""
import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from core.modele import (ZapisPraktyki, OcenaPraktyki, EfektUczenia,
                    RolaUzytkownika, StatusZapisu, WynikOceny)
from core.extensions import db
from core.autoryzacja import wymaga_roli

evaluation_bp = Blueprint('evaluation', __name__)


def _parse_grade(val: str):
    """Konwertuje ocenę z formularza na float, obsługując przecinki i kropki."""
    if not val or not val.strip():
        return None
    try:
        return float(val.strip().replace(',', '.'))
    except (ValueError, AttributeError):
        return None


from core.uslugi import SerwisOceniania


def get_pilne_oceny(uopz_id=None):
    return SerwisOceniania.get_pilne_oceny(uopz_id)


@evaluation_bp.route('/')
@login_required
def lista_ocen():
    SerwisOceniania.auto_complete_internships()

    q = db.session.query(ZapisPraktyki).filter(
        ZapisPraktyki.status.in_([StatusZapisu.IN_PROGRESS, StatusZapisu.COMPLETED])
    )

    if current_user.role == RolaUzytkownika.UOPZ:
        q = q.filter_by(uopz_id=current_user.id)

    zapisy = q.join(ZapisPraktyki.student).order_by(
        ZapisPraktyki.status.desc(),
        ZapisPraktyki.enrolled_at.desc()
    ).all()

    from datetime import date, timedelta

    zapisy_z_deadlinami = []
    for zapis in zapisy:
        deadline = None
        dni_do_deadline = None
        przekroczony = False

        if zapis.termin_do and zapis.status == StatusZapisu.COMPLETED:
            deadline = zapis.termin_do + timedelta(days=7)
            dni_do_deadline = (deadline - date.today()).days
            przekroczony = dni_do_deadline < 0

        zapisy_z_deadlinami.append({
            'zapis': zapis,
            'deadline': deadline,
            'dni_do_deadline': dni_do_deadline,
            'przekroczony': przekroczony,
            'w_trakcie': zapis.status == StatusZapisu.IN_PROGRESS,
            'zakonczona': zapis.status == StatusZapisu.COMPLETED,
        })

    w_trakcie = [z for z in zapisy_z_deadlinami if z['w_trakcie']]
    zakonczone = [z for z in zapisy_z_deadlinami if z['zakonczona']]

    return render_template('evaluation/lista_ocen.html',
                           zapisy_z_deadlinami=zapisy_z_deadlinami,
                           w_trakcie=w_trakcie,
                           zakonczone=zakonczone)

@evaluation_bp.route('/zapis/<uuid:id>/karta_ocen', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def ocen_praktyke(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    if request.method == 'POST':
        zapis.ocena_opisowa_uopz = request.form.get('ocena_opisowa_uopz')
        zapis.ocena_opisowa_zopz = request.form.get('ocena_opisowa_zopz')
        zapis.ocena_sprawozdania = _parse_grade(request.form.get('ocena_sprawozdania', ''))
        zapis.ocena_uopz         = _parse_grade(request.form.get('ocena_uopz', ''))
        zapis.ocena_zopz         = _parse_grade(request.form.get('ocena_zopz', ''))
        zapis.sprawdzian_pytanie_1 = request.form.get('sprawdzian_pytanie_1')
        zapis.sprawdzian_ocena_1   = _parse_grade(request.form.get('sprawdzian_ocena_1', ''))
        zapis.sprawdzian_pytanie_2 = request.form.get('sprawdzian_pytanie_2')
        zapis.sprawdzian_ocena_2   = _parse_grade(request.form.get('sprawdzian_ocena_2', ''))
        zapis.sprawdzian_pytanie_3 = request.form.get('sprawdzian_pytanie_3')
        zapis.sprawdzian_ocena_3   = _parse_grade(request.form.get('sprawdzian_ocena_3', ''))
        if request.form.get('zakoncz'):
            zapis.status = StatusZapisu.COMPLETED
        db.session.commit()
        flash('Oceny zostały zapisane.', 'success')
        return redirect(url_for('evaluation.ocen_praktyke', id=zapis.id))

    from flask_wtf import FlaskForm
    csrf_form = FlaskForm()
    return render_template('evaluation/karta_ocen.html', practically=zapis, zapis=zapis, csrf_form=csrf_form)

@evaluation_bp.route('/zapis/<uuid:id>/sprawozdanie')
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def podglad_sprawozdania(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    return render_template('evaluation/podglad_sprawozdania.html', zapis=zapis)

@evaluation_bp.route('/zapis/<uuid:id>', methods=['GET', 'POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def ocen_zapis(id):
    zapis  = db.session.get(ZapisPraktyki, id) or abort(404)
    efekty = db.session.query(EfektUczenia).order_by(EfektUczenia.id).all()

    istniejace = {
        str(o.learning_outcome_id): o
        for o in db.session.query(OcenaPraktyki).filter_by(enrollment_id=id).all()
    }

    if request.method == 'POST':
        for efekt in efekty:
            wynik_str = request.form.get(f'wynik_{efekt.id}')
            uwagi     = request.form.get(f'uwagi_{efekt.id}', '').strip()
            if not wynik_str:
                continue
            try:
                wynik = WynikOceny[wynik_str]
            except KeyError:
                continue
            ocena = istniejace.get(str(efekt.id))
            if ocena:
                ocena.result          = wynik
                ocena.evaluator_notes = uwagi or None
            else:
                db.session.add(OcenaPraktyki(
                    id                  = uuid.uuid4(),
                    enrollment_id       = zapis.id,
                    learning_outcome_id = efekt.id,
                    result              = wynik,
                    evaluator_notes     = uwagi or None,
                ))
        db.session.commit()
        flash('Oceny zostały zapisane.', 'success')
        return redirect(url_for('evaluation.ocen_zapis', id=id))

    return render_template('evaluation/formularz_ocen.html',
                           zapis=zapis, efekty=efekty, istniejace=istniejace)

@evaluation_bp.route('/zapis/<uuid:id>/zakoncz', methods=['POST'])
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def zakoncz_zapis(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    zapis.status = StatusZapisu.COMPLETED
    db.session.commit()
    flash(f'Praktyka studenta {zapis.student.first_name} {zapis.student.last_name} została zakończona.', 'success')
    return redirect(url_for('evaluation.lista_ocen'))

@evaluation_bp.route('/zapis/<uuid:id>/protokol')
@wymaga_roli(RolaUzytkownika.ADMIN, RolaUzytkownika.UOPZ)
def generuj_protokol(id):
    """Generuje Protokół egzaminu (zał.8) przez tex-service."""
    import httpx, unicodedata
    from flask import make_response, current_app
    from datetime import date

    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    if not zapis.ocena_uopz:
        flash('Protokół dostępny dopiero po wystawieniu oceny UOPZ.', 'warning')
        return redirect(url_for('evaluation.ocen_praktyke', id=id))

    s = zapis.student
    tex_url = current_app.config.get('TEX_SERVICE_URL', 'http://tex-service:5002')
    firma_nazwa = (zapis.firma.nazwa if zapis.firma else zapis.firma_nazwa) or ''

    def _f(v):
        return float(v) if v is not None else None

    ctx = {
        'zapis': {
            'firma_nazwa':          firma_nazwa,
            'termin_od':            zapis.termin_od.strftime('%d.%m.%Y') if zapis.termin_od else '',
            'termin_do':            zapis.termin_do.strftime('%d.%m.%Y') if zapis.termin_do else '',
            'ocena_sprawozdania':   _f(zapis.ocena_sprawozdania),
            'ocena_uopz':           _f(zapis.ocena_uopz),
            'ocena_zopz':           _f(zapis.ocena_zopz),
            'sprawdzian_pytanie_1': zapis.sprawdzian_pytanie_1,
            'sprawdzian_ocena_1':   _f(zapis.sprawdzian_ocena_1),
            'sprawdzian_pytanie_2': zapis.sprawdzian_pytanie_2,
            'sprawdzian_ocena_2':   _f(zapis.sprawdzian_ocena_2),
            'sprawdzian_pytanie_3': zapis.sprawdzian_pytanie_3,
            'sprawdzian_ocena_3':   _f(zapis.sprawdzian_ocena_3),
            'uopz': {'first_name': zapis.uopz.first_name, 'last_name': zapis.uopz.last_name} if zapis.uopz else None,
        },
        'student': {
            'imie': s.first_name, 'nazwisko': s.last_name,
            'first_name': s.first_name, 'last_name': s.last_name,
            'nr_albumu': s.album_number or '', 'album_number': s.album_number or '',
            'kierunek': getattr(s, 'kierunek', 'Informatyka') or 'Informatyka',
        },
        'specjalnosc': getattr(s, 'specjalnosc', '') or getattr(zapis, 'specjalnosc', '') or '',
        'praktyka': {
            'rok_uczelniany': zapis.praktyka.rok_uczelniany if zapis.praktyka else '',
            'semestr':        zapis.praktyka.semestr        if zapis.praktyka else '',
            'wymiar_godzin':  zapis.praktyka.wymiar_godzin  if zapis.praktyka else 960,
        },
        'data_egzaminu': date.today().strftime('%d.%m.%Y'),
    }
    try:
        r = httpx.post(f'{tex_url}/generuj',
                       json={'template': 'zal8_protokol.tex.j2', 'context': ctx, 'filename': 'zal8_protokol.pdf'},
                       timeout=60)
        if r.status_code == 200:
            safe = unicodedata.normalize('NFKD', s.last_name).encode('ascii', 'ignore').decode('ascii') or 'student'
            resp = make_response(r.content)
            resp.headers['Content-Type'] = 'application/pdf'
            resp.headers['Content-Disposition'] = f'attachment; filename="zal8_protokol_{safe}.pdf"'
            return resp
        flash(f'Błąd generowania protokołu: {r.text[:200]}', 'danger')
    except Exception as e:
        flash(f'Błąd połączenia z tex-service: {str(e)}', 'danger')
    return redirect(url_for('evaluation.ocen_praktyke', id=id))
