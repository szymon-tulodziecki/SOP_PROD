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
    'ZAL_3':  ('zal3_karta.tex.j2',          'zal3_karta.pdf'),
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
            'nazwa':    self.name,
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
    return {'separator': True, 'nazwa': name}


# Reguły dostępności — czytelne funkcje zamiast anonimowych lambdy
def _zawsze(ctx: dict) -> bool:           return True                                         # noqa: E704
def _w_trakcie_lub_zakonczona(ctx):       return ctx['w_trakcie'] or ctx['zakonczona']        # noqa: E704
def _zakonczona(ctx):                     return ctx['zakonczona']                            # noqa: E704
def _oceniona(ctx):                       return ctx['oceniona']                              # noqa: E704
def _ma_harmonogram(ctx):                 return ctx['harmonogram_count'] > 0                 # noqa: E704
def _firma_custom(ctx):                   return ctx['firma_custom']                          # noqa: E704
def _firma_bez_umowy(ctx):                return ctx['firma_bez_umowy']                       # noqa: E704
def _dziekan_lub_zakonczona(ctx):         return ctx['dziekan_zatwierdził'] or ctx['zakonczona']  # noqa: E704

_POWOD_HARMONOGRAM    = lambda _: 'Wymaga wypełnionego harmonogramu'            # noqa: E731
_POWOD_W_TRAKCIE      = lambda _: 'Dostępny po zatwierdzeniu praktyki'          # noqa: E731
_POWOD_ZAKONCZONA     = lambda _: 'Dostępny po zakończeniu praktyki'            # noqa: E731
_POWOD_OCENIONA       = lambda _: 'Dostępny po wystawieniu oceny przez UOPZ'   # noqa: E731
_POWOD_DZIEKAN        = lambda _: 'Dostępny po decyzji dziekana'                # noqa: E731


def _docs_standard() -> list:
    return [
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
        DocumentEntry('Zał. 3 – Karta praktyki / Skierowanie', 'ZAL_3',
                      'Z danymi studenta, firmy i ZOPZ'),
        DocumentEntry('Zał. 6 – Dziennik praktyki', 'ZAL_6',
                      'Generowany z wpisów dziennika',
                      available_when=_w_trakcie_lub_zakonczona,
                      unavailable_reason=_POWOD_W_TRAKCIE),
        _sep('Pakiet końcowy'),
        DocumentEntry('Zał. 7 – Sprawozdanie końcowe', 'ZAL_7',
                      'Podpisuje student',
                      available_when=_zakonczona,
                      unavailable_reason=_POWOD_ZAKONCZONA),
        DocumentEntry('Zał. 4 – Potwierdzenie efektów uczenia się', 'ZAL_4',
                      'Podpisuje ZOPZ + UOPZ',
                      available_when=_zakonczona,
                      unavailable_reason=_POWOD_ZAKONCZONA),
        _sep('Po egzaminie komisji'),
        DocumentEntry('Zał. 8 – Protokół egzaminu komisji', 'ZAL_8',
                      available_when=_oceniona,
                      unavailable_reason=_POWOD_OCENIONA),
        DocumentEntry('Zał. 5 – Ankieta oceny praktyki', static_key='ankieta',
                      description='Formularz anonimowej ankiety'),
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
                      available_when=_dziekan_lub_zakonczona,
                      unavailable_reason=_POWOD_DZIEKAN),
    ]


_DOCUMENT_POLICY: dict[str, Callable[[], list]] = {
    'STANDARD':     _docs_standard,
    'EMPLOYMENT':   _docs_employment_own_business,
    'OWN_BUSINESS': _docs_employment_own_business,
}


def buduj_flagi(zapis) -> dict:
    """Oblicza flagi stanu zapisu używane przez politykę dostępności.

    Jedno miejsce w domenie — nie duplikujemy w kontrolerach.
    """
    from core.modele import EnrollmentStatus, InternshipSchedule

    w_trakcie  = zapis.status == EnrollmentStatus.IN_PROGRESS
    zakonczona = zapis.status == EnrollmentStatus.COMPLETED
    return {
        'zapis_id':            str(zapis.id),
        'w_trakcie':           w_trakcie,
        'zakonczona':          zakonczona,
        'oceniona':            zakonczona and (zapis.final_grades and zapis.final_grades.supervisor_grade) is not None,
        'dziekan_zatwierdził': w_trakcie or zakonczona,
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
# Kanoniczny builder kontekstu TeX
# ---------------------------------------------------------------------------

def _fmt(value) -> str:
    """Formatuje datę jako DD.MM.YYYY lub zwraca pusty string."""
    if value is None:
        return ''
    if isinstance(value, (date, datetime)):
        return value.strftime('%d.%m.%Y')
    return str(value)


def _iso(value) -> str:
    """Formatuje datę jako ISO 8601 lub zwraca pusty string."""
    if value is None:
        return ''
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _g(obj, attr: str, default=''):
    """Bezpieczny getter — zwraca default gdy atrybut nie istnieje lub jest None."""
    val = getattr(obj, attr, default)
    return val if val is not None else default


def buduj_kontekst(zapis, typ: str) -> dict:
    """Buduje słownik kontekstu dla szablonu TeX danego typu dokumentu.

    Jedyna implementacja w całej aplikacji — używana przez:
      • app_admin/routes/zarzadzanie/dokumenty_studentow.py
      • app_student/routes/dokumenty.py
      • celery_app.py (generate_pdf_dziennik)

    Args:
        zapis: instancja ZapisPraktyki (z załadowanymi relacjami)
        typ:   klucz z DOC_CONFIG, np. 'ZAL_6'

    Returns:
        Słownik gotowy do serializacji JSON i przekazania do tex-service.
    """
    from core.modele.dziennik import JournalEntry
    from core.modele import InternshipSchedule

    s    = zapis.student
    p    = zapis.internship
    uopz = zapis.uopz

    dm = zapis.workplace_details
    firma_nazwa  = (_g(zapis.firma, 'name')    if zapis.firma else None) or (dm.company_name    if dm else None) or ''
    firma_adres  = (_g(zapis.firma, 'address') if zapis.firma else None) or (dm.company_address if dm else None) or ''
    firma_miasto = (_g(zapis.firma, 'city')    if zapis.firma else None) or (dm.company_city    if dm else None) or ''
    firma_nip    = (_g(zapis.firma, 'tax_id')  if zapis.firma else None) or (dm.company_tax_id  if dm else None) or ''

    ctx: dict = {
        'student': {
            'first_name':   _g(s, 'first_name'),
            'last_name':    _g(s, 'last_name'),
            'album_number': _g(s, 'album_number'),
            # Aliasy dla starszych szablonów
            'imie':         _g(s, 'first_name'),
            'nazwisko':     _g(s, 'last_name'),
            'nr_albumu':    _g(s, 'album_number'),
            'numer_albumu': _g(s, 'album_number'),
            'plec':         _g(s, 'gender', ''),
            'kierunek':     _g(s, 'field_of_study') or 'Informatyka',
            'specjalnosc':  _g(s, 'specialization', ''),
            'tryb_studiow': _g(s, 'study_mode', ''),
        },
        'praktyka': {
            'rok_uczelniany': _g(p, 'academic_year') if p else '',
            'semestr':        _g(p, 'semester')       if p else '',
            'wymiar_godzin':  _g(p, 'required_hours', 160) if p else 160,
        },
        'firma': {
            'nazwa':   firma_nazwa,
            'adres':   firma_adres,
            'miasto':  firma_miasto,
            'nip_krs': firma_nip,
            # Aliasy angielskie
            'name':    firma_nazwa,
            'address': firma_adres,
            'city':    firma_miasto,
        },
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
        'uzasadnienie':    zapis.path_justification.justification if zapis.path_justification else '',
        'specjalnosc':     _g(s, 'specialization', '') if s else '',
        'lacznie_godzin':  _g(zapis, 'total_hours_logged', 0),
        'data_wniosku':    '',
        # Aliasy dla szablonów odwołujących się do zapis.*
        'zapis': {
            'sciezka':    zapis.track_type.value if zapis.track_type else 'STANDARD',
            'firma_nazwa':  firma_nazwa,
            'firma_adres':  firma_adres,
            'firma_miasto': firma_miasto,
        },
    }

    # ── Rozszerzenia per typ dokumentu ────────────────────────────────────────

    if typ == 'ZAL_2A':
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
                'prace':      _g(h, 'sample_tasks', ''),
                'dni':        _g(h, 'days_count', 0),
            }
            for h in harmonogramy
        ]

    elif typ == 'ZAL_6':
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

    elif typ == 'ZAL_7':
        spr = getattr(zapis, 'sprawozdanie', None)
        ctx.update({
            'charakterystyka_miejsca': _g(spr, 'charakterystyka_miejsca') if spr else '',
            'opis_prac':               _g(spr, 'opis_i_analiza')          if spr else '',
            'efekty_opisy':            [''] * 13,
        })

    elif typ == 'ZAL_4':
        oceny = getattr(zapis, 'oceny', None) or []
        ctx.update({
            'oceny': [
                {
                    'efekt_id': o.learning_outcome_id,
                    'wynik':    o.result.value if o.result else 'uzyskał/a',
                    'uwagi':    _g(o, 'notes', ''),
                }
                for o in sorted(oceny, key=lambda x: x.learning_outcome_id)
            ],
            'uwagi_uopz': _g(zapis, 'supervisor_grade_description', ''),
        })

    return ctx
