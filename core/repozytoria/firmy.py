"""core/repozytoria/firmy.py — Repozytorium firm / zakładów pracy."""
from __future__ import annotations

import uuid
from typing import Optional

from core.extensions import db
from core.modele import Company, InternshipEnrollment, EnrollmentStatus


class CompanyRepository:
    """Jedyne miejsce zapytań ORM dotyczących tabeli firm."""

    def znajdz_po_id(self, firma_id: uuid.UUID) -> Optional[Company]:
        return db.session.get(Company, firma_id)

    def aktywne(self) -> list[Company]:
        return db.session.query(Company).filter_by(is_active=True).order_by(Company.name).all()

    def lista_strona(self, szukaj: str = '', status: str = 'wszystkie',
                     strona: int = 1, na_strone: int = 25):
        q = db.session.query(Company)
        if status == 'aktywne':
            q = q.filter_by(is_active=True)
        elif status == 'nieaktywne':
            q = q.filter_by(is_active=False)
        if szukaj:
            q = q.filter(db.or_(
                Company.name.ilike(f'%{szukaj}%'),
                Company.address.ilike(f'%{szukaj}%'),
                Company.city.ilike(f'%{szukaj}%'),
                Company.tax_id.ilike(f'%{szukaj}%'),
            ))
        return q.order_by(Company.name).paginate(page=strona, per_page=na_strone, error_out=False)

    def znajdz_po_nazwie_aktywna(self, name: str,
                                  pominij_id: Optional[uuid.UUID] = None) -> Optional[Company]:
        q = db.session.query(Company).filter_by(name=name, is_active=True)
        if pominij_id is not None:
            q = q.filter(Company.id != pominij_id)
        return q.first()

    def znajdz_po_nip_aktywna(self, tax_id: str,
                               pominij_id: Optional[uuid.UUID] = None) -> Optional[Company]:
        q = db.session.query(Company).filter_by(tax_id=tax_id, is_active=True)
        if pominij_id is not None:
            q = q.filter(Company.id != pominij_id)
        return q.first()

    def liczba_praktyk(self, firma_id: uuid.UUID) -> int:
        return db.session.query(InternshipEnrollment).filter_by(company_id=firma_id).count()

    def liczba_aktywnych_praktyk(self, firma_id: uuid.UUID,
                                  aktywne_statusy: list) -> int:
        return (
            db.session.query(InternshipEnrollment)
            .filter_by(company_id=firma_id)
            .filter(InternshipEnrollment.status.in_(aktywne_statusy))
            .count()
        )

    def zapisz(self, firma: Company) -> Company:
        db.session.add(firma)
        db.session.flush()
        return firma

    def usun(self, firma: Company) -> None:
        db.session.delete(firma)
