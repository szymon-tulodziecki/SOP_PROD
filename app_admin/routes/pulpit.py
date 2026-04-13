from flask import Blueprint, render_template
from flask_login import login_required, current_user
from core.modele import UserRole, EnrollmentStatus
from core.repozytoria import RepozytoriumZapisow, RepozytoriumPraktyk, RepozytoriumUzytkownikow
from flask_wtf import FlaskForm

dashboard_bp = Blueprint('dashboard', __name__)

_repo_zapisow    = RepozytoriumZapisow()
_repo_praktyk    = RepozytoriumPraktyk()
_repo_uzytk      = RepozytoriumUzytkownikow()


@dashboard_bp.route('/')
@login_required
def index():
    uopz_id = current_user.id if current_user.role == UserRole.UOPZ else None

    stats_zapisow = _repo_zapisow.statystyki_pulpit(supervisor_id=uopz_id)
    statystyki = {
        **stats_zapisow,
        'zakonczone':       _repo_praktyk.liczba_nieaktywnych(),
        'liczba_studentow': _repo_uzytk.liczba_aktywnych_studentow(),
    }

    ostatnie_zapisy = _repo_zapisow.ostatnie(supervisor_id=uopz_id, limit=8)

    pilne_oceny = []
    if current_user.role == UserRole.UOPZ:
        from datetime import date, timedelta
        for zapis in _repo_zapisow.zakonczone_dla_uopz(current_user.id):
            if zapis.termin_do:
                deadline        = zapis.termin_do + timedelta(days=7)
                dni_do_deadline = (deadline - date.today()).days
                if dni_do_deadline <= 2:
                    pilne_oceny.append({
                        'zapis':           zapis,
                        'deadline':        deadline,
                        'dni_do_deadline': dni_do_deadline,
                        'przekroczony':    dni_do_deadline < 0,
                    })

    csrf_form = FlaskForm()
    return render_template('dashboard/index.html',
                           statystyki=statystyki,
                           ostatnie_zapisy=ostatnie_zapisy,
                           pilne_oceny=pilne_oceny,
                           csrf_form=csrf_form)
