"""core/repozytoria/praktyki.py

Repozytoria edycji praktyk i zapisów studentów.
"""
from __future__ import annotations

from typing import Optional
import uuid

from sqlalchemy import func, case, exists

from core.extensions import db
from core.modele.praktyki import (
    Internship,
    InternshipStatus,
    InternshipEnrollment,
    EnrollmentStatus,
    InternshipSchedule,
    ProcessEvent,
    EventType,
)


class RepozytoriumPraktyk:
    """Dostęp do edycji praktyk (rok akademicki / semestr)."""

    def znajdz_po_id(self, praktyka_id: uuid.UUID) -> Optional[Internship]:
        return db.session.get(Internship, praktyka_id)

    def wszystkie(self) -> list[Internship]:
        return db.session.query(Internship).order_by(Internship.academic_year.desc(), Internship.semester).all()

    def aktywne(self) -> list[Internship]:
        return (
            db.session.query(Internship)
            .filter_by(status=InternshipStatus.ACTIVE)
            .order_by(Internship.academic_year.desc())
            .all()
        )

    def aktywna_edycja(self) -> Optional[Internship]:
        """Zwraca pierwszą aktywną edycję praktyk lub None."""
        return (
            db.session.query(Internship)
            .filter_by(status=InternshipStatus.ACTIVE)
            .order_by(Internship.academic_year.desc())
            .first()
        )

    def lista_strona(self, strona: int = 1, na_strone: int = 25):
        return (
            db.session.query(Internship)
            .order_by(Internship.academic_year.desc(), Internship.semester)
            .paginate(page=strona, per_page=na_strone, error_out=False)
        )

    def liczba_nieaktywnych(self) -> int:
        return db.session.query(Internship).filter_by(status=InternshipStatus.INACTIVE).count()

    def zapisz(self, praktyka: Internship) -> Internship:
        db.session.add(praktyka)
        db.session.flush()
        return praktyka

    def usun(self, praktyka: Internship) -> None:
        db.session.delete(praktyka)


class RepozytoriumZapisow:
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
        """Zwraca PENDING zapis studenta dla danej edycji praktyki lub None."""
        return (
            db.session.query(InternshipEnrollment)
            .filter_by(student_id=student_id, internship_id=praktyka_id,
                       status=EnrollmentStatus.PENDING)
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
        """Lista zapisów IN_PROGRESS z opcjonalnym filtrem UOPZ i wyszukiwaniem."""
        from sqlalchemy.orm import selectinload
        from core.modele.uzytkownicy import User
        q = (
            db.session.query(InternshipEnrollment)
            .options(selectinload(InternshipEnrollment.student))
            .filter(InternshipEnrollment.status == EnrollmentStatus.IN_PROGRESS)
        )
        if supervisor_id is not None:
            q = q.filter_by(supervisor_id=supervisor_id)
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
        from core.modele.uzytkownicy import User
        q = (
            db.session.query(InternshipEnrollment)
            .options(
                selectinload(InternshipEnrollment.student),
                selectinload(InternshipEnrollment.firma),
                selectinload(InternshipEnrollment.final_grades),
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
                               strona: int = 1, na_strone: int = 25):
        """Paginowana lista zgłoszeń ścieżki STANDARD z opcjonalnym filtrem statusu."""
        from sqlalchemy.orm import selectinload
        from core.modele.uzytkownicy import User
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
        if status_filter:
            q = q.filter(InternshipEnrollment.status == EnrollmentStatus(status_filter))
        return q.order_by(InternshipEnrollment.enrolled_at.desc()).paginate(
            page=strona, per_page=na_strone, error_out=False
        )

    def wnioski_komisja_strona(self, strona: int = 1, na_strone: int = 25):
        """Paginowana lista wniosków wymagających weryfikacji komisji (ścieżki B/C)."""
        from sqlalchemy.orm import selectinload
        from core.modele.uzytkownicy import User
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

    def wnioski_dziekana_strona(self, strona: int = 1, na_strone: int = 25):
        """Paginowana lista wniosków oczekujących na decyzję dziekana."""
        from sqlalchemy.orm import selectinload
        from core.modele.uzytkownicy import User
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

    def liczniki_nav(self) -> dict:
        """Liczniki statusów dla paska nawigacji (inject_nav_counts) — jedno zapytanie."""
        row = (
            db.session.query(
                func.count(case(
                    (InternshipEnrollment.status == EnrollmentStatus.AWAITING_APPROVAL, 1)
                )).label('oczekujace'),
                func.count(case(
                    (InternshipEnrollment.status == EnrollmentStatus.COMMISSION_REVIEW, 1)
                )).label('komisja'),
                func.count(case(
                    (InternshipEnrollment.status == EnrollmentStatus.DIRECTOR_APPROVAL, 1)
                )).label('dziekan'),
                func.count(case(
                    (InternshipEnrollment.status == EnrollmentStatus.COMPLETED, 1)
                )).label('do_oceny'),
            )
            .one()
        )
        return {
            'nav_oczekujace': row.oczekujace,
            'nav_komisja':    row.komisja,
            'nav_dyrektor':   row.dziekan,
            'nav_do_oceny':   row.do_oceny,
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

    def usun(self, zapis: InternshipEnrollment) -> None:
        db.session.delete(zapis)
