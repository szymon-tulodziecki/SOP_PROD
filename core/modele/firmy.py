"""core/modele/firmy.py

Modele domenowe: Zakłady pracy (firmy współpracujące z uczelnią).
"""
import uuid
from sqlalchemy.dialects.postgresql import UUID
from core.extensions import db


class Firma(db.Model):
    """Zakład pracy — partner praktyk o stałej umowie z ANS."""
    __tablename__ = 'firmy'

    id                   = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nazwa                = db.Column(db.String(255), nullable=False)
    adres                = db.Column(db.String(255), nullable=True)
    miasto               = db.Column(db.String(100), nullable=True)
    nip_krs              = db.Column(db.String(50),  nullable=True)
    stala_umowa          = db.Column('stala_umowa',  db.Boolean, default=True)
    aktywna              = db.Column('aktywna',      db.Boolean, default=True)
    utworzono            = db.Column('utworzono',    db.DateTime, server_default=db.func.now())

    # Compat
    @property
    def has_standing_agreement(self):
        return self.stala_umowa

    @property
    def is_active(self):
        return self.aktywna

    def __repr__(self) -> str:
        return f'<Firma {self.nazwa}>'
