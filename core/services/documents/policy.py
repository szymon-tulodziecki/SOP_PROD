"""Document availability policy and template configuration.

Determines which documents are available to a student based on enrollment
state (path type, status, schedule, exam, grades).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from core.extensions import db


# â”€â”€ Template configuration â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

DOC_CONFIG: dict[str, tuple[str, str]] = {
    'ZAL_1':  ('zal1_porozumienie.tex.j2',     'zal1_porozumienie.pdf'),
    'ZAL_2':  ('zal2_program.tex.j2',          'zal2_program.pdf'),
    'ZAL_2A': ('zal2a_program.tex.j2',         'zal2a_program.pdf'),
    'ZAL_3A': ('zal3a_skierowanie.tex.j2',     'zal3a_skierowanie.pdf'),
    'ZAL_3B': ('zal3b_karta_zakladowa.tex.j2', 'zal3b_karta_zakladowa.pdf'),
    'ZAL_3C': ('zal3c_suplement_uopz.tex.j2',  'zal3c_suplement_uopz.pdf'),
    'ZAL_4':  ('zal4_efekty.tex.j2',           'zal4_efekty.pdf'),
    'ZAL_4A': ('zal4a_komisja.tex.j2',         'zal4a_komisja.pdf'),
    'ZAL_4B': ('zal4b_wniosek.tex.j2',         'zal4b_wniosek.pdf'),
    'ZAL_6':  ('zal6_dziennik.tex.j2',         'zal6_dziennik.pdf'),
    'ZAL_7':  ('zal7_sprawozdanie.tex.j2',     'zal7_sprawozdanie.pdf'),
    'ZAL_7A': ('zal7a_sprawozdanie.tex.j2',    'zal7a_sprawozdanie.pdf'),
    'ZAL_8':  ('zal8_protokol.tex.j2',         'zal8_protokol.pdf'),
    'ZAL_9':  ('zal9_oswiadczenie.tex.j2',     'zal9_oswiadczenie.pdf'),
}

STATIC_TEMPLATES: dict[str, tuple[str, str]] = {
    'ankieta': ('zal5_ankieta.tex.j2', 'zal5_ankieta.pdf'),
}


# â”€â”€ Specification objects â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class DocumentEntry:
    """Declaration of one document with its availability rules."""
    name: str
    doc_type: str | None = None
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
            entry.update({'dynamiczny': True, 'event_type': self.doc_type,
                          'enrollment_id': ctx['enrollment_id']})
        return entry


def _sep(name: str) -> dict:
    return {'separator': True, 'name': name}


# â”€â”€ Availability rules â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _zawsze(_ctx: dict) -> bool:
    return True


def _w_trakcie_lub_zakonczona(ctx: dict) -> bool:
    return ctx['w_trakcie'] or ctx['zakonczona']


def _zakonczona(ctx: dict) -> bool:
    return ctx['zakonczona']


def _oceniona(ctx: dict) -> bool:
    return ctx['oceniona']


def _ma_harmonogram(ctx: dict) -> bool:
    return ctx['harmonogram_count'] > 0


def _firma_custom(ctx: dict) -> bool:
    return ctx['firma_custom']


def _firma_bez_umowy(ctx: dict) -> bool:
    return ctx['firma_bez_umowy']


def _dyrektor_lub_zakonczona(ctx: dict) -> bool:
    return ctx['dyrektor_zatwierdziĹ‚'] or ctx['zakonczona']


def _po_egzaminie(ctx: dict) -> bool:
    return ctx.get('po_egzaminie', False)


def _powod_harmonogram(_ctx: dict) -> str:
    return 'Wymaga wypeĹ‚nionego harmonogramu'


def _powod_w_trakcie(_ctx: dict) -> str:
    return 'DostÄ™pny po zatwierdzeniu praktyki'


def _powod_zakonczona(_ctx: dict) -> str:
    return 'DostÄ™pny po zakoĹ„czeniu praktyki'


def _powod_oceniona(_ctx: dict) -> str:
    return 'DostÄ™pny po wystawieniu assessments przez UOPZ'


def _powod_egzamin(_ctx: dict) -> str:
    return 'DostÄ™pny po egzaminie komisyjnym'


def _powod_dyrektor(_ctx: dict) -> str:
    return 'DostÄ™pny po decyzji dyrektora'


# â”€â”€ Document lists per path â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _docs_standard() -> list:
    return [
        _sep('Dokumenty startowe'),
        DocumentEntry('ZaĹ‚. 9 â€“ OĹ›wiadczenie instytucji', 'ZAL_9',
                      'Do wypeĹ‚nienia przez zakĹ‚ad pracy',
                      available_when=_firma_custom),
        DocumentEntry('ZaĹ‚. 1 â€“ Porozumienie uczelnia â†” zakĹ‚ad', 'ZAL_1',
                      'Dla firm bez staĹ‚ej umowy z ANS',
                      available_when=_firma_bez_umowy),
        DocumentEntry('ZaĹ‚. 2 â€“ Program praktyki', 'ZAL_2',
                      'Z danymi studenta i firmy'),
        DocumentEntry('ZaĹ‚. 2a â€“ Indywidualny Program Praktyk', 'ZAL_2A',
                      'Harmonogram learning_outcomeĂłw â€” student + UOPZ + ZOPZ',
                      available_when=_ma_harmonogram,
                      unavailable_reason=_powod_harmonogram),
        _sep('ZaĹ‚Ä…cznik nr 3 â€” Karta Praktyki Zawodowej'),
        DocumentEntry('ZaĹ‚. 3a â€“ Skierowanie na praktykÄ™', 'ZAL_3A',
                      'Przepustka do firmy â€” drukujesz i przynosisz pierwszego dnia'),
        _sep('W trakcie praktyki'),
        DocumentEntry('ZaĹ‚. 3b â€“ Karta zakĹ‚adowa (druk do wypeĹ‚nienia)', 'ZAL_3B',
                      'ZakĹ‚ad pracy wypeĹ‚nia i podpisuje przez 6 miesiÄ™cy'),
        DocumentEntry('ZaĹ‚. 6 â€“ Dziennik praktyki', 'ZAL_6',
                      'Generowany z wpisĂłw dziennika',
                      available_when=_w_trakcie_lub_zakonczona,
                      unavailable_reason=_powod_w_trakcie),
        _sep('DostÄ™pne po zakoĹ„czeniu praktyki'),
        DocumentEntry('ZaĹ‚. 4 â€“ Potwierdzenie learning_outcomeĂłw uczenia siÄ™', 'ZAL_4',
                      'Podpisuje ZOPZ + UOPZ',
                      available_when=_oceniona,
                      unavailable_reason=_powod_oceniona),
        DocumentEntry('ZaĹ‚. 7 â€“ Sprawozdanie koĹ„cowe', 'ZAL_7',
                      'Podpisuje student',
                      available_when=_zakonczona,
                      unavailable_reason=_powod_zakonczona),
        _sep('Rozliczenie na uczelni'),
        DocumentEntry('ZaĹ‚. 5 â€“ Ankieta assessments praktyki', static_key='ankieta',
                      description='Formularz anonimowej ankiety'),
        DocumentEntry('ZaĹ‚. 3c â€“ Ocena uczelniana (UOPZ)', 'ZAL_3C',
                      'Ocena UOPZ + ocena sprawozdania',
                      available_when=_oceniona,
                      unavailable_reason=_powod_oceniona),
        DocumentEntry('ZaĹ‚. 8 â€“ ProtokĂłĹ‚ egzaminu komisji', 'ZAL_8',
                      'SporzÄ…dzany przez KomisjÄ™ po ustnym egzaminie z praktyki',
                      available_when=_po_egzaminie,
                      unavailable_reason=_powod_egzamin),
    ]


def _docs_employment_own_business() -> list:
    return [
        DocumentEntry('ZaĹ‚. 4b â€“ Wniosek o zaliczenie', 'ZAL_4B',
                      'Praca etatowa / wĹ‚asna dziaĹ‚alnoĹ›Ä‡'),
        DocumentEntry('ZaĹ‚. 7a â€“ Sprawozdanie z pracy/dziaĹ‚alnoĹ›ci', 'ZAL_7A',
                      'Zatwierdza przeĹ‚oĹĽony/UOPZ',
                      available_when=_w_trakcie_lub_zakonczona,
                      unavailable_reason=_powod_w_trakcie),
        DocumentEntry('ZaĹ‚. 4a â€“ Potwierdzenie learning_outcomeĂłw (komisja)', 'ZAL_4A',
                      '13 learning_outcomeĂłw: uzyskaĹ‚ / czÄ™Ĺ›ciowo / nie',
                      available_when=_dyrektor_lub_zakonczona,
                      unavailable_reason=_powod_dyrektor),
        _sep('Po egzaminie komisji'),
        DocumentEntry('ZaĹ‚. 5 â€“ Ankieta', static_key='ankieta'),
        DocumentEntry('ZaĹ‚. 8 â€“ ProtokĂłĹ‚ egzaminu komisji', 'ZAL_8',
                      available_when=_po_egzaminie,
                      unavailable_reason=_powod_egzamin),
    ]


_DOCUMENT_POLICY: dict[str, Callable[[], list]] = {
    'STANDARD':     _docs_standard,
    'EMPLOYMENT':   _docs_employment_own_business,
    'OWN_BUSINESS': _docs_employment_own_business,
}


# â”€â”€ Public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def build_flags(zapis) -> dict:
    """Computes enrollment-state flags consumed by the availability policy."""
    from core.models import EnrollmentStatus, InternshipSchedule

    w_trakcie  = zapis.status == EnrollmentStatus.IN_PROGRESS
    zakonczona = zapis.status == EnrollmentStatus.COMPLETED
    return {
        'enrollment_id':            str(zapis.id),
        'w_trakcie':           w_trakcie,
        'zakonczona':          zakonczona,
        'oceniona':            zakonczona and (zapis.final_grades and zapis.final_grades.supervisor_grade) is not None,
        'dyrektor_zatwierdziĹ‚': w_trakcie or zakonczona,
        'po_egzaminie':        zapis.final_grade is not None,
        'harmonogram_count':   db.session.execute(
                                 db.select(db.func.count()).select_from(InternshipSchedule).filter_by(enrollment_id=zapis.id)
                               ).scalar(),
        'firma_bez_umowy':     not zapis.company or not zapis.company.has_standing_agreement,
        'firma_custom':        not zapis.company_id,
    }


def resolve_documents(zapis) -> list[dict]:
    """Returns the list of documents available for an enrollment per its path policy."""
    path = zapis.track_type.value if zapis.track_type else 'STANDARD'
    factory = _DOCUMENT_POLICY.get(path, _docs_standard)
    ctx = build_flags(zapis)
    result = []
    for entry in factory():
        if isinstance(entry, dict):
            result.append(entry)
        else:
            result.append(entry.resolve(ctx))
    return result
