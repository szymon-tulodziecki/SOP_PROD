"""
app_admin/routes/dziennik.py
Monitor dzienników praktyk — podgląd wpisów, wykrywanie przerw, generowanie PDF.
Przemianowano z journal.py.
"""
import io
from datetime import date, timedelta
from flask import Blueprint, render_template, request, abort, send_file
from flask_login import login_required, current_user
from sqlalchemy import func

from core.modele import (ZapisPraktyki, WpisDziennika, Uzytkownik,
                              RolaUzytkownika, StatusZapisu)
from core.extensions import db

journal_bp = Blueprint('journal', __name__)


def _wykryj_przerwy(wpisy, prog_dni=3):
    """Wykrywa przerwy dłuższe niż prog_dni roboczych między wpisami."""
    if not wpisy:
        return []
    daty = sorted(w.entry_date for w in wpisy)
    przerwy = []
    for i in range(1, len(daty)):
        delta = 0
        d = daty[i - 1]
        while d < daty[i]:
            d += timedelta(days=1)
            if d.weekday() < 5:
                delta += 1
        if delta > prog_dni:
            przerwy.append({'od': daty[i - 1], 'do': daty[i], 'dni_roboczych': delta})
    return przerwy


@journal_bp.route('/')
@login_required
def lista_dziennikow():
    szukaj = request.args.get('szukaj', '').strip()
    strona = request.args.get('strona', 1, type=int)

    q = db.session.query(ZapisPraktyki).filter(ZapisPraktyki.status == StatusZapisu.IN_PROGRESS)

    if current_user.role == RolaUzytkownika.UOPZ:
        q = q.filter_by(uopz_id=current_user.id)

    if szukaj:
        wzorzec = f'%{szukaj}%'
        q = q.join(Uzytkownik, ZapisPraktyki.student_id == Uzytkownik.id).filter(
            db.or_(Uzytkownik.first_name.ilike(wzorzec), Uzytkownik.last_name.ilike(wzorzec))
        )

    zapisy = q.order_by(ZapisPraktyki.enrolled_at.desc()).paginate(page=strona, per_page=20, error_out=False)

    dane = []
    for z in zapisy.items:
        ostatni = db.session.query(func.max(WpisDziennika.data_wpisu)).filter_by(zapis_id=z.id).scalar()
        liczba_wpisow = db.session.query(func.count(WpisDziennika.id)).filter_by(zapis_id=z.id).scalar()

        alert = False
        if ostatni:
            delta = 0
            d = ostatni
            dzisiaj = date.today()
            while d < dzisiaj:
                d += timedelta(days=1)
                if d.weekday() < 5:
                    delta += 1
            alert = delta > 3

        dane.append({'zapis': z, 'liczba_wpisow': liczba_wpisow, 'ostatni_wpis': ostatni, 'alert': alert})

    return render_template('journal/lista.html', dane=dane, zapisy=zapisy)


@journal_bp.route('/zapis/<uuid:id>')
@login_required
def dziennik_zapisu(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    wpisy = db.session.query(WpisDziennika)\
              .filter_by(zapis_id=id)\
              .order_by(WpisDziennika.data_wpisu.desc())\
              .all()
    przerwy     = _wykryj_przerwy(wpisy)
    suma_godzin = sum(w.duration_hours for w in wpisy)
    return render_template('journal/dziennik.html', zapis=zapis, wpisy=wpisy,
                           przerwy=przerwy, suma_godzin=suma_godzin)


@journal_bp.route('/zapis/<uuid:id>/pdf')
@login_required
def pdf_dziennik(id):
    zapis = db.session.get(ZapisPraktyki, id) or abort(404)
    wpisy = db.session.query(WpisDziennika)\
              .filter_by(zapis_id=id)\
              .order_by(WpisDziennika.data_wpisu)\
              .all()
    try:
        from tex_service.pdf_service import pdf_service

        class _FakePraktyka:
            def __init__(self, z, w):
                self.id                 = z.id
                self.student            = z.student
                self.zaklad             = None
                self.start_date         = z.enrolled_at.date() if z.enrolled_at else date.today()
                self.end_date           = date.today()
                self.path_type          = None
                self.total_hours_logged = z.total_hours_logged
                self.wpisy_dziennika    = w

        fake      = _FakePraktyka(zapis, wpisy)
        pdf_bytes = pdf_service.get_dziennik(fake)
        nazwa     = f"dziennik_{zapis.student.last_name}_{zapis.student.first_name}.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=nazwa)
    except EnvironmentError:
        abort(503)
    except Exception:
        abort(500)
