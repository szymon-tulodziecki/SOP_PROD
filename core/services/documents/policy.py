"""Polityka dostępności dokumentów i konfiguracja szablonów.

Określa, które dokumenty są dostępne dla studenta na podstawie stanu zapisu
(ścieżka, status, harmonogram, egzamin i oceny).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from core.extensions import db


# ── Konfiguracja szablonów ────────────────────────────────────────────────────

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


# ── Obiekty specyfikacji ─────────────────────────────────────────────────────

@dataclass
class DocumentEntry:
    """Deklaracja jednego dokumentu wraz z zasadami dostępności."""
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


# ── Zasady dostępności ────────────────────────────────────────────────────────

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
    return ctx['dyrektor_zatwierdził'] or ctx['zakonczona']


def _po_egzaminie(ctx: dict) -> bool:
    return ctx.get('po_egzaminie', False)


def _powod_harmonogram(_ctx: dict) -> str:
    return 'Wymaga wypełnionego harmonogramu'


def _powod_w_trakcie(_ctx: dict) -> str:
    return 'Dostępny po zatwierdzeniu praktyki'


def _powod_zakonczona(_ctx: dict) -> str:
    return 'Dostępny po zakończeniu praktyki'


def _powod_oceniona(_ctx: dict) -> str:
    return 'Dostępny po wystawieniu oceny przez UOPZ'


def _powod_egzamin(_ctx: dict) -> str:
    return 'Dostępny po egzaminie komisyjnym'


def _powod_dyrektor(_ctx: dict) -> str:
    return 'Dostępny po decyzji dyrektora'


# ─── Listy dokumentów dla ścieżek ───────────────────────────────────────────────────

def _docs_standard() -> list:
    return [
        _sep('Dokumenty startowe'),
        DocumentEntry('Zał. 9 — Oświadczenie instytucji', 'ZAL_9',
                      'Do wypełnienia przez zakład pracy',
                      available_when=_firma_custom),
        DocumentEntry('Zał. 1 — Porozumienie uczelnia ↔ zakład', 'ZAL_1',
                      'Dla firm bez stałej umowy z ANS',
                      available_when=_firma_bez_umowy),
        DocumentEntry('Zał. 2 — Program praktyki', 'ZAL_2',
                      'Z danymi studenta i firmy'),
        DocumentEntry('Zał. 2a — Indywidualny Program Praktyk', 'ZAL_2A',
                      'Harmonogram efektów uczenia się — student + UOPZ + ZOPZ',
                      available_when=_ma_harmonogram,
                      unavailable_reason=_powod_harmonogram),
        _sep('Załącznik nr 3 — Karta Praktyki Zawodowej'),
        DocumentEntry('Zał. 3a — Skierowanie na praktykę', 'ZAL_3A',
                      'Przepustka do firmy — drukujesz i przynosisz pierwszego dnia'),
        _sep('W trakcie praktyki'),
        DocumentEntry('Zał. 3b — Karta zakładowa (druk do wypełnienia)', 'ZAL_3B',
                      'Zakład pracy wypełnia i podpisuje przez 6 miesięcy'),
        DocumentEntry('Zał. 6 — Dziennik praktyki', 'ZAL_6',
                      'Generowany z wpisów dziennika',
                      available_when=_w_trakcie_lub_zakonczona,
                      unavailable_reason=_powod_w_trakcie),
        _sep('Dostępne po zakończeniu praktyki'),
        DocumentEntry('Zał. 4 — Potwierdzenie efektów uczenia się', 'ZAL_4',
                      'Podpisuje ZOPZ + UOPZ',
                      available_when=_oceniona,
                      unavailable_reason=_powod_oceniona),
        DocumentEntry('Zał. 7 — Sprawozdanie końcowe', 'ZAL_7',
                      'Podpisuje student',
                      available_when=_zakonczona,
                      unavailable_reason=_powod_zakonczona),
        _sep('Rozliczenie na uczelni'),
        DocumentEntry('Zał. 5 — Ankieta oceny praktyki', static_key='ankieta',
                      description='Formularz anonimowej ankiety'),
        DocumentEntry('Zał. 3c — Ocena uczelniana (UOPZ)', 'ZAL_3C',
                      'Ocena UOPZ + ocena sprawozdania',
                      available_when=_oceniona,
                      unavailable_reason=_powod_oceniona),
        DocumentEntry('Zał. 8 — Protokół egzaminu komisji', 'ZAL_8',
                      'Sporządzany przez Komisję po ustnym egzaminie z praktyki',
                      available_when=_po_egzaminie,
                      unavailable_reason=_powod_egzamin),
    ]


def _docs_employment_own_business() -> list:
    return [
        DocumentEntry('Zał. 4b — Wniosek o zaliczenie', 'ZAL_4B',
                      'Praca etatowa / własna działalność'),
        DocumentEntry('Zał. 7a — Sprawozdanie z pracy/działalności', 'ZAL_7A',
                      'Zatwierdza przełożony/UOPZ',
                      available_when=_w_trakcie_lub_zakonczona,
                      unavailable_reason=_powod_w_trakcie),
        DocumentEntry('Zał. 4a — Potwierdzenie efektów uczenia się (komisja)', 'ZAL_4A',
                      '13 efektów: uzyskał / częściowo / nie',
                      available_when=_dyrektor_lub_zakonczona,
                      unavailable_reason=_powod_dyrektor),
        _sep('Po egzaminie komisji'),
        DocumentEntry('Zał. 5 — Ankieta', static_key='ankieta'),
        DocumentEntry('Zał. 8 — Protokół egzaminu komisji', 'ZAL_8',
                      available_when=_po_egzaminie,
                      unavailable_reason=_powod_egzamin),
    ]


_DOCUMENT_POLICY: dict[str, Callable[[], list]] = {
    'STANDARD':     _docs_standard,
    'EMPLOYMENT':   _docs_employment_own_business,
    'OWN_BUSINESS': _docs_employment_own_business,
}


# ─── Publiczne API ──────────────────────────────────────────────────────────────────

def build_flags(zapis) -> dict:
    """Wylicza flagi stanu zapisu używane przez politykę dostępności."""
    from core.models import EnrollmentStatus, InternshipSchedule

    w_trakcie  = zapis.status == EnrollmentStatus.IN_PROGRESS
    zakonczona = zapis.status == EnrollmentStatus.COMPLETED
    return {
        'enrollment_id':            str(zapis.id),
        'w_trakcie':           w_trakcie,
        'zakonczona':          zakonczona,
        'oceniona':            zakonczona and (zapis.final_grades and zapis.final_grades.supervisor_grade) is not None,
        'dyrektor_zatwierdził': w_trakcie or zakonczona,
        'po_egzaminie':        zapis.final_grade is not None,
        'harmonogram_count':   db.session.execute(
                                 db.select(db.func.count()).select_from(InternshipSchedule).filter_by(enrollment_id=zapis.id)
                               ).scalar(),
        'firma_bez_umowy':     not zapis.company or not zapis.company.has_standing_agreement,
        'firma_custom':        not zapis.company_id,
    }


def resolve_documents(zapis) -> list[dict]:
    """Zwraca listę dokumentów dostępnych dla zapisu zgodnie z polityką ścieżki."""
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
