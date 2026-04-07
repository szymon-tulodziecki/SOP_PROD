"""core/uslugi/praktyki.py

Usługa zarządzania praktykami i zapisami studentów.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from core.extensions import db
from core.modele.praktyki import (
    Praktyka,
    StatusPraktyki,
    ZapisPraktyki,
    StatusZapisu,
    SciezkaPraktyki,
    TypZdarzenia,
    ZdarzenieProces,
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
        self._zapisy   = repo_zapisow  or RepozytoriumZapisow()

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

    def zmien_status(
        self,
        zapis: ZapisPraktyki,
        nowy_status: StatusZapisu,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Zmienia status zapisu i opcjonalnie dodaje zdarzenie do logu."""
        zapis.status = nowy_status

        if komentarz is not None:
            if nowy_status in (StatusZapisu.ODRZUCONA, StatusZapisu.OCZEKUJE_NA_AKCEPT):
                typ = TypZdarzenia.ADMIN_KOMENTARZ
            elif nowy_status == StatusZapisu.WERYFIKACJA_KOMISJI:
                typ = TypZdarzenia.UOPZ_KOMENTARZ
            else:
                typ = TypZdarzenia.ADMIN_KOMENTARZ
            self._dodaj_zdarzenie(zapis, typ, komentarz=komentarz, wykonane_przez_id=wykonane_przez_id)

        db.session.commit()

    def przypisz_opiekuna(self, zapis: ZapisPraktyki, uopz_id: uuid.UUID) -> None:
        zapis.uopz_id = uopz_id
        db.session.commit()

    def zatwierdz_przez_komisje(
        self,
        zapis: ZapisPraktyki,
        decyzja: str,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> None:
        self._dodaj_zdarzenie(
            zapis, TypZdarzenia.KOMISJA_DECYZJA,
            decyzja=decyzja, komentarz=komentarz,
            wykonane_przez_id=wykonane_przez_id,
        )
        zapis.status = StatusZapisu.AKCEPTACJA_DZIEKANA if decyzja == 'APPROVED' else StatusZapisu.ODRZUCONA
        db.session.commit()

    def zatwierdz_przez_dziekana(
        self,
        zapis: ZapisPraktyki,
        decyzja: str,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> None:
        self._dodaj_zdarzenie(
            zapis, TypZdarzenia.DZIEKAN_DECYZJA,
            decyzja=decyzja, komentarz=komentarz,
            wykonane_przez_id=wykonane_przez_id,
        )
        zapis.status = StatusZapisu.W_REALIZACJI if decyzja == 'APPROVED' else StatusZapisu.ODRZUCONA
        db.session.commit()

    def powiadom_studenta(
        self,
        zapis: ZapisPraktyki,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> None:
        self._dodaj_zdarzenie(
            zapis, TypZdarzenia.POWIADOMIENIE_STUDENTA,
            komentarz=komentarz,
            wykonane_przez_id=wykonane_przez_id,
        )
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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _dodaj_zdarzenie(
        self,
        zapis: ZapisPraktyki,
        typ: TypZdarzenia,
        decyzja: Optional[str] = None,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> ZdarzenieProces:
        zdarzenie = ZdarzenieProces(
            zapis_id=zapis.id,
            typ=typ,
            decyzja=decyzja,
            komentarz=komentarz,
            wykonane_przez_id=wykonane_przez_id,
            wykonano_o=datetime.utcnow(),
        )
        db.session.add(zdarzenie)
        return zdarzenie

    # ── Dostęp do repozytoriów ────────────────────────────────────────────────

    @property
    def praktyki(self) -> RepozytoriumPraktyk:
        return self._praktyki

    @property
    def zapisy(self) -> RepozytoriumZapisow:
        return self._zapisy
