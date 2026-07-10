"""core/modele/dokumenty.py

Domain models: Uploaded documents, audit log.
"""

import uuid

from sqlalchemy.dialects.postgresql import UUID
from core.extensions import db

_ON_SET_NULL = "SET NULL"


class DocumentAuditLog(db.Model):
    """Audit trail for PDF document operations."""

    __tablename__ = "document_audit_logs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id", ondelete=_ON_SET_NULL), nullable=True
    )
    enrollment_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("internship_enrollments.id", ondelete=_ON_SET_NULL),
        nullable=True,
    )
    document_type = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User")
    enrollment = db.relationship("InternshipEnrollment")


class UploadedDocument(db.Model):
    """File uploaded by a student or staff member (contracts, certificates, etc.).

    Soft-delete pattern: documents are never physically removed — only marked
    is_deleted=True.  The FK to internship_enrollments uses SET NULL so that
    archival documents survive even after the enrollment record is deleted.
    """

    __tablename__ = "uploaded_documents"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("internship_enrollments.id", ondelete=_ON_SET_NULL),
        nullable=True,
    )
    document_type = db.Column(db.String(50), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    mime_type = db.Column(db.String(100), nullable=False)
    uploaded_at = db.Column(db.DateTime, server_default=db.func.now())
    uploaded_by_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id", ondelete=_ON_SET_NULL), nullable=True
    )
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, server_default="false")

    enrollment = db.relationship(
        "InternshipEnrollment", backref=db.backref("uploaded_documents", passive_deletes=True)
    )
    uploaded_by = db.relationship("User")
