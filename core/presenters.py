"""Logika prezentacji wyniesiona z szablonów Jinja.

Widoki budują tu gotowe etykiety, klasy CSS i wartości pochodne,
a szablony jedynie je wyświetlają — bez mapowań i obliczeń w HTML.
"""
from __future__ import annotations

from core.translations import LOG_EVENT_LABELS


# ── Ścieżki praktyk ───────────────────────────────────────────────────────────

def path_label(path_value: str | None) -> str:
    """Etykieta ścieżki w panelu admina (A/B)."""
    return 'A — Standardowa' if path_value == 'STANDARD' else 'B — Uznanie efektów'


STUDENT_PATH_LABELS = {
    'STANDARD':   'Standardowa',
    'EMPLOYMENT': 'Praca etatowa',
}


def student_path_label(path_value: str | None) -> str:
    return STUDENT_PATH_LABELS.get(path_value, 'Działalność gospodarcza')


def employment_path_label(path_type) -> str:
    """Etykieta podścieżki B na karcie ocen."""
    value = path_type.value if path_type is not None else None
    return 'Staż/zatrudnienie' if value == 'EMPLOYMENT' else 'Dział. gospod.'


# ── Statusy zgłoszeń ──────────────────────────────────────────────────────────

_HERO_MODIFIERS = {
    'PENDING':           'pending',
    'AWAITING_APPROVAL': 'awaiting',
    'COMMISSION_REVIEW': 'commission',
    'DIRECTOR_APPROVAL': 'director',
    'IN_PROGRESS':       'progress',
    'COMPLETED':         'completed',
    'REJECTED':          'rejected',
}

ENROLLMENT_STATUS_BADGES = {
    'PENDING':           ('status--in-progress', 'Oczekuje na zatwierdzenie'),
    'AWAITING_APPROVAL': ('status--planned',     'Oczekuje na akceptację UOPZ'),
    'IN_PROGRESS':       ('status--completed',   'Zatwierdzona — w realizacji'),
    'COMPLETED':         ('status--completed',   'Zakończona'),
    'REVISION_REQUIRED': ('status--odrzucona',   'Czeka na poprawki'),
    'COMMISSION_REVIEW': ('status--planned',     'Weryfikacja komisji'),
    'DIRECTOR_APPROVAL': ('status--planned',     'Decyzja dyrektora'),
    'REJECTED':          ('status--odrzucona',   'Odrzucona'),
}

COMMITTEE_STATUS_BADGES = {
    'COMMISSION_REVIEW': ('status--planned',     'Do rozpatrzenia przez komisję'),
    'REVISION_REQUIRED': ('status--odrzucona',   'Czeka na poprawki studenta'),
    'AWAITING_APPROVAL': ('status--in-progress', 'Zwrócone do uzupełnienia'),
    'DIRECTOR_APPROVAL': ('status--planned',     'Przekazane do Dyrektora'),
    'IN_PROGRESS':       ('status--completed',   'Zatwierdzona — w realizacji'),
}


def _status_badge(mapa: dict, status_value: str) -> dict:
    cls, label = mapa.get(status_value, ('status--draft', status_value))
    return {
        'cls':   cls,
        'label': label,
        'hero':  'u-enrollment-hero--' + _HERO_MODIFIERS.get(status_value, 'default'),
    }


def enrollment_status_badge(status_value: str) -> dict:
    """Odznaka statusu w szczegółach zgłoszenia (panel admina/UOPZ)."""
    return _status_badge(ENROLLMENT_STATUS_BADGES, status_value)


def committee_status_badge(status_value: str) -> dict:
    """Odznaka statusu w widoku weryfikacji komisji."""
    return _status_badge(COMMITTEE_STATUS_BADGES, status_value)


DOCUMENT_STATUS_BADGES = {
    'COMPLETED':         ('status--zakonczona', 'Zakończona'),
    'IN_PROGRESS':       ('status--aktywna',    'W trakcie'),
    'AWAITING_APPROVAL': ('status--oczekuje',   'Oczekuje na akceptację'),
    'COMMISSION_REVIEW': ('status--oczekuje',   'Komisja'),
    'DIRECTOR_APPROVAL': ('status--oczekuje',   'Dyrektor'),
    'REVISION_REQUIRED': ('status--oczekuje',   'Czeka na poprawki'),
    'REJECTED':          ('status--oczekuje',   'Odrzucona'),
    'PENDING':           ('status--oczekuje',   'Oczekuje'),
}


def document_status_badge(status_value: str) -> dict:
    cls, label = DOCUMENT_STATUS_BADGES.get(status_value, ('status--oczekuje', status_value))
    return {'cls': cls, 'label': label}


# ── Decyzje komisji / dyrektora ───────────────────────────────────────────────

_COMMITTEE_DECISION_BADGES = {
    'APPROVED':           ('status--completed',   'Opinia pozytywna',           'Pozytywna',           'u-card-border-top-success'),
    'PARTIALLY_APPROVED': ('status--in-progress', 'Opinia częściowo pozytywna', 'Częściowo pozytywna', 'u-card-border-top-warning'),
}
_COMMITTEE_DECISION_DEFAULT = ('status--odrzucona', 'Opinia negatywna', 'Negatywna', 'u-card-border-top-danger')


def committee_decision_badge(decision: str | None) -> dict | None:
    if not decision:
        return None
    cls, label, label_short, border = _COMMITTEE_DECISION_BADGES.get(decision, _COMMITTEE_DECISION_DEFAULT)
    return {'cls': cls, 'label': label, 'label_short': label_short, 'border': border}


def dean_decision_badge(decision: str | None) -> dict | None:
    if not decision:
        return None
    if decision == 'APPROVED':
        return {'cls': 'status--completed', 'label': 'Zatwierdzone'}
    return {'cls': 'status--odrzucona', 'label': 'Odrzucone'}


# ── Logi systemowe ────────────────────────────────────────────────────────────

def log_event_badge(event_type_value: str, actor_role_value: str | None) -> dict:
    if event_type_value == 'DYREKTOR_DECYZJA':
        return {'label': 'Decyzja Dyrektora', 'cls': 'status--zakonczona'}
    if event_type_value == 'KOMISJA_DECYZJA':
        if actor_role_value == 'KOMISJA':
            return {'label': 'Decyzja Komisji', 'cls': 'status--w-trakcie'}
        if actor_role_value == 'UOPZ':
            return {'label': 'Decyzja UOPZ', 'cls': 'status--w-trakcie'}
        return {'label': 'Decyzja Admina', 'cls': 'status--szkic'}
    return {'label': LOG_EVENT_LABELS.get(event_type_value, event_type_value), 'cls': 'status--szkic'}


_LOG_DECISION_BADGES = {
    'APPROVED':           ('Zatwierdzone',     'status--zakonczona'),
    'PARTIALLY_APPROVED': ('Wymaga poprawek',  'status--w-trakcie'),
    'REJECTED':           ('Odrzucone',        'status--odrzucona'),
}


def log_decision_badge(decision: str | None) -> dict | None:
    if decision not in _LOG_DECISION_BADGES:
        return None
    label, cls = _LOG_DECISION_BADGES[decision]
    return {'label': label, 'cls': cls}


# ── Role użytkowników ─────────────────────────────────────────────────────────

ROLE_BADGE_CSS = {
    'ADMIN':    'admin',
    'UOPZ':     'supervisor',
    'KOMISJA':  'komisja',
    'DYREKTOR': 'dyrektor',
    'STUDENT':  'student',
}
_ROLE_ORDER = ['ADMIN', 'DYREKTOR', 'KOMISJA', 'UOPZ', 'STUDENT']

SIDEBAR_ROLE_LABELS = {
    'ADMIN':    'Administrator',
    'UOPZ':     'Opiekun uczelniany (UOPZ)',
    'KOMISJA':  'Przewodniczący Komisji',
    'DYREKTOR': 'Dyrektor Instytutu',
}


def role_badges(user) -> list[dict]:
    """Posortowane odznaki ról użytkownika (multirola lub rola główna)."""
    values = {r.value for r in user.roles} or ({user.role.value} if user.role else set())
    return [{'value': v, 'css': ROLE_BADGE_CSS.get(v, 'student')} for v in _ROLE_ORDER if v in values]


def sidebar_role_label(user) -> str:
    if not getattr(user, 'role', None):
        return ''
    return SIDEBAR_ROLE_LABELS.get(user.role.value, '')


def active_toggle(is_active: bool, feminine: bool = False) -> dict:
    """Stan + akcja przełączenia aktywności (konto/firma)."""
    if feminine:
        status_label = 'Aktywna' if is_active else 'Nieaktywna'
    else:
        status_label = 'Aktywny' if is_active else 'Nieaktywny'
    return {
        'status_cls':   'status--zakonczona' if is_active else 'status--szkic',
        'status_label': status_label,
        'akcja':        'dezaktywować' if is_active else 'aktywować',
        'przycisk':     'Dezaktywuj' if is_active else 'Aktywuj',
        'przycisk_cls': 'przycisk--ostrzezenie' if is_active else 'przycisk--drugorzedny',
    }


# ── Harmonogram praktyki ──────────────────────────────────────────────────────

LIMIT_DNI_MAX = 120
LIMIT_DNI_MIN = 100


def schedule_summary(efekty, harmonogram_dict) -> dict:
    """Wiersze harmonogramu + suma dni i klasy CSS zależne od limitów."""
    wiersze = []
    suma = 0
    for e in efekty:
        h = harmonogram_dict.get(e.id)
        dni = h.days_count if h else 0
        if h and h.days_count > 0:
            suma += h.days_count
        wiersze.append({
            'nr':      f'{e.id:02d}',
            'efekt':   e,
            'dzial':   h.department_name if h else None,
            'zadania': h.example_tasks if h else None,
            'dni':     dni,
            'brak':    not h or h.days_count == 0,
        })

    if suma > LIMIT_DNI_MAX:
        badge_cls, total_cls, alert = 'status--draft u-status-danger', 'u-day-total--high', 'za_duzo'
    elif suma < LIMIT_DNI_MIN:
        badge_cls, total_cls, alert = 'status--in-progress', 'u-day-total--low', 'za_malo'
    else:
        badge_cls, total_cls, alert = 'status--completed', 'u-day-total--ok', None

    return {
        'wiersze':   wiersze,
        'suma':      suma,
        'limit':     LIMIT_DNI_MAX,
        'badge_cls': badge_cls,
        'total_cls': total_cls,
        'alert':     alert,
    }


# ── Praktyki oczekujące na usunięcie ─────────────────────────────────────────

_OKRES_USUNIECIA_S = 7 * 86400


def dni_do_usuniecia(deleted_at, now) -> int:
    return int((deleted_at.timestamp() + _OKRES_USUNIECIA_S - now.timestamp()) / 86400)


# ── Oceny efektów uczenia się ─────────────────────────────────────────────────

_OUTCOME_RESULT_BADGES = {
    'ACHIEVED':           ('Uzyskał/a',     'status--completed',   ''),
    'PARTIALLY_ACHIEVED': ('Częściowo',     'status--in-progress', 'u-row-partial'),
    'NOT_ACHIEVED':       ('Nie uzyskał/a', 'status--odrzucona',   'u-row-negative'),
}


def outcome_result_badge(result_value: str) -> dict:
    label, cls, row_cls = _OUTCOME_RESULT_BADGES.get(result_value, (result_value, 'status--draft', ''))
    return {'label': label, 'cls': cls, 'row_cls': row_cls}


def outcome_result_counts(oceny: dict) -> dict:
    """Statystyka wyników komisji do podsumowania nad tabelą efektów."""
    values = [ev.result.value for ev in oceny.values()]
    return {
        'uzyskal':   values.count('ACHIEVED'),
        'czesciowo': values.count('PARTIALLY_ACHIEVED'),
        'nie':       values.count('NOT_ACHIEVED'),
    }


def split_outcome_description(description: str, fallback) -> dict:
    """Rozbija opis efektu 'KOD: treść' na kod i treść."""
    if ':' in description:
        kod, opis = description.split(':', 1)
        return {'kod': kod, 'opis': opis.strip()}
    return {'kod': str(fallback), 'opis': description}


# ── Pozostałe ─────────────────────────────────────────────────────────────────

STUDY_MODE_LABELS = {
    'full-time': 'Stacjonarne',
    'part-time': 'Niestacjonarne',
}


def study_mode_label(mode: str | None) -> str | None:
    if not mode:
        return None
    return STUDY_MODE_LABELS.get(mode, mode)


def flash_icon(category: str) -> str:
    return {'danger': '✕', 'success': '✓'}.get(category, 'ℹ')
