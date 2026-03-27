import uuid
import enum
from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import UUID
from app_admin.extensions import db


# ── Enums ─────────────────────────────────────────────────────────────────────

class RolaUzytkownika(enum.Enum):
    STUDENT = 'STUDENT'
    UOPZ    = 'UOPZ'
    ADMIN   = 'ADMIN'


class StatusPraktyki(enum.Enum):
    ACTIVE   = 'ACTIVE'
    INACTIVE = 'INACTIVE'


class StatusZapisu(enum.Enum):
    PENDING           = 'PENDING'
    AWAITING_APPROVAL = 'AWAITING_APPROVAL'
    COMMISSION_REVIEW = 'COMMISSION_REVIEW'  # Weryfikacja przez komisję (ścieżki B/C)
    DEAN_APPROVAL     = 'DEAN_APPROVAL'      # Oczekuje na zatwierdzenie dziekana (ścieżki B/C)
    IN_PROGRESS       = 'IN_PROGRESS'
    COMPLETED         = 'COMPLETED'
    REJECTED          = 'REJECTED'           # Odrzucone przez komisję/dziekana


class SciezkaPraktyki(enum.Enum):
    STANDARD = 'STANDARD'
    EMPLOYMENT = 'EMPLOYMENT'
    OWN_BUSINESS = 'OWN_BUSINESS'


class WynikOceny(enum.Enum):
    OSIAGNIETO     = 'ACHIEVED'
    CZESCIOWO      = 'PARTIALLY_ACHIEVED'
    NIE_OSIAGNIETO = 'NOT_ACHIEVED'


class StatusDokumentu(enum.Enum):
    DRAFT = 'DRAFT'
    AWAITING_APPROVAL = 'AWAITING_APPROVAL'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'


# ── Modele ────────────────────────────────────────────────────────────────────

class Uzytkownik(UserMixin, db.Model):
    __tablename__ = 'users'

    id                    = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email                 = db.Column(db.String(255), unique=True, nullable=False)
    password_hash         = db.Column(db.String(255), nullable=False)
    first_name            = db.Column(db.String(100), nullable=False)
    last_name             = db.Column(db.String(100), nullable=False)
    album_number          = db.Column(db.String(20), nullable=True)
    role                  = db.Column(db.Enum(RolaUzytkownika, name='user_role', values_callable=lambda e: [x.value for x in e]), nullable=False)
    is_active             = db.Column(db.Boolean, default=True)
    wymagana_zmiana_hasla = db.Column(db.Boolean, default=True)
    created_at            = db.Column(db.DateTime, server_default=db.func.now())

    # Aliasy
    @property
    def imie(self): return self.first_name
    @imie.setter
    def imie(self, v): self.first_name = v

    @property
    def nazwisko(self): return self.last_name
    @nazwisko.setter
    def nazwisko(self, v): self.last_name = v

    @property
    def numer_albumu(self): return self.album_number
    @numer_albumu.setter
    def numer_albumu(self, v): self.album_number = v

    @property
    def rola(self): return self.role
    @rola.setter
    def rola(self, v): self.role = v

    @property
    def aktywny(self): return self.is_active
    @aktywny.setter
    def aktywny(self, v): self.is_active = v

    @property
    def hash_hasla(self): return self.password_hash
    @hash_hasla.setter
    def hash_hasla(self, v): self.password_hash = v

    def get_id(self):
        return str(self.id)


class Praktyka(db.Model):
    __tablename__ = 'internships'

    id             = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rok_uczelniany = db.Column(db.String(9), nullable=False)   # np. '2023/2024'
    semestr        = db.Column(db.String(10), nullable=False)  # 'zimowy' / 'letni'
    wymiar_godzin  = db.Column(db.Integer, nullable=False, default=160)
    status         = db.Column(db.Enum(StatusPraktyki, name='internship_status', values_callable=lambda e: [x.value for x in e]), nullable=False, default=StatusPraktyki.INACTIVE)
    created_at     = db.Column(db.DateTime, server_default=db.func.now())

    # Relacja do zapisów
    zapisy = db.relationship('ZapisPraktyki', backref='praktyka', lazy='select',
                             cascade='all, delete-orphan')


class Firma(db.Model):
    __tablename__ = 'companies'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nazwa = db.Column(db.String(255), nullable=False)
    adres = db.Column(db.String(255), nullable=True)
    miasto = db.Column(db.String(100), nullable=True)
    nip_krs = db.Column(db.String(50), nullable=True)
    has_standing_agreement = db.Column(db.Boolean, default=True)  # Wszystkie firmy w bazie mają stałą umowę
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    is_active = db.Column(db.Boolean, default=True)


class ZapisPraktyki(db.Model):
    __tablename__ = 'internship_enrollments'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    internship_id = db.Column(UUID(as_uuid=True), db.ForeignKey('internships.id', ondelete='CASCADE'), nullable=False)
    student_id    = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    uopz_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    firma_id      = db.Column(UUID(as_uuid=True), db.ForeignKey('companies.id', ondelete='SET NULL'), nullable=True)  # Link do firmy z bazy
    status        = db.Column(db.Enum(StatusZapisu, name='enrollment_status', values_callable=lambda e: [x.value for x in e]), nullable=False, default=StatusZapisu.PENDING)
    track_type    = db.Column(db.Enum(SciezkaPraktyki, name='internship_track', values_callable=lambda e: [x.value for x in e]), nullable=False, default=SciezkaPraktyki.STANDARD)
    
    # Terminy i ogólne
    termin_od        = db.Column(db.Date, nullable=True)
    termin_do        = db.Column(db.Date, nullable=True)
    specjalnosc      = db.Column(db.String(255), nullable=True)
    ubezpieczenie_nw = db.Column(db.Boolean, default=False)
    
    # Dane o firmie (tylko do tex)
    firma_nazwa                  = db.Column(db.String(255), nullable=True)
    firma_adres                  = db.Column(db.String(255), nullable=True)
    firma_miasto                 = db.Column(db.String(255), nullable=True)
    firma_nip_krs                = db.Column(db.String(50), nullable=True)
    firma_upowazniony_osoba      = db.Column(db.String(255), nullable=True)
    firma_upowazniony_stanowisko = db.Column(db.String(255), nullable=True)
    
    # Dane ZOPZ (tylko do tex)
    zopz_imie_nazwisko = db.Column(db.String(255), nullable=True)
    zopz_stanowisko    = db.Column(db.String(255), nullable=True)
    zopz_telefon       = db.Column(db.String(50), nullable=True)
    zopz_email         = db.Column(db.String(255), nullable=True)
    
    # Dodatki dla ścieżek
    uzasadnienie_sciezki = db.Column(db.Text, nullable=True)
    zalaczniki_sciezki   = db.Column(db.Text, nullable=True)
    
    # Oceny z procesu ewaluacji
    ocena_sprawozdania = db.Column(db.Numeric(3,1), nullable=True)
    ocena_uopz         = db.Column(db.Numeric(3,1), nullable=True)
    ocena_zopz         = db.Column(db.Numeric(3,1), nullable=True)
    ocena_opisowa_uopz = db.Column(db.Text, nullable=True)
    ocena_opisowa_zopz = db.Column(db.Text, nullable=True)
    
    # Pytania egzaminacyjne
    sprawdzian_pytanie_1 = db.Column(db.Text, nullable=True)
    sprawdzian_ocena_1   = db.Column(db.Numeric(3,1), nullable=True)
    sprawdzian_pytanie_2 = db.Column(db.Text, nullable=True)
    sprawdzian_ocena_2   = db.Column(db.Numeric(3,1), nullable=True)
    sprawdzian_pytanie_3 = db.Column(db.Text, nullable=True)
    sprawdzian_ocena_3   = db.Column(db.Numeric(3,1), nullable=True)

    total_hours_logged = db.Column(db.Integer, default=0)
    enrolled_at   = db.Column(db.DateTime, server_default=db.func.now())

    # Feedback system
    admin_comments       = db.Column(db.Text)  # Komentarze administratora
    uopz_comments        = db.Column(db.Text)  # Komentarze UOPZ
    student_notified_at  = db.Column(db.DateTime)  # Kiedy powiadomiono studenta

    # Commission and Dean workflow (for non-standard tracks)
    komisja_comments     = db.Column(db.Text)     # Komentarz komisji weryfikującej
    komisja_decision     = db.Column(db.String(20))  # 'APPROVED', 'PARTIALLY_APPROVED', 'REJECTED'
    komisja_decision_at  = db.Column(db.DateTime)    # Kiedy komisja podjęła decyzję
    dean_comments        = db.Column(db.Text)        # Komentarz dziekana
    dean_decision        = db.Column(db.String(20))  # 'APPROVED', 'REJECTED'
    dean_decision_at     = db.Column(db.DateTime)    # Kiedy dziekan podjął decyzję

    # Relacje
    student = db.relationship('Uzytkownik', foreign_keys=[student_id], lazy='select')
    uopz    = db.relationship('Uzytkownik', foreign_keys=[uopz_id],    lazy='select')
    firma   = db.relationship('Firma', foreign_keys=[firma_id], lazy='select')
    wpisy_dziennika = db.relationship('WpisDziennika', backref='zapis', lazy='select', cascade='all, delete-orphan')
    oceny = db.relationship('OcenaPraktyki', backref='zapis', lazy='select', cascade='all, delete-orphan')
    harmonogram = db.relationship('HarmonogramPraktyki', backref='zapis', lazy='select', cascade='all, delete-orphan')
    sprawozdanie = db.relationship('Sprawozdanie', backref='zapis', uselist=False, lazy='select', cascade='all, delete-orphan')

    @property
    def lacznie_godzin(self): return self.total_hours_logged

    @property
    def ocena_e(self):
        oceny = []
        if self.sprawdzian_ocena_1 is not None: oceny.append(float(self.sprawdzian_ocena_1))
        if self.sprawdzian_ocena_2 is not None: oceny.append(float(self.sprawdzian_ocena_2))
        if self.sprawdzian_ocena_3 is not None: oceny.append(float(self.sprawdzian_ocena_3))
        if not oceny: return None
        return round(sum(oceny) / len(oceny), 2)

    @property
    def ocena_k(self):
        e = self.ocena_e
        s = float(self.ocena_sprawozdania) if self.ocena_sprawozdania is not None else None
        u = float(self.ocena_uopz) if self.ocena_uopz is not None else None
        z = float(self.ocena_zopz) if self.ocena_zopz is not None else None
        
        if e is None or s is None or u is None or z is None:
            return None
            
        k = 0.4 * e + 0.1 * s + 0.2 * u + 0.3 * z
        return round(k, 2)


class HarmonogramPraktyki(db.Model):
    __tablename__ = 'internship_schedule'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)
    nazwa_dzialu        = db.Column(db.String(255), nullable=False)
    przykladowe_prace   = db.Column(db.Text, nullable=False)
    liczba_dni          = db.Column(db.Integer, nullable=False, default=0)
    
    efekt = db.relationship('EfektUczenia', lazy='select')


class IndywidualnyProgram(db.Model):
    __tablename__ = 'individual_programs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False, unique=True)
    status = db.Column(db.Enum(StatusDokumentu, name='program_status', values_callable=lambda e: [x.value for x in e]), nullable=False, default=StatusDokumentu.DRAFT)
    approved_by_uopz = db.Column(db.Boolean, default=False)
    approved_at = db.Column(db.DateTime, nullable=True)
    uopz_comments = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    # Relacje
    enrollment = db.relationship('ZapisPraktyki', backref='indywidualny_program')


class NumerPisma(db.Model):
    __tablename__ = 'document_numbers'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)  # 'ZALACZNIK_2'
    numer = db.Column(db.String(100), nullable=False)  # np. "ANS/PZ/2024/001"
    generated_at = db.Column(db.DateTime, server_default=db.func.now())

    # Relacje
    enrollment = db.relationship('ZapisPraktyki')


class Sprawozdanie(db.Model):
    __tablename__ = 'internship_reports'

    id                      = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id           = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False, unique=True)
    charakterystyka_miejsca = db.Column(db.Text, nullable=True)
    opis_i_analiza          = db.Column(db.Text, nullable=True)
    updated_at              = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())


class EfektUczenia(db.Model):
    __tablename__ = 'learning_outcomes'

    id          = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.Text, nullable=False)

    @property
    def opis(self): return self.description

    @property
    def kod(self): return str(self.id).zfill(2)


class WpisDziennika(db.Model):
    __tablename__ = 'journal_entries'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    entry_date          = db.Column(db.Date, nullable=False)
    duration_hours      = db.Column(db.Integer, nullable=False)
    description         = db.Column(db.Text, nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)

    efekt = db.relationship('EfektUczenia', lazy='select')

    @property
    def data_wpisu(self): return self.entry_date

    @property
    def liczba_godzin(self): return self.duration_hours

    @property
    def opis(self): return self.description

    @property
    def efekt_uczenia(self): return self.efekt


class OcenaPraktyki(db.Model):
    __tablename__ = 'internship_evaluations'

    id                  = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id       = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    learning_outcome_id = db.Column(db.Integer, db.ForeignKey('learning_outcomes.id'), nullable=False)
    result              = db.Column(db.Enum(WynikOceny, name='evaluation_result', values_callable=lambda e: [x.value for x in e]), nullable=False)
    evaluator_notes     = db.Column(db.Text, nullable=True)

    efekt = db.relationship('EfektUczenia', lazy='select')

    @property
    def wynik(self): return self.result
    @wynik.setter
    def wynik(self, v): self.result = v

    @property
    def uwagi_oceniajacego(self): return self.evaluator_notes
    @uwagi_oceniajacego.setter
    def uwagi_oceniajacego(self, v): self.evaluator_notes = v


class DocumentAuditLog(db.Model):
    __tablename__ = 'document_audit_logs'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='SET NULL'), nullable=True)
    document_type = db.Column(db.String(50), nullable=False) # e.g. Zalacznik_1, Zalacznik_8
    action = db.Column(db.String(50), nullable=False) # GENERATED_AUTO, EDITED_MANUAL, COMPILED_MANUAL
    details = db.Column(db.Text, nullable=True) # Could store diff or notes
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship('Uzytkownik')
    enrollment = db.relationship('ZapisPraktyki')


class UploadedDocument(db.Model):
    __tablename__ = 'uploaded_documents'

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id = db.Column(UUID(as_uuid=True), db.ForeignKey('internship_enrollments.id', ondelete='CASCADE'), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)  # 'umowa_pracy', 'zaswiadczenie_zatrudnienie', 'ceidg', 'krs' etc.
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)  # UUID-based name on disk
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)  # bytes
    mime_type = db.Column(db.String(100), nullable=False)
    uploaded_at = db.Column(db.DateTime, server_default=db.func.now())
    uploaded_by_id = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # Relacje
    enrollment = db.relationship('ZapisPraktyki', backref='uploaded_documents')
    uploaded_by = db.relationship('Uzytkownik')