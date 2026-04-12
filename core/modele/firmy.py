"""core/modele/firmy.py

Domain models: Workplace companies (internship partners).
"""
import uuid
from sqlalchemy.dialects.postgresql import UUID
from core.extensions import db


class Company(db.Model):
    """Workplace — a partner company with a standing agreement with ANS."""
    __tablename__ = 'companies'

    id                   = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name                 = db.Column(db.String(255), nullable=False)
    address              = db.Column(db.String(255), nullable=True)
    city                 = db.Column(db.String(100), nullable=True)
    tax_id               = db.Column(db.String(50),  nullable=True)
    has_standing_agreement = db.Column(db.Boolean, default=True)
    is_active            = db.Column(db.Boolean, default=True)
    created_at           = db.Column(db.DateTime, server_default=db.func.now())

    # Backward-compat shims
    @property
    def nazwa(self):
        return self.name

    @property
    def adres(self):
        return self.address

    @property
    def miasto(self):
        return self.city

    @property
    def nip_krs(self):
        return self.tax_id

    @property
    def ma_stala_umowe(self):
        return self.has_standing_agreement

    def __repr__(self) -> str:
        return f'<Company {self.name}>'


# Backward-compat alias
Firma = Company
