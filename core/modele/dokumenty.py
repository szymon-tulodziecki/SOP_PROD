"""core/modele/dokumenty.py

Modele domenowe: Przesłane dokumenty, Log audytu.
"""
import uuid
import enum

from sqlalchemy.dialects.postgresql import UUID
from core.extensions import db


class StatusDokumentu(enum.Enum):
    SZKIC      = 'DRAFT'
    OCZEKUJACY = 'AWAITING_APPROVAL'
    ZATWIERDZONY = 'APPROVED'
    ODRZUCONY  = 'REJECTED'

    # Compat
    DRAFT = 'DRAFT'
    AWAITING_APPROVAL = 'AWAITING_APPROVAL'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'


class LogAudytuDokumentow(db.Model):
    """Ślad audytu dla operacji na dokumentach PDF."""
    __tablename__ = 'logi_audytu_dokumentow'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uzytkownik_id = db.Column('uzytkownik_id', UUID(as_uuid=True), db.ForeignKey('uzytkownicy.id', ondelete='SET NULL'), nullable=True)
    zapis_id      = db.Column('zapis_id',      UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='SET NULL'), nullable=True)
    typ_dokumentu = db.Column('typ_dokumentu', db.String(50), nullable=False)
    akcja         = db.Column('akcja',         db.String(50), nullable=False)
    szczegoly     = db.Column('szczegoly',     db.Text, nullable=True)
    wykonano_o    = db.Column('wykonano_o',    db.DateTime, server_default=db.func.now())

    uzytkownik = db.relationship('Uzytkownik')
    zapis      = db.relationship('ZapisPraktyki')

    # Compat
    @property
    def user_id(self):
        return self.uzytkownik_id

    @property
    def enrollment_id(self):
        return self.zapis_id

    @property
    def document_type(self):
        return self.typ_dokumentu

    @property
    def action(self):
        return self.akcja

    @property
    def details(self):
        return self.szczegoly

    @property
    def created_at(self):
        return self.wykonano_o


# Alias dla istniejącego kodu
DocumentAuditLog = LogAudytuDokumentow


class DokumentPrzeslany(db.Model):
    """Plik przesłany przez studenta lub pracownika (umowy, zaświadczenia itp.)."""
    __tablename__ = 'dokumenty_przeslane'

    id                 = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id           = db.Column('zapis_id',      UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False)
    typ_dokumentu      = db.Column('typ_dokumentu', db.String(50),  nullable=False)
    oryginalna_nazwa   = db.Column('oryginalna_nazwa', db.String(255), nullable=False)
    zapisana_nazwa     = db.Column('zapisana_nazwa',   db.String(255), nullable=False)
    sciezka_pliku      = db.Column('sciezka_pliku',    db.String(500), nullable=False)
    rozmiar_pliku      = db.Column('rozmiar_pliku',    db.Integer, nullable=False)
    typ_mime           = db.Column('typ_mime',         db.String(100), nullable=False)
    przeslano_o        = db.Column('przeslano_o',      db.DateTime, server_default=db.func.now())
    przeslane_przez_id = db.Column('przeslane_przez_id', UUID(as_uuid=True), db.ForeignKey('uzytkownicy.id', ondelete='SET NULL'), nullable=True)

    zapis          = db.relationship('ZapisPraktyki', backref=db.backref('uploaded_documents', passive_deletes=True))
    przeslane_przez = db.relationship('Uzytkownik')

    # Compat
    @property
    def enrollment_id(self):
        return self.zapis_id

    @property
    def document_type(self):
        return self.typ_dokumentu

    @property
    def original_filename(self):
        return self.oryginalna_nazwa

    @property
    def stored_filename(self):
        return self.zapisana_nazwa

    @property
    def file_path(self):
        return self.sciezka_pliku

    @property
    def file_size(self):
        return self.rozmiar_pliku

    @property
    def mime_type(self):
        return self.typ_mime

    @property
    def uploaded_at(self):
        return self.przeslano_o

    @property
    def uploaded_by_id(self):
        return self.przeslane_przez_id


# Alias dla istniejącego kodu
UploadedDocument = DokumentPrzeslany
