"""
app_admin/routes/dziennik.py
Monitor dzienników praktyk — podgląd wpisów, wykrywanie przerw, generowanie PDF.
"""
import io
from datetime import date, timedelta
from flask import Blueprint, render_template, request, abort, send_file
from flask_login import login_required, current_user

from core.modele import UserRole
from core.repozytoria import EnrollmentRepository, JournalRepository

journal_bp = Blueprint('journal', __name__)

_repo_enrollments = EnrollmentRepository()
_repo_entries     = JournalRepository()


def _detect_gaps(entries, threshold_days=3):
    """Wykrywa przerwy dłuższe niż threshold_days roboczych między wpisami."""
    if not entries:
        return []
    dates = sorted(e.entry_date for e in entries)
    gaps  = []
    for i in range(1, len(dates)):
        delta   = 0
        current = dates[i - 1]
        while current < dates[i]:
            current += timedelta(days=1)
            if current.weekday() < 5:
                delta += 1
        if delta > threshold_days:
            gaps.append({
                'date_from':    dates[i - 1],
                'date_to':      dates[i],
                'working_days': delta,
            })
    return gaps


@journal_bp.route('/', methods=['GET'])
@login_required
def lista_dziennikow():
    search_query         = request.args.get('szukaj', '').strip()
    page                 = request.args.get('strona', 1, type=int)
    uopz_id              = current_user.id if current_user.role == UserRole.UOPZ else None

    paginated_enrollments = _repo_enrollments.w_trakcie_strona(
        szukaj=search_query, supervisor_id=uopz_id, strona=page
    )

    stats = _repo_entries.statystyki_dla_zapisow([z.id for z in paginated_enrollments.items])

    rows  = []
    today = date.today()
    for enrollment in paginated_enrollments.items:
        path_val = enrollment.path_type.value if hasattr(enrollment.path_type, 'value') else str(enrollment.path_type)
        if path_val != 'STANDARD':
            continue
        last_entry_date, entry_count = stats.get(enrollment.id, (None, 0))
        alert = False
        if last_entry_date:
            delta   = 0
            current = last_entry_date
            while current < today:
                current += timedelta(days=1)
                if current.weekday() < 5:
                    delta += 1
            alert = delta > 3
        rows.append({
            'zapis':          enrollment,
            'liczba_wpisow':  entry_count,
            'ostatni_wpis':   last_entry_date,
            'alert':          alert,
        })

    return render_template('journal/lista.html', dane=rows, paginated_enrollments=paginated_enrollments)


@journal_bp.route('/zapis/<uuid:id>', methods=['GET'])
@login_required
def dziennik_zapisu(id):
    from datetime import date as _date
    enrollment = _repo_enrollments.znajdz_po_id(id) or abort(404)
    if current_user.role == UserRole.UOPZ and enrollment.supervisor_id != current_user.id:
        abort(403)

    def _parse_date(key):
        val = request.args.get(key, '').strip()
        try:
            return _date.fromisoformat(val) if val else None
        except ValueError:
            return None

    date_from = _parse_date('od')
    date_to   = _parse_date('do')

    entries     = _repo_entries.dla_zapisu(id, malejaco=True, data_od=date_from, data_do=date_to)
    gaps        = _detect_gaps(entries)
    total_hours = sum(e.duration_hours for e in entries)
    return render_template('journal/dziennik.html', zapis=enrollment, entries=entries,
                           gaps=gaps, total_hours=total_hours,
                           data_od=date_from, data_do=date_to)


@journal_bp.route('/zapis/<uuid:id>/pdf', methods=['GET'])
@login_required
def pdf_dziennik(id):
    enrollment = _repo_enrollments.znajdz_po_id(id) or abort(404)
    try:
        from tex_service.compiler import compile_pdf
        from core.uslugi.dokumenty import buduj_kontekst
        context   = buduj_kontekst(enrollment, 'ZAL_6')
        pdf_bytes = compile_pdf('zal6_dziennik.tex.j2', context)
        filename  = f"dziennik_{enrollment.student.last_name}_{enrollment.student.first_name}.pdf"
        return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=filename)
    except EnvironmentError:
        abort(503)
    except Exception:
        abort(500)
