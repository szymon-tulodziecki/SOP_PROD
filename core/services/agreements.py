"""core/services/agreements.py

Logika porozumień z zakładami pracy.

Bezpieczeństwo tokenu:
  - surowy token: secrets.token_urlsafe(32) — trafia wyłącznie do e-maila,
  - w bazie tylko SHA-256(token) — wyciek bazy nie ujawnia aktywnych linków,
  - wyszukiwanie po hashu (indeks unique), porównanie stałoczasowe zbędne,
    bo hash nie jest sekretem porównywanym ze źródłem zewnętrznym.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from core.extensions import db
from core.models import (
    AgreementEnrollment,
    AgreementStatus,
    InternshipAgreement,
    InternshipEnrollment,
)

TOKEN_VALID_DAYS = 30


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class AgreementService:
    """Tworzenie, wyszukiwanie i wypełnianie porozumień."""

    @staticmethod
    def enrollment_ids_with_open_agreement(enrollment_ids) -> set[uuid.UUID]:
        """Zwraca id zapisów, które mają już porozumienie SENT albo FILLED."""
        if not enrollment_ids:
            return set()
        rows = (
            db.session.query(AgreementEnrollment.enrollment_id)
            .join(InternshipAgreement, InternshipAgreement.id == AgreementEnrollment.agreement_id)
            .filter(AgreementEnrollment.enrollment_id.in_(enrollment_ids))
            .filter(InternshipAgreement.status != AgreementStatus.CANCELLED)
            .all()
        )
        return {r.enrollment_id for r in rows}

    @staticmethod
    def create_agreement(
        enrollments: list[InternshipEnrollment],
        recipient_name: str,
        recipient_email: str,
        recipient_position: str = "",
        created_by_id=None,
    ) -> tuple[InternshipAgreement, str]:
        """Tworzy porozumienie dla grupy zapisów. Zwraca (porozumienie, surowy token).

        Commit po stronie wywołującego. Wszystkie zapisy muszą dotyczyć tego
        samego zakładu pracy (walidacja po stronie widoku dziekanatu).
        """
        if not enrollments:
            raise ValueError("Porozumienie musi obejmować co najmniej jednego studenta.")

        wzorzec = enrollments[0]
        raw_token = secrets.token_urlsafe(32)
        agreement = InternshipAgreement(
            company_name=wzorzec.company_display_name or "",
            company_address=wzorzec.company_display_address,
            company_city=wzorzec.company_city,
            company_tax_id=wzorzec.company_display_tax_id,
            recipient_name=recipient_name,
            recipient_position=recipient_position or None,
            recipient_email=recipient_email,
            token_hash=_hash_token(raw_token),
            status=AgreementStatus.SENT,
            created_by_id=created_by_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=TOKEN_VALID_DAYS),
        )
        db.session.add(agreement)
        for zapis in enrollments:
            agreement.enrollments.append(AgreementEnrollment(enrollment_id=zapis.id))
        return agreement, raw_token

    @staticmethod
    def find_by_token(raw_token: str) -> InternshipAgreement | None:
        """Zwraca porozumienie dla tokenu niezależnie od statusu (albo None)."""
        if not raw_token or len(raw_token) > 128:
            return None
        return (
            db.session.query(InternshipAgreement)
            .filter_by(token_hash=_hash_token(raw_token))
            .one_or_none()
        )

    @staticmethod
    def find_open_by_token(raw_token: str) -> InternshipAgreement | None:
        """Zwraca aktywne porozumienie dla tokenu albo None (zły/wygasły/zamknięty)."""
        agreement = AgreementService.find_by_token(raw_token)
        if agreement is None or not agreement.is_open:
            return None
        return agreement

    @staticmethod
    def fill_agreement(
        agreement: InternshipAgreement,
        signer_name: str,
        signer_position: str = "",
        company_notes: str = "",
    ) -> None:
        """Zapisuje dane z publicznego formularza i zamyka link. Commit u wywołującego."""
        agreement.signer_name = signer_name
        agreement.signer_position = signer_position or None
        agreement.company_notes = company_notes or None
        agreement.status = AgreementStatus.FILLED
        agreement.filled_at = datetime.now(timezone.utc)

    @staticmethod
    def cancel(agreement: InternshipAgreement) -> None:
        agreement.status = AgreementStatus.CANCELLED
