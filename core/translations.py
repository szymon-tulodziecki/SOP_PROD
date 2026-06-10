STATUS_CSS_MAP = {
    'PENDING':           'draft',
    'AWAITING_APPROVAL': 'planned',
    'COMMISSION_REVIEW': 'planned',
    'DIRECTOR_APPROVAL': 'planned',
    'REVISION_REQUIRED': 'draft',
    'IN_PROGRESS':       'w-trakcie',
    'COMPLETED':         'zakonczona',
    'REJECTED':          'draft',
}


def status_css_class(status_value: str) -> str:
    """Zwraca fragment klasy CSS dla danej wartości statusu (np. 'status--draft')."""
    return STATUS_CSS_MAP.get(status_value, 'draft')


ROLE_TRANSLATIONS = {
    'STUDENT':   'Student',
    'UOPZ':      'Opiekun uczelniany',
    'KOMISJA':   'Komisja',
    'DYREKTOR':  'Dyrektor',
    'ADMIN':     'Administrator',
}


def translate_role(val: str) -> str:
    return ROLE_TRANSLATIONS.get(val, val)


STATUS_TRANSLATIONS = {
    'PENDING':            'Oczekuje na wysłanie',
    'AWAITING_APPROVAL':  'Oczekuje na zatwierdzenie',
    'COMMISSION_REVIEW':  'Weryfikacja komisji',
    'REVISION_REQUIRED':  'Wymaga uzupełnień',
    'DIRECTOR_APPROVAL':  'Oczekuje na dyrektora',
    'IN_PROGRESS':        'W trakcie',
    'COMPLETED':          'Zakończona',
    'REJECTED':           'Odrzucone',
    'ACTIVE':             'Aktywna',
    'INACTIVE':           'Nieaktywna',
}


def translate_status(val: str) -> str:
    return STATUS_TRANSLATIONS.get(val, val)


LOG_EVENT_LABELS = {
    'ADMIN_KOMENTARZ':        'Komentarz admina',
    'UOPZ_KOMENTARZ':         'Komentarz UOPZ',
    'POWIADOMIENIE_STUDENTA': 'Powiadomienie studenta',
    'KOMISJA_DECYZJA':        'Decyzja weryfikacji',
    'DYREKTOR_DECYZJA':       'Decyzja Dyrektora',
}
