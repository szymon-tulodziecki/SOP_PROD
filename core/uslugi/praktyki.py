"""core/uslugi/praktyki.py

Usługa zarządzania praktykami i zapisami studentów.
"""
from __future__ import annotations

from typing import Optional
import uuid

from core.extensions import db
from core.modele.praktyki import (
    Praktyka,
    StatusPraktyki,
    ZapisPraktyki,
    StatusZapisu,
    SciezkaPraktyki,
    Sprawozdanie,
)
from core.repozytoria.praktyki import RepozytoriumPraktyk, RepozytoriumZapisow


class UslugaPraktyk:
    """Logika biznesowa edycji praktyk i procesowania zapisów."""

    def __init__(
        self,
        repo_praktyk: Optional[RepozytoriumPraktyk] = None,
        repo_zapisow: Optional[RepozytoriumZapisow] = None,
    ) -> None:
        self._praktyki = repo_praktyk or RepozytoriumPraktyk()
        self._zapisy  = repo_zapisow  or RepozytoriumZapisow()

    # ── Edycje praktyk ────────────────────────────────────────────────────────

    def utworz_edycje(self, rok_uczelniany: str, semestr: str, wymiar_godzin: int = 160) -> Praktyka:
        praktyka = Praktyka(
            rok_uczelniany=rok_uczelniany,
            semestr=semestr,
            wymiar_godzin=wymiar_godzin,
            status=StatusPraktyki.NIEAKTYWNA,
        )
        self._praktyki.zapisz(praktyka)
        db.session.commit()
        return praktyka

    def aktywuj_edycje(self, praktyka: Praktyka) -> None:
        praktyka.status = StatusPraktyki.AKTYWNA
        db.session.commit()

    def dezaktywuj_edycje(self, praktyka: Praktyka) -> None:
        praktyka.status = StatusPraktyki.NIEAKTYWNA
        db.session.commit()

    # ── Zapisy studentów ──────────────────────────────────────────────────────

    def zapisz_studenta(
        self,
        student_id: uuid.UUID,
        praktyka_id: uuid.UUID,
        sciezka: SciezkaPraktyki = SciezkaPraktyki.STANDARDOWA,
    ) -> ZapisPraktyki:
        if self._zapisy.student_ma_aktywny_zapis(student_id, praktyka_id):
            raise ValueError('Student ma już aktywne zgłoszenie do tej edycji praktyk.')
        zapis = ZapisPraktyki(
            student_id=student_id,
            praktyka_id=praktyka_id,
            sciezka=sciezka,
            status=StatusZapisu.OCZEKUJACY,
        )
        self._zapisy.zapisz(zapis)
        db.session.commit()
        return zapis

    def zmien_status(self, zapis: ZapisPraktyki, nowy_status: StatusZapisu, komentarz: Optional[str] = None) -> None:
        """Zmienia status zapisu z opcjonalnym komentarzem."""
        zapis.status = nowy_status
        if komentarz is not None:
            if nowy_status in (StatusZapisu.ODRZUCONA, StatusZapisu.OCZEKUJE_NA_AKCEPT):
                zapis.komentarze_admina = komentarz
            elif nowy_status == StatusZapisu.WERYFIKACJA_KOMISJI:
                zapis.komentarze_uopz = komentarz
        db.session.commit()

    def przypisz_opiekuna(self, zapis: ZapisPraktyki, uopz_id: uuid.UUID) -> None:
        zapis.uopz_id = uopz_id
        db.session.commit()

    def zatwierdz_przez_komisje(
        self,
        zapis: ZapisPraktyki,
        decyzja: str,
        komentarz: Optional[str] = None,
    ) -> None:
        from datetime import datetime
        zapis.decyzja_komisji   = decyzja
        zapis.komentarze_komisji = komentarz
        zapis.decyzja_komisji_o  = datetime.utcnow()
        if decyzja == 'APPROVED':
            zapis.status = StatusZapisu.AKCEPTACJA_DZIEKANA
        else:
            zapis.status = StatusZapisu.ODRZUCONA
        db.session.commit()

    def zatwierdz_przez_dziekana(
        self,
        zapis: ZapisPraktyki,
        decyzja: str,
        komentarz: Optional[str] = None,
    ) -> None:
        from datetime import datetime
        zapis.decyzja_dziekana   = decyzja
        zapis.komentarze_dziekana = komentarz
        zapis.decyzja_dziekana_o  = datetime.utcnow()
        if decyzja == 'APPROVED':
            zapis.status = StatusZapisu.W_REALIZACJI
        else:
            zapis.status = StatusZapisu.ODRZUCONA
        db.session.commit()

    def zakoncz(self, zapis: ZapisPraktyki) -> None:
        zapis.status = StatusZapisu.ZAKONCZONA
        db.session.commit()

    # ── Sprawozdania ──────────────────────────────────────────────────────────

    def pobierz_lub_utworz_sprawozdanie(self, zapis: ZapisPraktyki) -> Sprawozdanie:
        if zapis.sprawozdanie is None:
            sprawozdanie = Sprawozdanie(zapis_id=zapis.id)
            db.session.add(sprawozdanie)
            db.session.flush()
            return sprawozdanie
        return zapis.sprawozdanie

    # ── Dostęp do repozytoriów ────────────────────────────────────────────────

    @property
    def praktyki(self) -> RepozytoriumPraktyk:
        return self._praktyki

    @property
    def zapisy(self) -> RepozytoriumZapisow:
        return self._zapisy
