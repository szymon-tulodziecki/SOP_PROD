from flask import Blueprint, render_template, request
from flask_login import login_required
from core.autoryzacja import roles_required
from core.modele import UserRole
from core.modele.internships import EventType
from core.repozytoria import LogRepository

logi_bp = Blueprint('logi', __name__)

_repo_logow = LogRepository()

_LABELS = {
    'ADMIN_KOMENTARZ':        'Komentarz admina',
    'UOPZ_KOMENTARZ':         'Komentarz UOPZ',
    'POWIADOMIENIE_STUDENTA':  'Powiadomienie studenta',
    'KOMISJA_DECYZJA':        'Decyzja weryfikacji',
    'DYREKTOR_DECYZJA':       'Decyzja Dyrektora',
}

@logi_bp.route('/', methods=['GET'])
@login_required
@roles_required(UserRole.ADMIN)
def lista_logow():
    page              = request.args.get('strona', 1, type=int)
    event_type_filter = request.args.get('typ', '')
    search_query      = request.args.get('szukaj', '').strip()

    events = _repo_logow.wszystkie_zdarzenia(
        filtr_typ=event_type_filter or None,
        szukaj_user=search_query,
        strona=page,
    )

    return render_template(
        'logi/index.html',
        events=events,
        labels=_LABELS,
        event_types=[e.value for e in EventType],
        active_type=event_type_filter,
        search_query=search_query,
    )
