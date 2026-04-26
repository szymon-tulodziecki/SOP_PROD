"""core/uslugi/praktyki.py

Internship and enrollment management service.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from core.extensions import db
from core.modele.praktyki import (
    Internship,
    InternshipStatus,
    InternshipEnrollment,
    EnrollmentStatus,
    InternshipPath,
    EventType,
    ProcessEvent,
    InternshipReport,
)
from core.repozytoria.praktyki import RepozytoriumPraktyk, RepozytoriumZapisow


class UslugaPraktyk:
    """Business logic for internship editions and enrollment processing."""

    def __init__(
        self,
        repo_praktyk: Optional[RepozytoriumPraktyk] = None,
        repo_zapisow: Optional[RepozytoriumZapisow] = None,
    ) -> None:
        self._praktyki = repo_praktyk or RepozytoriumPraktyk()
        self._zapisy   = repo_zapisow  or RepozytoriumZapisow()

    # ── Internship editions ───────────────────────────────────────────────────

    def utworz_edycje(self, rok_uczelniany: str, semestr: str, wymiar_godzin: int = 160) -> Internship:
        praktyka = Internship(
            academic_year=rok_uczelniany,
            semester=semestr,
            required_hours=wymiar_godzin,
            status=InternshipStatus.INACTIVE,
        )
        self._praktyki.zapisz(praktyka)
        db.session.commit()
        return praktyka

    def aktywuj_edycje(self, praktyka: Internship) -> None:
        praktyka.status = InternshipStatus.ACTIVE
        db.session.commit()

    def dezaktywuj_edycje(self, praktyka: Internship) -> None:
        praktyka.status = InternshipStatus.INACTIVE
        db.session.commit()

    # ── Student enrollments ───────────────────────────────────────────────────

    def zapisz_studenta(
        self,
        student_id: uuid.UUID,
        praktyka_id: uuid.UUID,
        sciezka: InternshipPath = InternshipPath.STANDARD,
    ) -> InternshipEnrollment:
        if self._zapisy.student_ma_aktywny_zapis(student_id, praktyka_id):
            raise ValueError('Student ma już aktywne zgłoszenie do tej edycji praktyk.')
        zapis = InternshipEnrollment(
            student_id=student_id,
            internship_id=praktyka_id,
            path_type=sciezka,
            status=EnrollmentStatus.PENDING,
        )
        self._zapisy.zapisz(zapis)
        db.session.commit()
        return zapis

    def zmien_status(
        self,
        zapis: InternshipEnrollment,
        nowy_status: EnrollmentStatus,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Changes enrollment status via FSM public methods."""
        from core.uslugi.workflow import ZapisFSM, IllegalTransitionError
        fsm = ZapisFSM(zapis)
        _dispatch = {
            EnrollmentStatus.AWAITING_APPROVAL: fsm.wyslij_do_akceptacji,
            EnrollmentStatus.COMMISSION_REVIEW: fsm.wyslij_do_komisji,
            EnrollmentStatus.IN_PROGRESS:       fsm.zatwierdz_przez_uopz,
            EnrollmentStatus.DIRECTOR_APPROVAL:     fsm.zatwierdz_przez_komisje,
            EnrollmentStatus.COMPLETED:         fsm.zakoncz,
            EnrollmentStatus.REJECTED:          fsm.odrzuc,
        }
        method = _dispatch.get(nowy_status)
        if method is None:
            raise ValueError(f'Nieobsługiwany status docelowy: {nowy_status!r}')
        method()

        if komentarz is not None:
            if nowy_status in (EnrollmentStatus.REJECTED, EnrollmentStatus.AWAITING_APPROVAL):
                typ = EventType.ADMIN_COMMENT
            elif nowy_status == EnrollmentStatus.COMMISSION_REVIEW:
                typ = EventType.SUPERVISOR_COMMENT
            else:
                typ = EventType.ADMIN_COMMENT
            self._dodaj_zdarzenie(zapis, typ, komentarz=komentarz, wykonane_przez_id=wykonane_przez_id)

        db.session.commit()

    def przypisz_opiekuna(self, zapis: InternshipEnrollment, uopz_id: uuid.UUID) -> None:
        zapis.supervisor_id = uopz_id
        db.session.commit()

    def zatwierdz_przez_komisje(
        self,
        zapis: InternshipEnrollment,
        decyzja: str,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> None:
        from core.uslugi.workflow import ZapisFSM
        self._dodaj_zdarzenie(
            zapis, EventType.COMMITTEE_DECISION,
            decyzja=decyzja, komentarz=komentarz,
            wykonane_przez_id=wykonane_przez_id,
        )
        fsm = ZapisFSM(zapis)
        if decyzja == 'APPROVED':
            fsm.zatwierdz_przez_komisje()
        else:
            fsm.odrzuc()
        db.session.commit()

    def zatwierdz_przez_dyrektora(
        self,
        zapis: InternshipEnrollment,
        decyzja: str,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> None:
        from core.uslugi.workflow import ZapisFSM
        self._dodaj_zdarzenie(
            zapis, EventType.DIRECTOR_DECISION,
            decyzja=decyzja, komentarz=komentarz,
            wykonane_przez_id=wykonane_przez_id,
        )
        fsm = ZapisFSM(zapis)
        if decyzja == 'APPROVED':
            fsm.zatwierdz_przez_dyrektora()
        else:
            fsm.odrzuc()
        db.session.commit()

    def powiadom_studenta(
        self,
        zapis: InternshipEnrollment,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> None:
        self._dodaj_zdarzenie(
            zapis, EventType.STUDENT_NOTIFICATION,
            komentarz=komentarz,
            wykonane_przez_id=wykonane_przez_id,
        )
        db.session.commit()

    def zakoncz(self, zapis: InternshipEnrollment) -> None:
        from core.uslugi.workflow import ZapisFSM
        ZapisFSM(zapis).zakoncz()
        db.session.commit()

    # ── Reports ───────────────────────────────────────────────────────────────

    def pobierz_lub_utworz_sprawozdanie(self, zapis: InternshipEnrollment) -> InternshipReport:
        if zapis.report is None:
            report = InternshipReport(enrollment_id=zapis.id)
            db.session.add(report)
            db.session.flush()
            return report
        return zapis.report

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _dodaj_zdarzenie(
        self,
        zapis: InternshipEnrollment,
        typ: EventType,
        decyzja: Optional[str] = None,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> ProcessEvent:
        zdarzenie = ProcessEvent(
            enrollment_id=zapis.id,
            event_type=typ,
            decision=decyzja,
            comment=komentarz,
            executed_by_id=wykonane_przez_id,
            executed_at=datetime.now(timezone.utc),
        )
        db.session.add(zdarzenie)
        return zdarzenie

    # ── Student-facing helpers ────────────────────────────────────────────────

    @staticmethod
    def waliduj_mozliwosc_zakonczenia(zapis) -> tuple[bool, str]:
        """Sprawdza czy praktykę STANDARD można zakończyć.

        Returns:
            (True, '') jeśli można zakończyć,
            (False, komunikat) jeśli warunek nie jest spełniony.
        """
        wymagane      = zapis.internship.required_hours if zapis.internship else 0
        zalogowane    = zapis.total_hours_logged or 0
        liczba_wpisow = len(zapis.journal_entries)

        if liczba_wpisow == 0:
            return False, 'Nie można zakończyć praktyki bez wpisów w dzienniku.'
        if zalogowane < wymagane:
            return (
                False,
                f'Nie można zakończyć praktyki — zalogowano {zalogowane} z wymaganych {wymagane} godzin.',
            )
        return True, ''

    @staticmethod
    def status_dla_studenta(zapis) -> dict:
        """Analizuje zapis i zwraca gotowy dict do widoku listy praktyk studenta."""
        komentarz_admina = zapis.admin_comments
        komentarz_uopz   = zapis.supervisor_comments
        sciezka = zapis.path_type.value if zapis.path_type else None

        zwrocone_a = (
            zapis.status == EnrollmentStatus.PENDING
            and bool(komentarz_admina or komentarz_uopz)
        )
        zwrocone_bc = (
            zapis.status == EnrollmentStatus.AWAITING_APPROVAL
            and bool(komentarz_uopz)
            and sciezka in ('EMPLOYMENT', 'OWN_BUSINESS')
        )
        zwrocone_komisja = (zapis.status == EnrollmentStatus.REVISION_REQUIRED)
        in_review = zapis.status in (EnrollmentStatus.COMMISSION_REVIEW, EnrollmentStatus.DIRECTOR_APPROVAL)
        zwrocone = (zwrocone_a or zwrocone_bc or zwrocone_komisja) and not in_review

        komentarz_komisji = None
        if zwrocone_komisja:
            ev = (
                db.session.query(ProcessEvent)
                .filter_by(enrollment_id=zapis.id, event_type=EventType.COMMITTEE_DECISION)
                .filter(ProcessEvent.decision == 'PARTIALLY_APPROVED')
                .order_by(ProcessEvent.executed_at.desc())
                .first()
            )
            komentarz_komisji = ev.comment if ev else None

        komentarz_odrzucenia = None
        if zapis.status == EnrollmentStatus.REJECTED:
            ev = (
                db.session.query(ProcessEvent)
                .filter_by(enrollment_id=zapis.id)
                .filter(ProcessEvent.decision == 'REJECTED')
                .order_by(ProcessEvent.executed_at.desc())
                .first()
            )
            komentarz_odrzucenia = ev.comment if ev else None

        return {
            'id':                   str(zapis.id),
            'status':               zapis.status.value,
            'sciezka':              sciezka,
            'zwrocone':             zwrocone,
            'komentarz_zwrotny':    komentarz_komisji or komentarz_admina or komentarz_uopz or '',
            'komentarz_odrzucenia': komentarz_odrzucenia or '',
            'wymaga_uwagi': (
                zapis.status == EnrollmentStatus.AWAITING_APPROVAL
                and bool(komentarz_uopz)
                and sciezka == 'STANDARD'
            ),
        }

    # ── Repository access ─────────────────────────────────────────────────────

    @property
    def praktyki(self) -> RepozytoriumPraktyk:
        return self._praktyki

    @property
    def zapisy(self) -> RepozytoriumZapisow:
        return self._zapisy
