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
