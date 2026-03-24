import re
from datetime import date, datetime

_LATEX_SPECIAL = {
    '&': r'\&',
    '%': r'\%',
    '$': r'\$',
    '#': r'\#',
    '_': r'\_',
    '{': r'\{',
    '}': r'\}',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
    '\\': r'\textbackslash{}',
}

_LATEX_SPECIAL_RE = re.compile('|'.join(re.escape(k) for k in _LATEX_SPECIAL.keys()))


def sanitize(value, max_length: int = 500) -> str:
    if value is None:
        return ''
    text = str(value).strip()
    if max_length:
        text = text[:max_length]
    return _LATEX_SPECIAL_RE.sub(lambda m: _LATEX_SPECIAL[m.group()], text)


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
