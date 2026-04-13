"""core/repozytoria/dokumenty.py — Repozytoria logów audytu i dokumentów przesłanych."""
from __future__ import annotations

import uuid

from core.extensions import db
from core.modele import DocumentAuditLog, UploadedDocument


class RepozytoriumLogow:
    """Dostęp do dziennika audytu operacji na dokumentach."""

    def ostatnie_dla_zapisu(self, enrollment_id: uuid.UUID,
                             limit: int = 20) -> list[DocumentAuditLog]:
        return (
            db.session.query(DocumentAuditLog)
            .filter_by(enrollment_id=enrollment_id)
            .order_by(DocumentAuditLog.created_at.desc())
            .limit(limit)
            .all()
        )


class RepozytoriumDokumentowStudenta:
    """Dostęp do przesłanych dokumentów powiązanych z zapisem i studentem."""

    def dla_zapisu_studenta(self, enrollment_id: uuid.UUID,
                             student_id: uuid.UUID) -> list[UploadedDocument]:
        return (
            db.session.query(UploadedDocument)
            .filter_by(enrollment_id=enrollment_id, uploaded_by_id=student_id)
            .order_by(UploadedDocument.uploaded_at.desc())
            .all()
        )
