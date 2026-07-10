"""core/modele/porozumienia.py

Domain models: Porozumienia z zakładami pracy (Zał. 1).

Jedno porozumienie obejmuje 1..N zapisów studentów w tym samym zakładzie
pracy. Dziekanat wysyła osobie upoważnionej unikalny link z formularzem;
w bazie trzymamy wyłącznie hash SHA-256 tokenu — sam token istnieje tylko
w wysłanym e-mailu (wyciek bazy nie ujawnia działających linków).
"""

import enum
import uuid

from sqlalchemy.dialects.postgresql import UUID

from core.extensions import db

_FK_USERS = "users.id"


class AgreementStatus(enum.Enum):
    SENT = "SENT"  # link wysłany, czeka na zakład pracy
    FILLED = "FILLED"  # zakład uzupełnił dane porozumienia
    CANCELLED = "CANCELLED"  # anulowane przez dziekanat (link przestaje działać)


class InternshipAgreement(db.Model):
    """Porozumienie w sprawie praktyk — grupowe per zakład pracy."""

    __tablename__ = "internship_agreements"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Snapshot danych zakładu pracy w chwili utworzenia porozumienia
    company_name = db.Column(db.String(255), nullable=False)
    company_address = db.Column(db.String(255), nullable=True)
    company_city = db.Column(db.String(255), nullable=True)
    company_tax_id = db.Column(db.String(50), nullable=True)

    # Osoba upoważniona do podpisania (odbiorca linku)
    recipient_name = db.Column(db.String(255), nullable=False)
    recipient_position = db.Column(db.String(255), nullable=True)
    recipient_email = db.Column(db.String(255), nullable=False)

    token_hash = db.Column(db.String(64), nullable=False, unique=True)

    status = db.Column(
        db.Enum(
            AgreementStatus, name="agreement_status", values_callable=lambda e: [x.value for x in e]
        ),
        nullable=False,
        default=AgreementStatus.SENT,
    )

    created_by_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey(_FK_USERS, ondelete="SET NULL"), nullable=True
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    expires_at = db.Column(db.DateTime, nullable=True)
    filled_at = db.Column(db.DateTime, nullable=True)

    # Dane uzupełniane przez zakład pracy w publicznym formularzu
    signer_name = db.Column(
        db.String(255), nullable=True
    )  # reprezentant zakładu (może się różnić od odbiorcy)
    signer_position = db.Column(db.String(255), nullable=True)
    company_notes = db.Column(db.Text, nullable=True)

    created_by = db.relationship("User")
    enrollments = db.relationship(
        "AgreementEnrollment",
        back_populates="agreement",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def is_open(self) -> bool:
        """Czy link jest jeszcze aktywny (status + termin ważności)."""
        from datetime import datetime, timezone

        if self.status != AgreementStatus.SENT:
            return False
        if self.expires_at is None:
            return True
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) <= expires

    @property
    def students_label(self) -> str:
        return ", ".join(
            f"{ae.enrollment.student.first_name} {ae.enrollment.student.last_name}"
            for ae in self.enrollments
            if ae.enrollment and ae.enrollment.student
        )

    def __repr__(self) -> str:
        return f"<InternshipAgreement {self.company_name} ({self.status})>"


class AgreementEnrollment(db.Model):
    """Powiązanie porozumienia z zapisami studentów (M:N)."""

    __tablename__ = "agreement_enrollments"

    agreement_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("internship_agreements.id", ondelete="CASCADE"),
        primary_key=True,
    )
    enrollment_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("internship_enrollments.id", ondelete="CASCADE"),
        primary_key=True,
    )

    agreement = db.relationship("InternshipAgreement", back_populates="enrollments")
    enrollment = db.relationship(
        "InternshipEnrollment", backref=db.backref("agreement_links", passive_deletes=True)
    )
