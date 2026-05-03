"""Company repository."""
from __future__ import annotations

import uuid
from typing import Optional

from core.extensions import db
from core.models import Company, EnrollmentStatus, InternshipEnrollment


class CompanyRepository:
    """Data access for companies."""

    def find_by_id(self, company_id: uuid.UUID) -> Optional[Company]:
        return db.session.get(Company, company_id)

    def active(self) -> list[Company]:
        return db.session.query(Company).filter_by(is_active=True).order_by(Company.name).all()

    def paginated_list(self, search: str = '', status: str = 'wszystkie',
                       page: int = 1, per_page: int = 25):
        q = db.session.query(Company)
        if status == 'aktywne':
            q = q.filter_by(is_active=True)
        elif status == 'nieaktywne':
            q = q.filter_by(is_active=False)
        if search:
            q = q.filter(db.or_(
                Company.name.ilike(f'%{search}%'),
                Company.address.ilike(f'%{search}%'),
                Company.city.ilike(f'%{search}%'),
                Company.tax_id.ilike(f'%{search}%'),
            ))
        return q.order_by(Company.name).paginate(page=page, per_page=per_page, error_out=False)

    def find_active_by_name(self, name: str,
                            exclude_id: Optional[uuid.UUID] = None) -> Optional[Company]:
        q = db.session.query(Company).filter_by(name=name, is_active=True)
        if exclude_id is not None:
            q = q.filter(Company.id != exclude_id)
        return q.first()

    def find_active_by_tax_id(self, tax_id: str,
                              exclude_id: Optional[uuid.UUID] = None) -> Optional[Company]:
        q = db.session.query(Company).filter_by(tax_id=tax_id, is_active=True)
        if exclude_id is not None:
            q = q.filter(Company.id != exclude_id)
        return q.first()

    def count_internships(self, company_id: uuid.UUID) -> int:
        return db.session.query(InternshipEnrollment).filter_by(company_id=company_id).count()

    def count_active_internships(self, company_id: uuid.UUID,
                                 active_statuses: list[EnrollmentStatus]) -> int:
        return (
            db.session.query(InternshipEnrollment)
            .filter_by(company_id=company_id)
            .filter(InternshipEnrollment.status.in_(active_statuses))
            .count()
        )

    def save(self, company: Company) -> Company:
        db.session.add(company)
        db.session.flush()
        return company

    def delete(self, company: Company) -> None:
        db.session.delete(company)
