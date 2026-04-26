from flask import Blueprint, render_template, request
from flask_login import login_required
from core.autoryzacja import wymaga_roli
from core.modele import UserRole
from core.modele.praktyki import ProcessEvent, EventType
from core.extensions import db
from sqlalchemy import desc

logi_bp = Blueprint('logi', __name__)

_ETYKIETY = {
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
    strona   = request.args.get('strona', 1, type=int)
    typ      = request.args.get('typ', '')
    szukaj   = request.args.get('szukaj', '').strip()

    q = ProcessEvent.query.order_by(desc(ProcessEvent.executed_at))

    if typ:
        try:
            q = q.filter(ProcessEvent.event_type == EventType(typ))
        except ValueError:
            pass

    if szukaj:
        from core.modele.praktyki import InternshipEnrollment
        from core.modele.uzytkownicy import User as UserModel
        q = q.join(ProcessEvent.enrollment).join(
            UserModel, InternshipEnrollment.student_id == UserModel.id
        ).filter(
            db.or_(
                UserModel.first_name.ilike(f'%{szukaj}%'),
                UserModel.last_name.ilike(f'%{szukaj}%'),
            )
        )

    zdarzenia = q.paginate(page=strona, per_page=30, error_out=False)

    return render_template(
        'logi/index.html',
        zdarzenia=zdarzenia,
        etykiety=_ETYKIETY,
        typy_zdarzen=[e.value for e in EventType],
        aktywny_typ=typ,
        szukaj=szukaj,
    )
