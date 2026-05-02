"""core/repozytoria/praktyki.py

Repozytoria edycji praktyk i zapisów studentów.
"""
from __future__ import annotations

from typing import Optional
import uuid

from sqlalchemy import func, case, exists

from core.extensions import db
from core.modele.internships import (
    Internship,
    InternshipStatus,
    InternshipEnrollment,
    EnrollmentStatus,
    InternshipSchedule,
    ProcessEvent,
    EventType,
)


class InternshipRepository:
    """Repository for internship editions."""

    def find_by_id(self, internship_id: uuid.UUID) -> Optional[Internship]:
        return db.session.get(Internship, internship_id)

    def all(self) -> list[Internship]:
        return (
            db.session.query(Internship)
            .filter(Internship.deleted_at.is_(None))
            .order_by(Internship.academic_year.desc(), Internship.semester)
            .all()
        )

    def active(self) -> list[Internship]:
        return (
            db.session.query(Internship)
            .filter_by(status=InternshipStatus.ACTIVE)
            .filter(Internship.deleted_at.is_(None))
            .order_by(Internship.academic_year.desc())
            .all()
        )

    def active_edition(self) -> Optional[Internship]:
        return (
            db.session.query(Internship)
            .filter_by(status=InternshipStatus.ACTIVE)
            .filter(Internship.deleted_at.is_(None))
            .order_by(Internship.academic_year.desc())
            .first()
        )

    def paginated_list(self, page: int = 1, per_page: int = 25):
        return (
            db.session.query(Internship)
            .filter(Internship.deleted_at.is_(None))
            .order_by(Internship.academic_year.desc(), Internship.semester)
            .paginate(page=page, per_page=per_page, error_out=False)
        )

    def inactive_count(self) -> int:
        return (
            db.session.query(Internship)
            .filter_by(status=InternshipStatus.INACTIVE)
            .filter(Internship.deleted_at.is_(None))
            .count()
        )

    def marked_for_deletion(self) -> list[Internship]:
        return (
            db.session.query(Internship)
            .filter(Internship.deleted_at.isnot(None))
            .order_by(Internship.deleted_at.desc())
            .all()
        )

    def save(self, internship: Internship) -> Internship:
        db.session.add(internship)
        db.session.flush()
        return internship

    def delete(self, internship: Internship) -> None:
        db.session.delete(internship)

    def znajdz_po_id(self, praktyka_id: uuid.UUID) -> Optional[Internship]:
        return self.find_by_id(praktyka_id)

    def wszystkie(self) -> list[Internship]:
        return self.all()

    def aktywne(self) -> list[Internship]:
        return self.active()

    def aktywna_edycja(self) -> Optional[Internship]:
        return self.active_edition()

    def lista_strona(self, strona: int = 1, na_strone: int = 25):
        return self.paginated_list(page=strona, per_page=na_strone)

    def liczba_nieaktywnych(self) -> int:
        return self.inactive_count()

    def do_usuniecia(self) -> list[Internship]:
        return self.marked_for_deletion()

    def zapisz(self, praktyka: Internship) -> Internship:
        return self.save(praktyka)

    def usun(self, praktyka: Internship) -> None:
        self.delete(praktyka)


class EnrollmentRepository:
    """Dostęp do zapisów studentów na edycje praktyk."""

    def znajdz_po_id(self, zapis_id: uuid.UUID) -> Optional[InternshipEnrollment]:
        return db.session.get(InternshipEnrollment, zapis_id)

    def wszystkie(self) -> list[InternshipEnrollment]:
        return db.session.query(InternshipEnrollment).order_by(InternshipEnrollment.enrolled_at.desc()).all()

    def dla_studenta(self, student_id: uuid.UUID) -> list[InternshipEnrollment]:
        return (
            db.session.query(InternshipEnrollment)
            .filter_by(student_id=student_id)
            .order_by(InternshipEnrollment.enrolled_at.desc())
            .all()
        )

    def dla_praktyki(self, praktyka_id: uuid.UUID) -> list[InternshipEnrollment]:
        return (
            db.session.query(InternshipEnrollment)
            .filter_by(internship_id=praktyka_id)
            .order_by(InternshipEnrollment.enrolled_at.desc())
            .all()
        )

    def dla_opiekuna(self, uopz_id: uuid.UUID) -> list[InternshipEnrollment]:
        return (
            db.session.query(InternshipEnrollment)
            .filter_by(supervisor_id=uopz_id)
            .order_by(InternshipEnrollment.enrolled_at.desc())
            .all()
        )

    def po_statusie(self, status: EnrollmentStatus) -> list[InternshipEnrollment]:
        return (
            db.session.query(InternshipEnrollment)
            .filter_by(status=status)
            .order_by(InternshipEnrollment.enrolled_at.desc())
            .all()
        )

    def pending_dla_studenta_i_praktyki(self, student_id: uuid.UUID,
                                         praktyka_id: uuid.UUID) -> Optional[InternshipEnrollment]:
        """Zwraca istniejący (nie-odrzucony) zapis studenta dla danej edycji lub None."""
        return (
            db.session.query(InternshipEnrollment)
            .filter(
                InternshipEnrollment.student_id == student_id,
                InternshipEnrollment.internship_id == praktyka_id,
                InternshipEnrollment.status != EnrollmentStatus.REJECTED,
            )
            .first()
        )

    def student_ma_aktywny_zapis(self, student_id: uuid.UUID, praktyka_id: uuid.UUID) -> bool:
        """Sprawdza czy student ma już zapis do danej edycji (inny niż ODRZUCONY)."""
        q = (
            db.session.query(InternshipEnrollment)
            .filter_by(student_id=student_id, internship_id=praktyka_id)
            .filter(InternshipEnrollment.status != EnrollmentStatus.REJECTED)
        )
        return db.session.query(q.exists()).scalar()

    def aktywny_dla_studenta(self, student_id: uuid.UUID,
                              statusy: list) -> Optional[InternshipEnrollment]:
        """Pierwszy aktywny zapis studenta (spośród podanych statusów)."""
        return (
            db.session.query(InternshipEnrollment)
            .filter(InternshipEnrollment.student_id == student_id,
                    InternshipEnrollment.status.in_(statusy))
            .first()
        )

    def pierwszy_dla_studenta(self, student_id: uuid.UUID) -> Optional[InternshipEnrollment]:
        """Dowolny pierwszy zapis studenta (do sprawdzenia czy w ogóle istnieje)."""
        return db.session.query(InternshipEnrollment).filter_by(student_id=student_id).first()

    def aktywne_dla_studenta(self, student_id: uuid.UUID,
                              statusy: list) -> list[InternshipEnrollment]:
        """Lista zapisów studenta z podanymi statusami, malejąco po dacie."""
        return (
            db.session.query(InternshipEnrollment)
            .filter(InternshipEnrollment.student_id == student_id,
                    InternshipEnrollment.status.in_(statusy))
            .order_by(InternshipEnrollment.enrolled_at.desc())
            .all()
        )

    def ostatni_dla_studenta(self, student_id: uuid.UUID) -> Optional[InternshipEnrollment]:
        """Ostatni zapis studenta (dowolny status), malejąco po dacie."""
        return (
            db.session.query(InternshipEnrollment)
            .filter_by(student_id=student_id)
            .order_by(InternshipEnrollment.enrolled_at.desc())
            .first()
        )

    def w_trakcie_strona(self, szukaj: str = '', supervisor_id=None,
                          strona: int = 1, na_strone: int = 20):
        """Lista zapisów IN_PROGRESS i COMPLETED z opcjonalnym filtrem UOPZ i wyszukiwaniem."""
        from sqlalchemy.orm import selectinload
        from core.modele.users import Student, User
        q = (
            db.session.query(InternshipEnrollment)
            .options(selectinload(InternshipEnrollment.student))
            .filter(InternshipEnrollment.status.in_([
                EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMPLETED,
            ]))
        )
        if supervisor_id is not None:
            student_assigned_to_uopz = exists().where(
                (Student.id == InternshipEnrollment.student_id) &
                (Student.supervisor_id == supervisor_id)
            )
            q = q.filter(db.or_(
                InternshipEnrollment.supervisor_id == supervisor_id,
                student_assigned_to_uopz,
            ))
        if szukaj:
            wzorzec = f'%{szukaj}%'
            q = q.join(User, InternshipEnrollment.student_id == User.id).filter(
                db.or_(User.first_name.ilike(wzorzec),
                       User.last_name.ilike(wzorzec))
            )
        return q.order_by(InternshipEnrollment.enrolled_at.desc()).paginate(
            page=strona, per_page=na_strone, error_out=False
        )

    def aktywne_i_zakonczone(self, supervisor_id=None) -> list[InternshipEnrollment]:
        """Zapisy IN_PROGRESS i COMPLETED, opcjonalnie filtrowane do jednego UOPZ."""
        from sqlalchemy.orm import selectinload
        from core.modele.users import User
        q = (
            db.session.query(InternshipEnrollment)
            .options(
                selectinload(InternshipEnrollment.student),
                selectinload(InternshipEnrollment.firma),
                selectinload(InternshipEnrollment.final_grades),
                selectinload(InternshipEnrollment.examination),
            )
            .filter(InternshipEnrollment.status.in_(
                [EnrollmentStatus.IN_PROGRESS, EnrollmentStatus.COMPLETED]
            ))
        )
        if supervisor_id is not None:
            q = q.filter_by(supervisor_id=supervisor_id)
        return q.join(InternshipEnrollment.student).order_by(
            InternshipEnrollment.status.desc(),
            InternshipEnrollment.enrolled_at.desc()
        ).all()

    def zakonczone_dla_uopz(self, supervisor_id) -> list[InternshipEnrollment]:
        from sqlalchemy.orm import selectinload
        return (
            db.session.query(InternshipEnrollment)
            .options(
                selectinload(InternshipEnrollment.student),
                selectinload(InternshipEnrollment.firma),
            )
            .filter(InternshipEnrollment.status == EnrollmentStatus.COMPLETED,
                    InternshipEnrollment.supervisor_id == supervisor_id)
            .all()
        )

    def lista_zgloszen_strona(self, status_filter: str = '',
                               strona: int = 1, na_strone: int = 25,
                               supervisor_id=None):
        """Paginowana lista zgłoszeń ścieżki STANDARD z opcjonalnym filtrem statusu."""
        from sqlalchemy.orm import selectinload
        from core.modele.users import User
        q = (
            db.session.query(InternshipEnrollment)
            .options(
                selectinload(InternshipEnrollment.student),
                selectinload(InternshipEnrollment.firma),
                selectinload(InternshipEnrollment.internship),
            )
            .join(User, InternshipEnrollment.student_id == User.id)
            .filter(InternshipEnrollment.path_type == 'STANDARD')
        )
        if supervisor_id:
            q = q.filter(InternshipEnrollment.supervisor_id == supervisor_id)
        if status_filter:
            q = q.filter(InternshipEnrollment.status == EnrollmentStatus(status_filter))
        return q.order_by(InternshipEnrollment.enrolled_at.desc()).paginate(
            page=strona, per_page=na_strone, error_out=False
        )

    def wnioski_komisja_strona(self, strona: int = 1, na_strone: int = 25):
        """Paginowana lista wniosków wymagających weryfikacji komisji (ścieżki B/C)."""
        from sqlalchemy.orm import selectinload
        from core.modele.users import User
        ma_komentarz_uopz = exists().where(
            (ProcessEvent.enrollment_id == InternshipEnrollment.id) &
            (ProcessEvent.event_type == EventType.SUPERVISOR_COMMENT) &
            ProcessEvent.comment.isnot(None)
        )
        q = (
            db.session.query(InternshipEnrollment)
            .options(selectinload(InternshipEnrollment.student),
                     selectinload(InternshipEnrollment.firma))
            .join(User, InternshipEnrollment.student_id == User.id)
            .filter(InternshipEnrollment.path_type.in_(['EMPLOYMENT', 'OWN_BUSINESS']))
            .filter(db.or_(
                InternshipEnrollment.status == EnrollmentStatus.COMMISSION_REVIEW,
                InternshipEnrollment.status == EnrollmentStatus.REVISION_REQUIRED,
                (InternshipEnrollment.status == EnrollmentStatus.AWAITING_APPROVAL) & ma_komentarz_uopz,
            ))
        )
        return q.order_by(InternshipEnrollment.enrolled_at.desc()).paginate(
            page=strona, per_page=na_strone, error_out=False
        )

    def wnioski_dyrektora_strona(self, strona: int = 1, na_strone: int = 25):
        """Paginowana lista wniosków oczekujących na decyzję dyrektora."""
        from sqlalchemy.orm import selectinload
        from core.modele.users import User
        q = (
            db.session.query(InternshipEnrollment)
            .options(
                selectinload(InternshipEnrollment.student),
                selectinload(InternshipEnrollment.firma),
            )
            .join(User, InternshipEnrollment.student_id == User.id)
            .filter(InternshipEnrollment.status == EnrollmentStatus.DIRECTOR_APPROVAL)
            .filter(InternshipEnrollment.path_type.in_(['EMPLOYMENT', 'OWN_BUSINESS']))
        )
        return q.order_by(InternshipEnrollment.enrolled_at.desc()).paginate(
            page=strona, per_page=na_strone, error_out=False
        )

    def dla_uopz_strona(self, supervisor_id, status_filter: str = '',
                         strona: int = 1, na_strone: int = 25):
        """Paginowana lista zgłoszeń przypisanych do UOPZ."""
        from sqlalchemy.orm import selectinload
        q = (
            db.session.query(InternshipEnrollment)
            .options(
                selectinload(InternshipEnrollment.student),
                selectinload(InternshipEnrollment.firma),
            )
            .filter(InternshipEnrollment.supervisor_id == supervisor_id)
        )
        if status_filter:
            q = q.filter(InternshipEnrollment.status == EnrollmentStatus(status_filter))
        return q.order_by(InternshipEnrollment.enrolled_at.desc()).paginate(
            page=strona, per_page=na_strone, error_out=False
        )

    def liczniki_dla_uopz(self, supervisor_id) -> dict:
        """Trzy liczniki statusów dla UOPZ — jedno zapytanie SQL."""
        row = (
            db.session.query(
                func.count().label('wszystkie'),
                func.count(case(
                    (InternshipEnrollment.status == EnrollmentStatus.AWAITING_APPROVAL, 1)
                )).label('oczekujace'),
                func.count(case(
                    (InternshipEnrollment.status == EnrollmentStatus.IN_PROGRESS, 1)
                )).label('zatwierdzone'),
            )
            .filter(InternshipEnrollment.supervisor_id == supervisor_id)
            .one()
        )
        return {
            'wszystkie':   row.wszystkie,
            'oczekujace':  row.oczekujace,
            'zatwierdzone': row.zatwierdzone,
        }

    def liczniki_nav(self, supervisor_id=None) -> dict:
        """Liczniki statusów dla paska nawigacji (inject_nav_counts)."""
        from core.modele.internships import FinalGrades

        def _base(extra_filter=None):
            q = db.session.query(func.count(InternshipEnrollment.id))
            if supervisor_id:
                q = q.filter(InternshipEnrollment.supervisor_id == supervisor_id)
            if extra_filter is not None:
                q = q.filter(extra_filter)
            return q.scalar() or 0

        oczekujace = _base(InternshipEnrollment.status == EnrollmentStatus.AWAITING_APPROVAL)
        komisja    = _base(InternshipEnrollment.status == EnrollmentStatus.COMMISSION_REVIEW)
        dyrektor   = _base(InternshipEnrollment.status == EnrollmentStatus.DIRECTOR_APPROVAL)

        # Ungraded path A: COMPLETED, no supervisor_grade row
        # Ungraded path B: COMPLETED or IN_PROGRESS, no report_grade row
        # Use NOT EXISTS subquery to avoid join issues with NULL FinalGrades
        from sqlalchemy import exists, and_, or_, cast, String

        has_supervisor = exists().where(
            and_(FinalGrades.enrollment_id == InternshipEnrollment.id,
                 FinalGrades.supervisor_grade.isnot(None))
        )
        has_report = exists().where(
            and_(FinalGrades.enrollment_id == InternshipEnrollment.id,
                 FinalGrades.report_grade.isnot(None))
        )
        path_b_vals = ('EMPLOYMENT', 'OWN_BUSINESS')

        ungraded_a = and_(
            InternshipEnrollment.status == EnrollmentStatus.COMPLETED,
            cast(InternshipEnrollment.path_type, String).notin_(path_b_vals),
            ~has_supervisor,
        )
        ungraded_b = and_(
            InternshipEnrollment.status.in_([EnrollmentStatus.COMPLETED, EnrollmentStatus.IN_PROGRESS]),
            cast(InternshipEnrollment.path_type, String).in_(path_b_vals),
            ~has_report,
        )
        do_oceny = _base(or_(ungraded_a, ungraded_b))

        return {
            'nav_oczekujace': oczekujace,
            'nav_komisja':    komisja,
            'nav_dyrektor':   dyrektor,
            'nav_do_oceny':   do_oceny,
        }

    def liczba_aktywnych_dla_studentow(self, student_ids: list,
                                        aktywne_statusy: list) -> dict:
        """Zwraca {student_id: count} dla listy studentów — eliminuje N+1."""
        if not student_ids:
            return {}
        rows = (
            db.session.query(
                InternshipEnrollment.student_id,
                func.count(InternshipEnrollment.id).label('cnt')
            )
            .filter(InternshipEnrollment.student_id.in_(student_ids),
                    InternshipEnrollment.status.in_(aktywne_statusy))
            .group_by(InternshipEnrollment.student_id)
            .all()
        )
        return {r.student_id: r.cnt for r in rows}

    def statystyki_pulpit(self, supervisor_id=None) -> dict:
        """Liczniki dla panelu głównego — dwa liczniki w jednym zapytaniu."""
        q = db.session.query(InternshipEnrollment)
        if supervisor_id is not None:
            q = q.filter(db.or_(
                InternshipEnrollment.supervisor_id == supervisor_id,
                InternshipEnrollment.status == EnrollmentStatus.PENDING,
            ))
        row = q.with_entities(
            func.count(case((InternshipEnrollment.status == EnrollmentStatus.IN_PROGRESS, 1))).label('aktywne'),
            func.count(case((InternshipEnrollment.status == EnrollmentStatus.COMPLETED, 1))).label('zakonczone'),
        ).one()
        return {'praktyki_aktywne': row.aktywne, 'oczekujace_oceny': row.zakonczone}

    def dashboard_stats(self, supervisor_id=None) -> dict:
        return self.statystyki_pulpit(supervisor_id=supervisor_id)

    def ostatnie(self, supervisor_id=None, limit: int = 8) -> list[InternshipEnrollment]:
        """Ostatnie zapisy (dla widżetu na pulpicie)."""
        from sqlalchemy.orm import selectinload
        q = (
            db.session.query(InternshipEnrollment)
            .options(
                selectinload(InternshipEnrollment.student),
                selectinload(InternshipEnrollment.firma),
            )
        )
        if supervisor_id is not None:
            q = q.filter(db.or_(
                InternshipEnrollment.supervisor_id == supervisor_id,
                InternshipEnrollment.status == EnrollmentStatus.PENDING,
            ))
        return q.order_by(InternshipEnrollment.enrolled_at.desc()).limit(limit).all()

    def recent(self, supervisor_id=None, limit: int = 8) -> list[InternshipEnrollment]:
        return self.ostatnie(supervisor_id=supervisor_id, limit=limit)

    # ── Harmonogramy (powiązane ściśle z zapisami) ────────────────────────────

    def harmonogram_dla_zapisu(self, enrollment_id: uuid.UUID) -> list[InternshipSchedule]:
        return (
            db.session.query(InternshipSchedule)
            .filter_by(enrollment_id=enrollment_id)
            .all()
        )

    def usun_harmonogram(self, enrollment_id: uuid.UUID) -> None:
        db.session.query(InternshipSchedule).filter_by(enrollment_id=enrollment_id).delete()

    def zapisz(self, zapis: InternshipEnrollment) -> InternshipEnrollment:
        db.session.add(zapis)
        db.session.flush()
        return zapis

    def znajdz_odrzucony(self, student_id, internship_id) -> Optional[InternshipEnrollment]:
        return (
            db.session.query(InternshipEnrollment)
            .filter_by(student_id=student_id, internship_id=internship_id,
                       status=EnrollmentStatus.REJECTED)
            .first()
        )

    def usun_zdarzenia_zapisu(self, enrollment_id) -> None:
        db.session.query(ProcessEvent).filter_by(enrollment_id=enrollment_id).delete()

    def zapisz_harmonogram(self, wiersze: list) -> None:
        db.session.add_all(wiersze)

    def ostatnie_zdarzenie(self, enrollment_id, event_type=None,
                           decision=None) -> Optional[ProcessEvent]:
        q = (db.session.query(ProcessEvent)
             .filter_by(enrollment_id=enrollment_id))
        if event_type is not None:
            q = q.filter(ProcessEvent.event_type == event_type)
        if decision is not None:
            q = q.filter(ProcessEvent.decision == decision)
        return q.order_by(ProcessEvent.executed_at.desc()).first()

    def usun(self, zapis: InternshipEnrollment) -> None:
        db.session.delete(zapis)
