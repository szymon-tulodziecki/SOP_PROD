"""core/modele/dokumenty.py

Domain models: Uploaded documents, audit log.
"""
import uuid
import enum

from sqlalchemy.dialects.postgresql import UUID
from core.extensions import db


class DocumentStatus(enum.Enum):
    DRAFT             = 'DRAFT'
    AWAITING_APPROVAL = 'AWAITING_APPROVAL'
    APPROVED          = 'APPROVED'
    REJECTED          = 'REJECTED'


class DocumentAuditLog(db.Model):
    """Audit trail for PDF document operations."""
    __tablename__ = 'document_audit_logs'

    id             = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id',                  ondelete='SET NULL'), nullable=True)
    enrollment_id  = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='SET NULL'), nullable=True)
    document_type  = db.Column(db.String(50),  nullable=False)
    action         = db.Column(db.String(50),  nullable=False)
    details        = db.Column(db.Text,        nullable=True)
    created_at     = db.Column(db.DateTime,    server_default=db.func.now())

    user       = db.relationship('User')
    enrollment = db.relationship('InternshipEnrollment')

    # Backward-compat shims
    @property
    def uzytkownik_id(self):
        return self.user_id

    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def typ_dokumentu(self):
        return self.document_type

    @property
    def akcja(self):
        return self.action

    @property
    def szczegoly(self):
        return self.details

    @property
    def wykonano_o(self):
        return self.created_at


class UploadedDocument(db.Model):
    """File uploaded by a student or staff member (contracts, certificates, etc.).

    Soft-delete pattern: documents are never physically removed — only marked
    is_deleted=True.  The FK to internship_enrollments uses SET NULL so that
    archival documents survive even after the enrollment record is deleted.
    """
    __tablename__ = 'uploaded_documents'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='SET NULL'), nullable=True)
    document_type       = db.Column(db.String(50),  nullable=False)
    original_filename   = db.Column(db.String(255), nullable=False)
    stored_filename     = db.Column(db.String(255), nullable=False)
    file_path           = db.Column(db.String(500), nullable=False)
    file_size           = db.Column(db.Integer,     nullable=False)
    mime_type           = db.Column(db.String(100), nullable=False)
    uploaded_at         = db.Column(db.DateTime,    server_default=db.func.now())
    uploaded_by_id      = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    is_deleted          = db.Column(db.Boolean,     nullable=False, default=False, server_default='false')

    enrollment   = db.relationship('InternshipEnrollment', backref=db.backref('uploaded_documents', passive_deletes=True))
    uploaded_by  = db.relationship('User')

    # Backward-compat shims
    @property
    def zapis_id(self):
        return self.enrollment_id

    @property
    def typ_dokumentu(self):
        return self.document_type

    @property
    def oryginalna_nazwa(self):
        return self.original_filename

    @property
    def zapisana_nazwa(self):
        return self.stored_filename

    @property
    def sciezka_pliku(self):
        return self.file_path

    @property
    def rozmiar_pliku(self):
        return self.file_size

    @property
    def typ_mime(self):
        return self.mime_type

    @property
    def przeslano_o(self):
        return self.uploaded_at

    @property
    def przeslane_przez_id(self):
        return self.uploaded_by_id


# Backward-compat aliases
StatusDokumentu      = DocumentStatus
LogAudytuDokumentow  = DocumentAuditLog
DokumentPrzeslany    = UploadedDocument
