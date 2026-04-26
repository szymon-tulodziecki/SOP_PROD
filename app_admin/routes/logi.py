from flask import Blueprint, render_template, request
from flask_login import login_required
from core.autoryzacja import wymaga_roli
from core.modele import UserRole
from core.modele.praktyki import ProcessEvent, EventType
from core.extensions import db
from sqlalchemy import desc

logi_bp = Blueprint('logi', __name__)

_LABELS = {
    'ADMIN_KOMENTARZ':        'Komentarz admina',
    'UOPZ_KOMENTARZ':         'Komentarz UOPZ',
    'POWIADOMIENIE_STUDENTA':  'Powiadomienie studenta',
    'KOMISJA_DECYZJA':        'Decyzja weryfikacji',
    'DYREKTOR_DECYZJA':       'Decyzja Dyrektora',
}

@logi_bp.route('/', methods=['GET'])
@login_required
@wymaga_roli(UserRole.ADMIN)
def lista_logow():
    page              = request.args.get('strona', 1, type=int)
    event_type_filter = request.args.get('typ', '')
    search_query      = request.args.get('szukaj', '').strip()

    q = ProcessEvent.query.order_by(desc(ProcessEvent.executed_at))

    if event_type_filter:
        try:
            q = q.filter(ProcessEvent.event_type == EventType(event_type_filter))
        except ValueError:
            pass

    if search_query:
        from core.modele.praktyki import InternshipEnrollment
        from core.modele.uzytkownicy import User as UserModel
        q = q.join(ProcessEvent.enrollment).join(
            UserModel, InternshipEnrollment.student_id == UserModel.id
        ).filter(
            db.or_(
                UserModel.first_name.ilike(f'%{search_query}%'),
                UserModel.last_name.ilike(f'%{search_query}%'),
            )
        )

    events = q.paginate(page=page, per_page=30, error_out=False)

    return render_template(
        'logi/index.html',
        events=events,
        labels=_LABELS,
        event_types=[e.value for e in EventType],
        active_type=event_type_filter,
        search_query=search_query,
    )
