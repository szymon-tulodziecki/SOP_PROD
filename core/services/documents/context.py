"""Canonical TeX template context builder.

Single source of truth for context shape across all PDF generators
(admin, student, celery worker).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable

from core.extensions import db


# â”€â”€ Formatting helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _fmt(value) -> str:
    if value is None:
        return ''
    if isinstance(value, (date, datetime)):
        return value.strftime('%d.%m.%Y')
    return str(value)


def _iso(value) -> str:
    if value is None:
        return ''
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _g(obj, attr: str, default=''):
    val = getattr(obj, attr, default)
    return val if val is not None else default


_GENDER_FORMS: dict[str, dict[str, str]] = {
    'M': {'pos': 'uzyskaĹ‚',  'par': 'uzyskaĹ‚ czÄ™Ĺ›ciowo',  'neg': 'nie uzyskaĹ‚'},
    'F': {'pos': 'uzyskaĹ‚a', 'par': 'uzyskaĹ‚a czÄ™Ĺ›ciowo', 'neg': 'nie uzyskaĹ‚a'},
}
_GENDER_FORMS_DEFAULT = {'pos': 'uzyskaĹ‚/a', 'par': 'uzyskaĹ‚/a czÄ™Ĺ›ciowo', 'neg': 'nie uzyskaĹ‚/a'}


# â”€â”€ Per-doc-type context extension registry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_CTX_EXT: dict[str, Callable[[dict, object], None]] = {}


def _ext(*doc_types: str):
    """Decorator registering a context extension for one or more document types."""
    def decorator(fn: Callable) -> Callable:
        for t in doc_types:
            _CTX_EXT[t] = fn
        return fn
    return decorator


@_ext('ZAL_2A')
def _ext_zal2a(ctx: dict, zapis) -> None:
    from core.models import InternshipSchedule
    harmonogramy = (
        db.session.query(InternshipSchedule)
        .filter_by(enrollment_id=zapis.id)
        .order_by(InternshipSchedule.learning_outcome_id)
        .all()
    )
    ctx['schedule'] = [
        {
            'efekt_kod':  _g(h.learning_outcome, 'kod') if h.learning_outcome else str(h.learning_outcome_id).zfill(2),
            'efekt_opis': _g(h.learning_outcome, 'opis') if h.learning_outcome else '',
            'dzial':      _g(h, 'department_name', ''),
            'prace':      _g(h, 'example_tasks', ''),
            'dni':        _g(h, 'days_count', 0),
        }
        for h in harmonogramy
    ]


@_ext('ZAL_6')
def _ext_zal6(ctx: dict, zapis) -> None:
    from core.models.journal import JournalEntry
    wpisy = (
        db.session.query(JournalEntry)
        .filter_by(enrollment_id=zapis.id)
        .order_by(JournalEntry.entry_date)
        .all()
    )
    ctx.update({
        'path':          zapis.track_type.value if zapis.track_type else 'STANDARD',
        'data_rozpoczecia': _iso(zapis.start_date),
        'data_zakonczenia': _iso(zapis.end_date),
        'wpisy': [
            {
                'data':     _iso(w.entry_date),
                'opis':     _g(w, 'description', ''),
                'godziny':  _g(w, 'duration_hours', 0),
                'efekt_nr': ', '.join(f"{e.id:02d}" for e in w.learning_outcomes)
                            if w.learning_outcomes else '--',
            }
            for w in wpisy
        ],
    })


@_ext('ZAL_7', 'ZAL_7A')
def _ext_zal7(ctx: dict, zapis) -> None:
    spr = getattr(zapis, 'report', None)
    ctx.update({
        'workplace_description': _g(spr, 'workplace_description') if spr else '',
        'opis_prac':               _g(spr, 'analysis')          if spr else '',
        'skills':                  _g(spr, 'skills')                  if spr else '',
    })


@_ext('ZAL_3C')
def _ext_zal3c(ctx: dict, zapis) -> None:
    fg = zapis.final_grades
    ctx.update({
        'supervisor_grade':         str(fg.supervisor_grade) if fg and fg.supervisor_grade else '',
        'supervisor_grade_description': fg.supervisor_grade_description if fg else '',
        'report_grade': str(fg.report_grade) if fg and fg.report_grade else '',
    })


@_ext('ZAL_4')
def _ext_zal4(ctx: dict, zapis) -> None:
    from core.models import LearningOutcome
    oceny_map        = {o.learning_outcome_id: o for o in (getattr(zapis, 'assessments', None) or [])}
    wszystkie_efekty = db.session.query(LearningOutcome).order_by(LearningOutcome.id).all()

    def _wynik_str(e):
        if e.id not in oceny_map:
            return None
        w = oceny_map[e.id].result
        return w.value if w else None

    ctx.update({
        'assessments': [
            {
                'learning_outcome': {'id': e.id, 'opis': _g(e, 'opis') or _g(e, 'description', ''), 'kod': _g(e, 'kod', '')},
                'wynik': _wynik_str(e),
            }
            for e in wszystkie_efekty
        ],
        'uwagi_uopz': _g(zapis, 'supervisor_grade_description', ''),
    })


@_ext('ZAL_4B')
def _ext_zal4b(ctx: dict, zapis) -> None:
    ctx['dean_decision'] = zapis.dean_decision or ''


@_ext('ZAL_4A', 'ZAL_4a')
def _ext_zal4a(ctx: dict, zapis) -> None:
    from core.models import LearningOutcome, CommitteeOutcomeEvaluation
    s                = zapis.student
    wszystkie_efekty = db.session.query(LearningOutcome).order_by(LearningOutcome.id).all()
    oceny_map        = {
        e.learning_outcome_id: e
        for e in db.session.query(CommitteeOutcomeEvaluation).filter_by(enrollment_id=zapis.id).all()
    }
    gender = _g(s, 'gender', '') or ''
    forma = _GENDER_FORMS.get(gender, _GENDER_FORMS_DEFAULT)
    ctx['oceny_komisji'] = [
        {
            'efekt_kod':  str(e.id).zfill(2),
            'efekt_opis': _g(e, 'opis') or _g(e, 'description', ''),
            'wynik':      oceny_map[e.id].result.value if e.id in oceny_map else None,
            'uwagi':      (oceny_map[e.id].notes or '') if e.id in oceny_map else '',
        }
        for e in wszystkie_efekty
    ]
    ctx['forma']             = forma
    ctx['komentarz_komisji'] = zapis.committee_comment or ''


@_ext('ZAL_8')
def _ext_zal8(ctx: dict, zapis) -> None:
    fg   = zapis.final_grades
    sw   = zapis.examination
    supervisor = zapis.supervisor

    def _f(v):
        return float(v) if v is not None else None

    ctx['zapis'].update({
        'company_display_name':            ctx['company']['nazwa'],
        'termin_od':              _fmt(zapis.start_date),
        'termin_do':              _fmt(zapis.end_date),
        'report_grade':     _f(fg.report_grade)     if fg else None,
        'supervisor_grade':             _f(fg.supervisor_grade) if fg else None,
        'workplace_grade':             _f(fg.workplace_grade)  if fg else None,
        'exam_question_1':   sw.question_1           if sw else None,
        'exam_grade_1':     _f(sw.grade_1)          if sw else None,
        'exam_question_2':   sw.question_2           if sw else None,
        'exam_grade_2':     _f(sw.grade_2)          if sw else None,
        'exam_question_3':   sw.question_3           if sw else None,
        'exam_grade_3':     _f(sw.grade_3)          if sw else None,
        'supervisor':                   {'first_name': supervisor.first_name, 'last_name': supervisor.last_name} if supervisor else None,
        'komisja_przewodniczacy': sw.commission_chair     if sw else None,
        'komisja_czlonek_2':      sw.commission_member_2  if sw else None,
        'komisja_czlonek_3':      sw.commission_member_3  if sw else None,
    })
    ctx['data_egzaminu'] = date.today().strftime('%d.%m.%Y')


# â”€â”€ Sub-builders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_STUDY_MODE_MAP = {
    'full-time':      'stacjonarne',
    'part-time':      'niestacjonarne',
    'stacjonarne':    'stacjonarne',
    'niestacjonarne': 'niestacjonarne',
}


def _ctx_student(s) -> dict:
    return {
        'first_name':   _g(s, 'first_name'),
        'last_name':    _g(s, 'last_name'),
        'album_number': _g(s, 'album_number'),
        'imie':         _g(s, 'first_name'),
        'nazwisko':     _g(s, 'last_name'),
        'nr_albumu':    _g(s, 'album_number'),
        'numer_albumu': _g(s, 'album_number'),
        'plec':         _g(s, 'gender', ''),
        'kierunek':     _g(s, 'field_of_study') or 'Informatyka',
        'specialization':  _g(s, 'specialization', ''),
        'tryb_studiow': _STUDY_MODE_MAP.get(_g(s, 'study_mode', '').lower(), _g(s, 'study_mode', '')),
    }


def _company_value(company, details, company_attr: str, details_attr: str) -> str:
    value = _g(company, company_attr) if company else None
    if value:
        return value
    return _g(details, details_attr) if details else ''


def _ctx_firma(zapis, dm) -> tuple[dict, str, str, str]:
    f = zapis.company
    nazwa  = _company_value(f, dm, 'name', 'company_name')
    adres  = _company_value(f, dm, 'address', 'company_address')
    zip_   = _company_value(f, dm, 'zip_code', 'company_zip')
    city   = _company_value(f, dm, 'city', 'company_city')
    nip    = _company_value(f, dm, 'tax_id', 'company_tax_id')
    miasto = f"{zip_} {city}".strip() if zip_ else city
    return {
        'nazwa': nazwa, 'adres': adres, 'miasto': miasto, 'nip_krs': nip,
        'name':  nazwa, 'address': adres, 'city': miasto,
    }, nazwa, adres, miasto


def _ctx_zopz(dm) -> dict:
    return {
        'imie_nazwisko': dm.workplace_mentor_name     if dm else '',
        'stanowisko':    dm.workplace_mentor_position if dm else '',
        'telefon':       dm.workplace_mentor_phone    if dm else '',
        'email':         dm.workplace_mentor_email    if dm else '',
    }


def _ctx_uopz(supervisor) -> dict:
    return {
        'first_name':    _g(supervisor, 'first_name') if supervisor else '',
        'last_name':     _g(supervisor, 'last_name')  if supervisor else '',
        'imie_nazwisko': f"{supervisor.first_name} {supervisor.last_name}" if supervisor else '',
    }


# â”€â”€ Canonical builder â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def build_context(enrollment, document_type: str) -> dict:
    """Builds the TeX template context dictionary for a given document type."""
    zapis = enrollment
    event_type = document_type
    s    = zapis.student
    p    = zapis.internship
    supervisor = zapis.supervisor
    dm   = zapis.workplace_details

    firma_dict, company_display_name, company_display_address, company_city = _ctx_firma(zapis, dm)

    ctx: dict = {
        'student': _ctx_student(s),
        'internship': {
            'rok_uczelniany': _g(p, 'academic_year')      if p else '',
            'semestr':        _g(p, 'semester')            if p else '',
            'wymiar_godzin':  _g(p, 'required_hours', 160) if p else 160,
        },
        'company': firma_dict,
        'terminy': {
            'od': _fmt(zapis.start_date),
            'do': _fmt(zapis.end_date),
        },
        'zopz': _ctx_zopz(dm),
        'supervisor': _ctx_uopz(supervisor),
        'firma_upowazniony':            dm.authorized_person          if dm else '',
        'authorized_person_position': dm.authorized_person_position if dm else '',
        'justification':   zapis.path_justification.justification if zapis.path_justification else '',
        'specialization':    _g(s, 'specialization', '') if s else '',
        'lacznie_godzin': _g(zapis, 'total_hours_logged', 0),
        'data_wniosku':   '',
        'zapis': {
            'path':      zapis.track_type.value if zapis.track_type else 'STANDARD',
            'company_display_name':  company_display_name,
            'company_display_address':  company_display_address,
            'company_city': company_city,
        },
    }

    ext = _CTX_EXT.get(event_type)
    if ext:
        ext(ctx, zapis)
    return ctx
