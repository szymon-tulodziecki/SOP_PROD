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
            EnrollmentStatus.DEAN_APPROVAL:     fsm.zatwierdz_przez_komisje,
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

    def zatwierdz_przez_dziekana(
        self,
        zapis: InternshipEnrollment,
        decyzja: str,
        komentarz: Optional[str] = None,
        wykonane_przez_id: Optional[uuid.UUID] = None,
    ) -> None:
        from core.uslugi.workflow import ZapisFSM
        self._dodaj_zdarzenie(
            zapis, EventType.DEAN_DECISION,
            decyzja=decyzja, komentarz=komentarz,
            wykonane_przez_id=wykonane_przez_id,
        )
        fsm = ZapisFSM(zapis)
        if decyzja == 'APPROVED':
            fsm.zatwierdz_przez_dziekana()
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

    # ── Repository access ─────────────────────────────────────────────────────

    @property
    def praktyki(self) -> RepozytoriumPraktyk:
        return self._praktyki

    @property
    def zapisy(self) -> RepozytoriumZapisow:
        return self._zapisy
