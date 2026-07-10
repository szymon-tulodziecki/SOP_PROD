from flask import Blueprint, render_template, request
from flask_login import login_required
from core.auth import roles_required
from core.models import UserRole
from core.models.internships import EventType
from core.presenters import log_decision_badge, log_event_badge
from core.repositories import LogRepository
from core.translations import LOG_EVENT_LABELS

logi_bp = Blueprint("logi", __name__)

_repo_logow = LogRepository()


def _wiersz_logu(event) -> dict:
    actor_role = (
        event.executed_by.role.value if event.executed_by and event.executed_by.role else None
    )
    return {
        "z": event,
        "typ": log_event_badge(event.event_type.value, actor_role),
        "decyzja": log_decision_badge(event.decision),
    }


@logi_bp.route("/", methods=["GET"])
@login_required
@roles_required(UserRole.ADMIN)
def lista_logow():
    page = request.args.get("strona", 1, type=int)
    event_type_filter = request.args.get("event_type", "")
    search_query = request.args.get("szukaj", "").strip()

    events = _repo_logow.wszystkie_zdarzenia(
        filtr_typ=event_type_filter or None,
        szukaj_user=search_query,
        strona=page,
    )

    return render_template(
        "logi/index.html",
        events=events,
        wiersze=[_wiersz_logu(z) for z in events.items],
        labels=LOG_EVENT_LABELS,
        event_types=[e.value for e in EventType],
        active_type=event_type_filter,
        search_query=search_query,
    )
