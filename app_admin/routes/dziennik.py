"""
app_admin/routes/dziennik.py
Monitor dzienników praktyk — podgląd wpisów, wykrywanie przerw, generowanie PDF.
"""
import io
from datetime import date, timedelta
from flask import Blueprint, render_template, request, abort, send_file
from flask_login import login_required, current_user

from core.modele import UserRole
from core.repozytoria import RepozytoriumZapisow, RepozytoriumWpisow

journal_bp = Blueprint('journal', __name__)

_repo_zapisow = RepozytoriumZapisow()
_repo_wpisow  = RepozytoriumWpisow()


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
    szukaj     = request.args.get('szukaj', '').strip()
    strona     = request.args.get('strona', 1, type=int)
    uopz_id    = current_user.id if current_user.role == UserRole.UOPZ else None

    zapisy = _repo_zapisow.w_trakcie_strona(
        szukaj=szukaj, supervisor_id=uopz_id, strona=strona
    )

    stats  = _repo_wpisow.statystyki_dla_zapisow([z.id for z in zapisy.items])

    dane      = []
    dzisiaj   = date.today()
    for z in zapisy.items:
        ostatni, liczba_wpisow = stats.get(z.id, (None, 0))
        alert = False
        if ostatni:
            delta = 0
            d = ostatni
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
    zapis       = _repo_zapisow.znajdz_po_id(id) or abort(404)
    wpisy       = _repo_wpisow.dla_zapisu(id, malejaco=True)
    przerwy     = _wykryj_przerwy(wpisy)
    suma_godzin = sum(w.duration_hours for w in wpisy)
    return render_template('journal/dziennik.html', zapis=zapis, wpisy=wpisy,
                           przerwy=przerwy, suma_godzin=suma_godzin)


@journal_bp.route('/zapis/<uuid:id>/pdf')
@login_required
def pdf_dziennik(id):
    zapis = _repo_zapisow.znajdz_po_id(id) or abort(404)
    try:
        from tex_service.compiler import compile_pdf
        from core.uslugi.dokumenty import buduj_kontekst
        ctx       = buduj_kontekst(zapis, 'ZAL_6')
        pdf_bytes = compile_pdf('zal6_dziennik.tex.j2', ctx)
        nazwa     = f"dziennik_{zapis.student.last_name}_{zapis.student.first_name}.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=nazwa)
    except EnvironmentError:
        abort(503)
    except Exception:
        abort(500)
