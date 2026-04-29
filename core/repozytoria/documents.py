"""core/repozytoria/dokumenty.py — Repozytoria logów audytu i dokumentów przesłanych."""
from __future__ import annotations

import uuid

from sqlalchemy import desc

from core.extensions import db
from core.modele import DocumentAuditLog, UploadedDocument


class LogRepository:
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

    def wszystkie_zdarzenia(self, filtr_typ=None, szukaj_user: str = '',
                             strona: int = 1, na_strone: int = 30):
        from core.modele.internships import ProcessEvent, EventType, InternshipEnrollment
        from core.modele.users import User
        from sqlalchemy import desc
        q = db.session.query(ProcessEvent).order_by(desc(ProcessEvent.executed_at))
        if filtr_typ:
            try:
                q = q.filter(ProcessEvent.event_type == EventType(filtr_typ))
            except ValueError:
                pass
        if szukaj_user:
            wzorzec = f'%{szukaj_user}%'
            q = (q.join(ProcessEvent.enrollment)
                  .join(User, InternshipEnrollment.student_id == User.id)
                  .filter(db.or_(User.first_name.ilike(wzorzec),
                                 User.last_name.ilike(wzorzec))))
        return q.paginate(page=strona, per_page=na_strone, error_out=False)


class StudentDocumentRepository:
    """Dostęp do przesłanych dokumentów powiązanych z zapisem i studentem."""

    def dla_zapisu_studenta(self, enrollment_id: uuid.UUID,
                             student_id: uuid.UUID) -> list[UploadedDocument]:
        return (
            db.session.query(UploadedDocument)
            .filter_by(enrollment_id=enrollment_id, uploaded_by_id=student_id)
            .order_by(UploadedDocument.uploaded_at.desc())
            .all()
        )

    def znajdz_po_id(self, document_id: uuid.UUID) -> UploadedDocument | None:
        return db.session.get(UploadedDocument, document_id)

    def dokumenty_zapisu(self, enrollment_id: uuid.UUID) -> list[UploadedDocument]:
        return (db.session.execute(
            db.select(UploadedDocument).filter_by(enrollment_id=enrollment_id)
        ).scalars().all())

    def dokumenty_zapisu_posortowane(self, enrollment_id: uuid.UUID) -> list[UploadedDocument]:
        return (db.session.execute(
            db.select(UploadedDocument)
            .filter_by(enrollment_id=enrollment_id)
            .order_by(UploadedDocument.uploaded_at.desc())
        ).scalars().all())

    def zapisz(self, doc: UploadedDocument) -> UploadedDocument:
        db.session.add(doc)
        return doc

    def zapisz_log(self, log: DocumentAuditLog) -> None:
        db.session.add(log)
