"""
core/uslugi/dokumenty.py

Warstwa domenowa dokumentów praktyki.

Zawiera dwie odpowiedzialności:
  1. Polityka dostępności dokumentów (DocumentEntry + _DOCUMENT_POLICY)
     — zastępuje powielone reguły z app_admin i app_student.
  2. Kanoniczny builder kontekstu TeX (buduj_kontekst)
     — jedno miejsce zamiast trzech niezależnych implementacji w:
       • app_admin/routes/zarzadzanie/dokumenty_studentow.py (_build_context)
       • app_student/routes/dokumenty.py (_build_context / _serialize_context)
       • celery_app.py (generate_pdf_dziennik — inline)

Oba kontrolery importują z tego modułu i nie zawierają własnej logiki
budowania kontekstu ani reguł dostępności.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable

from core.extensions import db

# ---------------------------------------------------------------------------
# Mapa szablonów (canonical — jeden słownik dla całej aplikacji)
# ---------------------------------------------------------------------------

DOC_CONFIG: dict[str, tuple[str, str]] = {
    'ZAL_1':  ('zal1_porozumienie.tex.j2',  'zal1_porozumienie.pdf'),
    'ZAL_2':  ('zal2_program.tex.j2',        'zal2_program.pdf'),
    'ZAL_2A': ('zal2a_program.tex.j2',       'zal2a_program.pdf'),
    'ZAL_3A': ('zal3a_skierowanie.tex.j2',   'zal3a_skierowanie.pdf'),
    'ZAL_3B': ('zal3b_karta_zakladowa.tex.j2','zal3b_karta_zakladowa.pdf'),
    'ZAL_3C': ('zal3c_suplement_uopz.tex.j2', 'zal3c_suplement_uopz.pdf'),
    'ZAL_4':  ('zal4_efekty.tex.j2',         'zal4_efekty.pdf'),
    'ZAL_4A': ('zal4a_komisja.tex.j2',       'zal4a_komisja.pdf'),
    'ZAL_4B': ('zal4b_wniosek.tex.j2',       'zal4b_wniosek.pdf'),
    'ZAL_6':  ('zal6_dziennik.tex.j2',       'zal6_dziennik.pdf'),
    'ZAL_7':  ('zal7_sprawozdanie.tex.j2',   'zal7_sprawozdanie.pdf'),
    'ZAL_7A': ('zal7a_sprawozdanie.tex.j2',  'zal7a_sprawozdanie.pdf'),
    'ZAL_8':  ('zal8_protokol.tex.j2',       'zal8_protokol.pdf'),
    'ZAL_9':  ('zal9_oswiadczenie.tex.j2',   'zal9_oswiadczenie.pdf'),
}

STATIC_TEMPLATES: dict[str, tuple[str, str]] = {
    'ankieta': ('zal5_ankieta.tex.j2', 'zal5_ankieta.pdf'),
}


# ---------------------------------------------------------------------------
# Polityka dostępności dokumentów (Specification Pattern)
# ---------------------------------------------------------------------------

@dataclass
class DocumentEntry:
    """Deklaracja jednego dokumentu i warunków jego dostępności.

    available_when: callable(ctx) → bool
    unavailable_reason: callable(ctx) → str | None
    """
    name: str
    doc_type: str | None = None       # None → dokument statyczny
    description: str | None = None
    static_key: str | None = None
    available_when: Callable = field(default=lambda _ctx: True)
    unavailable_reason: Callable = field(default=lambda _ctx: None)

    def resolve(self, ctx: dict) -> dict:
        available = self.available_when(ctx)
        entry = {
            'name':     self.name,
            'opis':     self.description,
            'dostepny': available,
            'powod':    None if available else self.unavailable_reason(ctx),
        }
        if self.static_key:
            entry.update({'staly': True, 'klucz_staly': self.static_key})
        else:
            entry.update({'dynamiczny': True, 'typ': self.doc_type,
                          'zapis_id': ctx['zapis_id']})
        return entry


def _sep(name: str) -> dict:
    return {'separator': True, 'name': name}



# Reguły dostępności — czytelne funkcje zamiast anonimowych lambdy
def _zawsze(_ctx: dict) -> bool:          return True                                         # noqa: E704
def _w_trakcie_lub_zakonczona(ctx):       return ctx['w_trakcie'] or ctx['zakonczona']        # noqa: E704
def _zakonczona(ctx):                     return ctx['zakonczona']                            # noqa: E704
def _oceniona(ctx):                       return ctx['oceniona']                              # noqa: E704
def _ma_harmonogram(ctx):                 return ctx['harmonogram_count'] > 0                 # noqa: E704
def _firma_custom(ctx):                   return ctx['firma_custom']                          # noqa: E704
def _firma_bez_umowy(ctx):                return ctx['firma_bez_umowy']                       # noqa: E704
def _dziekan_lub_zakonczona(ctx):         return ctx['dziekan_zatwierdził'] or ctx['zakonczona']  # noqa: E704
def _po_egzaminie(ctx):                   return ctx.get('po_egzaminie', False)                    # noqa: E704

_POWOD_HARMONOGRAM    = lambda _: 'Wymaga wypełnionego harmonogramu'            # noqa: E731
_POWOD_W_TRAKCIE      = lambda _: 'Dostępny po zatwierdzeniu praktyki'          # noqa: E731
_POWOD_ZAKONCZONA     = lambda _: 'Dostępny po zakończeniu praktyki'            # noqa: E731
_POWOD_OCENIONA       = lambda _: 'Dostępny po wystawieniu oceny przez UOPZ'   # noqa: E731
_POWOD_EGZAMIN        = lambda _: 'Dostępny po egzaminie komisyjnym'            # noqa: E731
_POWOD_DZIEKAN        = lambda _: 'Dostępny po decyzji dziekana'                # noqa: E731


def _docs_standard() -> list:
    return [
        _sep('Dokumenty startowe'),
        DocumentEntry('Zał. 9 – Oświadczenie instytucji', 'ZAL_9',
                      'Do wypełnienia przez zakład pracy',
                      available_when=_firma_custom),
        DocumentEntry('Zał. 1 – Porozumienie uczelnia ↔ zakład', 'ZAL_1',
                      'Dla firm bez stałej umowy z ANS',
                      available_when=_firma_bez_umowy),
        DocumentEntry('Zał. 2 – Program praktyki', 'ZAL_2',
                      'Z danymi studenta i firmy'),
        DocumentEntry('Zał. 2a – Indywidualny Program Praktyk', 'ZAL_2A',
                      'Harmonogram efektów — student + UOPZ + ZOPZ',
                      available_when=_ma_harmonogram,
                      unavailable_reason=_POWOD_HARMONOGRAM),
        _sep('Załącznik nr 3 — Karta Praktyki Zawodowej'),
        DocumentEntry('Zał. 3a – Skierowanie na praktykę', 'ZAL_3A',
                      'Przepustka do firmy — drukujesz i przynosisz pierwszego dnia'),
        _sep('W trakcie praktyki'),
        DocumentEntry('Zał. 3b – Karta zakładowa (druk do wypełnienia)', 'ZAL_3B',
                      'Firma wypełnia i podpisuje przez 6 miesięcy'),
        DocumentEntry('Zał. 6 – Dziennik praktyki', 'ZAL_6',
                      'Generowany z wpisów dziennika',
                      available_when=_w_trakcie_lub_zakonczona,
                      unavailable_reason=_POWOD_W_TRAKCIE),
        _sep('Dostępne po zakończeniu praktyki'),
        DocumentEntry('Zał. 4 – Potwierdzenie efektów uczenia się', 'ZAL_4',
                      'Podpisuje ZOPZ + UOPZ',
                      available_when=_zakonczona,
                      unavailable_reason=_POWOD_ZAKONCZONA),
        DocumentEntry('Zał. 7 – Sprawozdanie końcowe', 'ZAL_7',
                      'Podpisuje student',
                      available_when=_zakonczona,
                      unavailable_reason=_POWOD_ZAKONCZONA),
        _sep('Rozliczenie na uczelni'),
        DocumentEntry('Zał. 5 – Ankieta oceny praktyki', static_key='ankieta',
                      description='Formularz anonimowej ankiety'),
        DocumentEntry('Zał. 3c – Ocena uczelniana (UOPZ)', 'ZAL_3C',
                      'Ocena UOPZ + ocena sprawozdania',
                      available_when=_oceniona,
                      unavailable_reason=_POWOD_OCENIONA),
        DocumentEntry('Zał. 8 – Protokół egzaminu komisji', 'ZAL_8',
                      'Sporządzany przez Komisję po ustnym egzaminie z praktyki',
                      available_when=_po_egzaminie,
                      unavailable_reason=_POWOD_EGZAMIN),
    ]


def _docs_employment_own_business() -> list:
    return [
        DocumentEntry('Zał. 4b – Wniosek o zaliczenie', 'ZAL_4B',
                      'Praca etatowa / własna działalność'),
        DocumentEntry('Zał. 7a – Sprawozdanie z pracy/działalności', 'ZAL_7A',
                      'Zatwierdza przełożony/UOPZ',
                      available_when=_w_trakcie_lub_zakonczona,
                      unavailable_reason=_POWOD_W_TRAKCIE),
        DocumentEntry('Zał. 4a – Potwierdzenie efektów (komisja)', 'ZAL_4A',
                      '13 efektów: uzyskał / częściowo / nie',
                      available_when=_dziekan_lub_zakonczona,
                      unavailable_reason=_POWOD_DZIEKAN),
        _sep('Po egzaminie komisji'),
        DocumentEntry('Zał. 5 – Ankieta', static_key='ankieta'),
        DocumentEntry('Zał. 8 – Protokół egzaminu komisji', 'ZAL_8',
                      available_when=_po_egzaminie,
                      unavailable_reason=_POWOD_EGZAMIN),
    ]


_DOCUMENT_POLICY: dict[str, Callable[[], list]] = {
    'STANDARD':     _docs_standard,
    'EMPLOYMENT':   _docs_employment_own_business,
    'OWN_BUSINESS': _docs_employment_own_business,
}


def buduj_flagi(zapis) -> dict:
    """Oblicza flagi stanu zapisu używane przez politykę dostępności."""
    from core.modele import EnrollmentStatus, InternshipSchedule

    w_trakcie  = zapis.status == EnrollmentStatus.IN_PROGRESS
    zakonczona = zapis.status == EnrollmentStatus.COMPLETED
    return {
        'zapis_id':            str(zapis.id),
        'w_trakcie':           w_trakcie,
        'zakonczona':          zakonczona,
        'oceniona':            zakonczona and (zapis.final_grades and zapis.final_grades.supervisor_grade) is not None,
        'dziekan_zatwierdził': w_trakcie or zakonczona,
        'po_egzaminie':        zapis.final_grade is not None,
        'harmonogram_count':   db.session.execute(
                                 db.select(db.func.count()).select_from(InternshipSchedule).filter_by(enrollment_id=zapis.id)
                               ).scalar(),
        'firma_bez_umowy':     not zapis.firma or not zapis.firma.has_standing_agreement,
        'firma_custom':        not zapis.company_id,
    }


def rozwiaz_dokumenty(zapis) -> list[dict]:
    """Zwraca listę dokumentów dla danego zapisu zgodnie z polityką ścieżki."""
    sciezka = zapis.track_type.value if zapis.track_type else 'STANDARD'
    factory = _DOCUMENT_POLICY.get(sciezka, _docs_standard)
    ctx = buduj_flagi(zapis)
    result = []
    for entry in factory():
        if isinstance(entry, dict):           # separator
            result.append(entry)
        else:
            result.append(entry.resolve(ctx))
    return result


# ---------------------------------------------------------------------------
# Pomocnicze funkcje formatujące (używane przez builder i rozszerzenia)
# ---------------------------------------------------------------------------

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
    'M': {'pos': 'uzyskał',   'par': 'uzyskał częściowo',   'neg': 'nie uzyskał'},
    'F': {'pos': 'uzyskała',  'par': 'uzyskała częściowo',  'neg': 'nie uzyskała'},
}
_GENDER_FORMS_DEFAULT = {'pos': 'uzyskał/a', 'par': 'uzyskał/a częściowo', 'neg': 'nie uzyskał/a'}


# ---------------------------------------------------------------------------
# Registry rozszerzeń kontekstu per typ dokumentu
# ---------------------------------------------------------------------------

# Każda funkcja przyjmuje (ctx, zapis) i mutuje ctx in-place.
_CTX_EXT: dict[str, Callable[[dict, object], None]] = {}


def _ext(*doc_types: str):
    """Dekorator rejestrujący funkcję rozszerzenia dla podanych typów dokumentu."""
    def decorator(fn: Callable) -> Callable:
        for t in doc_types:
            _CTX_EXT[t] = fn
        return fn
    return decorator


@_ext('ZAL_2A')
def _ext_zal2a(ctx: dict, zapis) -> None:
    from core.modele import InternshipSchedule
    harmonogramy = (
        db.session.query(InternshipSchedule)
        .filter_by(enrollment_id=zapis.id)
        .order_by(InternshipSchedule.learning_outcome_id)
        .all()
    )
    ctx['harmonogram'] = [
        {
            'efekt_kod':  _g(h.efekt, 'kod') if h.efekt else str(h.learning_outcome_id).zfill(2),
            'efekt_opis': _g(h.efekt, 'opis') if h.efekt else '',
            'dzial':      _g(h, 'department_name', ''),
            'prace':      _g(h, 'example_tasks', ''),
            'dni':        _g(h, 'days_count', 0),
        }
        for h in harmonogramy
    ]


@_ext('ZAL_6')
def _ext_zal6(ctx: dict, zapis) -> None:
    from core.modele.dziennik import JournalEntry
    wpisy = (
        db.session.query(JournalEntry)
        .filter_by(enrollment_id=zapis.id)
        .order_by(JournalEntry.entry_date)
        .all()
    )
    ctx.update({
        'sciezka':          zapis.track_type.value if zapis.track_type else 'STANDARD',
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
    spr = getattr(zapis, 'sprawozdanie', None)
    ctx.update({
        'charakterystyka_miejsca': _g(spr, 'charakterystyka_miejsca') if spr else '',
        'opis_prac':               _g(spr, 'opis_i_analiza')          if spr else '',
        'wiedza':                  _g(spr, 'wiedza')                  if spr else '',
    })


@_ext('ZAL_3C')
def _ext_zal3c(ctx: dict, zapis) -> None:
    fg = zapis.final_grades
    ctx.update({
        'ocena_uopz':         str(fg.supervisor_grade) if fg and fg.supervisor_grade else '',
        'ocena_opisowa_uopz': fg.supervisor_grade_description if fg else '',
        'ocena_sprawozdania': str(fg.report_grade) if fg and fg.report_grade else '',
    })


@_ext('ZAL_4')
def _ext_zal4(ctx: dict, zapis) -> None:
    from core.modele import LearningOutcome
    oceny_map        = {o.learning_outcome_id: o for o in (getattr(zapis, 'oceny', None) or [])}
    wszystkie_efekty = db.session.query(LearningOutcome).order_by(LearningOutcome.id).all()

    def _wynik_str(e):
        if e.id not in oceny_map:
            return None
        w = oceny_map[e.id].wynik
        return w.value if w else None

    ctx.update({
        'oceny': [
            {
                'efekt': {'id': e.id, 'opis': _g(e, 'opis') or _g(e, 'description', ''), 'kod': _g(e, 'kod', '')},
                'wynik': _wynik_str(e),
            }
            for e in wszystkie_efekty
        ],
        'uwagi_uopz': _g(zapis, 'supervisor_grade_description', ''),
    })


@_ext('ZAL_4B')
def _ext_zal4b(ctx: dict, zapis) -> None:
    ctx['decyzja_dyrektora'] = zapis.dean_decision or ''


@_ext('ZAL_4A', 'ZAL_4a')
def _ext_zal4a(ctx: dict, zapis) -> None:
    from core.modele import LearningOutcome, CommitteeOutcomeEvaluation
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
    ctx['komentarz_komisji'] = zapis.komentarze_komisji or ''


@_ext('ZAL_8')
def _ext_zal8(ctx: dict, zapis) -> None:
    fg   = zapis.final_grades
    sw   = zapis.examination
    uopz = zapis.uopz

    def _f(v):
        return float(v) if v is not None else None

    ctx['zapis'].update({
        'firma_nazwa':            ctx['firma']['nazwa'],
        'termin_od':              _fmt(zapis.start_date),
        'termin_do':              _fmt(zapis.end_date),
        'ocena_sprawozdania':     _f(fg.report_grade)     if fg else None,
        'ocena_uopz':             _f(fg.supervisor_grade) if fg else None,
        'ocena_zopz':             _f(fg.workplace_grade)  if fg else None,
        'sprawdzian_pytanie_1':   sw.question_1           if sw else None,
        'sprawdzian_ocena_1':     _f(sw.grade_1)          if sw else None,
        'sprawdzian_pytanie_2':   sw.question_2           if sw else None,
        'sprawdzian_ocena_2':     _f(sw.grade_2)          if sw else None,
        'sprawdzian_pytanie_3':   sw.question_3           if sw else None,
        'sprawdzian_ocena_3':     _f(sw.grade_3)          if sw else None,
        'uopz':                   {'first_name': uopz.first_name, 'last_name': uopz.last_name} if uopz else None,
        'komisja_przewodniczacy': sw.commission_chair     if sw else None,
        'komisja_czlonek_2':      sw.commission_member_2  if sw else None,
        'komisja_czlonek_3':      sw.commission_member_3  if sw else None,
    })
    ctx['data_egzaminu'] = date.today().strftime('%d.%m.%Y')


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Context sub-builders (reduce cognitive complexity of buduj_kontekst)
# ---------------------------------------------------------------------------

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
        'specjalnosc':  _g(s, 'specialization', ''),
        'tryb_studiow': _STUDY_MODE_MAP.get(_g(s, 'study_mode', '').lower(), _g(s, 'study_mode', '')),
    }


def _ctx_firma(zapis, dm) -> tuple[dict, str, str, str]:
    f = zapis.firma
    nazwa  = (_g(f, 'name')     if f else None) or (dm.company_name    if dm else None) or ''
    adres  = (_g(f, 'address')  if f else None) or (dm.company_address if dm else None) or ''
    zip_   = (_g(f, 'zip_code') if f else None) or (dm.company_zip     if dm else None) or ''
    city   = (_g(f, 'city')     if f else None) or (dm.company_city    if dm else None) or ''
    nip    = (_g(f, 'tax_id')   if f else None) or (dm.company_tax_id  if dm else None) or ''
    miasto = f"{zip_} {city}".strip() if zip_ else city
    return {
        'nazwa': nazwa, 'adres': adres, 'miasto': miasto, 'nip_krs': nip,
        'name':  nazwa, 'address': adres, 'city': miasto,
    }, nazwa, adres, miasto


# Kanoniczny builder kontekstu TeX
# ---------------------------------------------------------------------------

def buduj_kontekst(zapis, typ: str) -> dict:
    """Buduje słownik kontekstu dla szablonu TeX danego typu dokumentu."""
    s    = zapis.student
    p    = zapis.internship
    uopz = zapis.uopz
    dm   = zapis.workplace_details

    firma_dict, firma_nazwa, firma_adres, firma_miasto = _ctx_firma(zapis, dm)

    ctx: dict = {
        'student': _ctx_student(s),
        'praktyka': {
            'rok_uczelniany': _g(p, 'academic_year')       if p else '',
            'semestr':        _g(p, 'semester')             if p else '',
            'wymiar_godzin':  _g(p, 'required_hours', 160) if p else 160,
        },
        'firma': firma_dict,
        'terminy': {
            'od': _fmt(zapis.start_date),
            'do': _fmt(zapis.end_date),
        },
        'zopz': {
            'imie_nazwisko': dm.workplace_mentor_name     if dm else '',
            'stanowisko':    dm.workplace_mentor_position if dm else '',
            'telefon':       dm.workplace_mentor_phone    if dm else '',
            'email':         dm.workplace_mentor_email    if dm else '',
        },
        'uopz': {
            'first_name':    _g(uopz, 'first_name') if uopz else '',
            'last_name':     _g(uopz, 'last_name')  if uopz else '',
            'imie_nazwisko': f"{uopz.first_name} {uopz.last_name}" if uopz else '',
        },
        'firma_upowazniony':            dm.authorized_person          if dm else '',
        'firma_upowazniony_stanowisko': dm.authorized_person_position if dm else '',
        'uzasadnienie':   zapis.path_justification.justification if zapis.path_justification else '',
        'specjalnosc':    _g(s, 'specialization', '') if s else '',
        'lacznie_godzin': _g(zapis, 'total_hours_logged', 0),
        'data_wniosku':   '',
        'zapis': {
            'sciezka':      zapis.track_type.value if zapis.track_type else 'STANDARD',
            'firma_nazwa':  firma_nazwa,
            'firma_adres':  firma_adres,
            'firma_miasto': firma_miasto,
        },
    }

    ext = _CTX_EXT.get(typ)
    if ext:
        ext(ctx, zapis)
    return ctx


# ---------------------------------------------------------------------------
# Walidacja kompletności danych przed generowaniem dokumentu
# ---------------------------------------------------------------------------

def waliduj_kompletnosc(zapis, doc_type: str) -> list[str]:
    """Zwraca listę brakujących pól wymaganych dla danego dokumentu."""
    missing = []
    if not (getattr(zapis, 'firma_nazwa', None) or (zapis.firma and zapis.firma.name)):
        missing.append('Nazwa firmy')
    if not (getattr(zapis, 'firma_adres', None) or (zapis.firma and zapis.firma.address)):
        missing.append('Adres firmy')
    if doc_type == 'ZAL_6' and not getattr(zapis, 'wpisy_dziennika', None):
        missing.append('Brak wpisów w dzienniku')
    return missing


# ---------------------------------------------------------------------------
# Generator SSE dla statusu generowania PDF
# ---------------------------------------------------------------------------

def sse_pdf_status(task_id: str, download_url: str, celery_app, max_seconds: int = 30):
    """Generator SSE — zwraca kolejne zdarzenia statusu zadania Celery jako tekst SSE."""
    import json
    import time
    import logging

    try:
        from gevent import sleep as _sleep
    except ImportError:
        from time import sleep as _sleep  # type: ignore[assignment]

    _log     = logging.getLogger(__name__)
    deadline = time.monotonic() + max_seconds

    while time.monotonic() < deadline:
        try:
            task = celery_app.AsyncResult(task_id)
            if task.state == 'SUCCESS':
                res = task.result
                if isinstance(res, dict) and res.get('status') == 'error':
                    data = {'status': 'FAILURE', 'error': res.get('message', 'Nieznany błąd')}
                else:
                    data = {'status': 'SUCCESS', 'download_url': download_url}
                yield f"data: {json.dumps(data)}\n\n"
                return
            elif task.state == 'FAILURE':
                yield f"data: {json.dumps({'status': 'FAILURE', 'error': str(task.info)})}\n\n"
                return
            else:
                yield f"data: {json.dumps({'status': task.state})}\n\n"
        except GeneratorExit:
            return
        except Exception as exc:
            _log.error("SSE stream error for task %s: %s", task_id, exc)
            yield f"data: {json.dumps({'status': 'FAILURE', 'error': str(exc)})}\n\n"
            return
        _sleep(1)

    yield f"data: {json.dumps({'status': 'TIMEOUT'})}\n\n"
