import re
from datetime import date, datetime

import re
from datetime import date, datetime
from pylatexenc.latexencode import unicode_to_latex


def sanitize(value, max_length: int = 500) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    if max_length:
        text = text[:max_length]
    return unicode_to_latex(text)


def sanitize_date(value, fmt: str = '%d.%m.%Y') -> str:
    if value is None:
        return '—'
    if isinstance(value, (date, datetime)):
        return value.strftime(fmt)
    try:
        return date.fromisoformat(str(value)).strftime(fmt)
    except ValueError:
        return sanitize(str(value))


def sanitize_int(value) -> str:
    if value is None:
        return '0'
    try:
        return str(int(value))
    except (ValueError, TypeError):
        return '0'
