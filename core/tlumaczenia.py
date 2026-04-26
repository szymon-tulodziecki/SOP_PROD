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


TLUMACZENIA_ROL = {
    'STUDENT':   'Student',
    'UOPZ':      'Opiekun uczelniany',
    'KOMISJA':   'Komisja',
    'DYREKTOR':  'Dyrektor',
    'ADMIN':     'Administrator',
}


def tlumacz_role(val: str) -> str:
    return TLUMACZENIA_ROL.get(val, val)


TLUMACZENIA_STATUSOW = {
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


def tlumacz_status(val: str) -> str:
    return TLUMACZENIA_STATUSOW.get(val, val)
