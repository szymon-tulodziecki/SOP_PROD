"""core/modele/praktyki.py

Modele domenowe: Praktyki, Zapisy, Harmonogram, Sprawozdania.
"""
import uuid
import enum

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property

from core.extensions import db


# ── Enumy dziedziny praktyk ───────────────────────────────────────────────────

class StatusPraktyki(enum.Enum):
    AKTYWNA   = 'ACTIVE'
    NIEAKTYWNA = 'INACTIVE'


class StatusZapisu(enum.Enum):
    OCZEKUJACY          = 'PENDING'
    OCZEKUJE_NA_AKCEPT  = 'AWAITING_APPROVAL'
    WERYFIKACJA_KOMISJI = 'COMMISSION_REVIEW'
    AKCEPTACJA_DZIEKANA = 'DEAN_APPROVAL'
    W_REALIZACJI        = 'IN_PROGRESS'
    ZAKONCZONA          = 'COMPLETED'
    ODRZUCONA           = 'REJECTED'


class SciezkaPraktyki(enum.Enum):
    STANDARDOWA         = 'STANDARD'
    ZATRUDNIENIE        = 'EMPLOYMENT'
    WLASNA_DZIALALNOSC  = 'OWN_BUSINESS'


# Aliasy dla istniejącego kodu (nie usuwać do pełnej migracji kontrolerów)
StatusPraktyki.ACTIVE   = StatusPraktyki.AKTYWNA
StatusPraktyki.INACTIVE = StatusPraktyki.NIEAKTYWNA
StatusZapisu.PENDING           = StatusZapisu.OCZEKUJACY
StatusZapisu.AWAITING_APPROVAL = StatusZapisu.OCZEKUJE_NA_AKCEPT
StatusZapisu.COMMISSION_REVIEW = StatusZapisu.WERYFIKACJA_KOMISJI
StatusZapisu.DEAN_APPROVAL     = StatusZapisu.AKCEPTACJA_DZIEKANA
StatusZapisu.IN_PROGRESS       = StatusZapisu.W_REALIZACJI
StatusZapisu.COMPLETED         = StatusZapisu.ZAKONCZONA
StatusZapisu.REJECTED          = StatusZapisu.ODRZUCONA
SciezkaPraktyki.STANDARD      = SciezkaPraktyki.STANDARDOWA
SciezkaPraktyki.EMPLOYMENT    = SciezkaPraktyki.ZATRUDNIENIE
SciezkaPraktyki.OWN_BUSINESS  = SciezkaPraktyki.WLASNA_DZIALALNOSC


# ── Modele ────────────────────────────────────────────────────────────────────

class Praktyka(db.Model):
    """Edycja praktyk — rok akademicki i semestr."""
    __tablename__ = 'praktyki'

    id             = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rok_uczelniany = db.Column(db.String(9),  nullable=False)   # np. '2024/2025'
    semestr        = db.Column(db.String(10), nullable=False)   # 'zimowy' / 'letni'
    wymiar_godzin  = db.Column(db.Integer, nullable=False, default=160)
    status         = db.Column(
        db.Enum(StatusPraktyki, name='status_praktyki', values_callable=lambda e: [x.value for x in e]),
        nullable=False, default=StatusPraktyki.NIEAKTYWNA,
    )
    utworzono = db.Column(db.DateTime, server_default=db.func.now())

    zapisy = db.relationship(
        'ZapisPraktyki', backref='praktyka',
        lazy='select', cascade='all, delete-orphan', passive_deletes=True,
    )


class ZapisPraktyki(db.Model):
    """Zgłoszenie studenta do konkretnej edycji praktyki."""
    __tablename__ = 'zapisy_praktyk'

    id           = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    praktyka_id  = db.Column(UUID(as_uuid=True), db.ForeignKey('praktyki.id',    ondelete='CASCADE'), nullable=False)
    student_id   = db.Column(UUID(as_uuid=True), db.ForeignKey('uzytkownicy.id', ondelete='CASCADE'), nullable=False)
    uopz_id      = db.Column(UUID(as_uuid=True), db.ForeignKey('uzytkownicy.id', ondelete='SET NULL'), nullable=True)
    firma_id     = db.Column(UUID(as_uuid=True), db.ForeignKey('firmy.id',       ondelete='SET NULL'), nullable=True)

    status    = db.Column(
        db.Enum(StatusZapisu, name='status_zapisu', values_callable=lambda e: [x.value for x in e]),
        nullable=False, default=StatusZapisu.OCZEKUJACY,
    )
    sciezka   = db.Column(
        'sciezka',
        db.Enum(SciezkaPraktyki, name='sciezka_praktyki', values_callable=lambda e: [x.value for x in e]),
        nullable=False, default=SciezkaPraktyki.STANDARDOWA,
    )

    # Terminy
    termin_od        = db.Column(db.Date,    nullable=True)
    termin_do        = db.Column(db.Date,    nullable=True)
    specjalnosc      = db.Column(db.String(255), nullable=True)
    ubezpieczenie_nw = db.Column(db.Boolean, default=False)

    # Dane zakładu (kopiowane z formularza do dokumentów TeX)
    firma_nazwa                  = db.Column(db.String(255), nullable=True)
    firma_adres                  = db.Column(db.String(255), nullable=True)
    firma_miasto                 = db.Column(db.String(255), nullable=True)
    firma_nip_krs                = db.Column(db.String(50),  nullable=True)
    firma_upowazniony_osoba      = db.Column(db.String(255), nullable=True)
    firma_upowazniony_stanowisko = db.Column(db.String(255), nullable=True)

    # Dane ZOPZ
    zopz_imie_nazwisko = db.Column(db.String(255), nullable=True)
    zopz_stanowisko    = db.Column(db.String(255), nullable=True)
    zopz_telefon       = db.Column(db.String(50),  nullable=True)
    zopz_email         = db.Column(db.String(255), nullable=True)

    # Ścieżki B/C
    uzasadnienie_sciezki = db.Column(db.Text, nullable=True)
    zalaczniki_sciezki   = db.Column(db.Text, nullable=True)

    # Oceny
    ocena_sprawozdania  = db.Column(db.Numeric(3, 1), nullable=True)
    ocena_uopz          = db.Column(db.Numeric(3, 1), nullable=True)
    ocena_zopz          = db.Column(db.Numeric(3, 1), nullable=True)
    ocena_opisowa_uopz  = db.Column(db.Text, nullable=True)
    ocena_opisowa_zopz  = db.Column(db.Text, nullable=True)

    # Sprawdzian
    sprawdzian_pytanie_1 = db.Column(db.Text,         nullable=True)
    sprawdzian_ocena_1   = db.Column(db.Numeric(3, 1), nullable=True)
    sprawdzian_pytanie_2 = db.Column(db.Text,         nullable=True)
    sprawdzian_ocena_2   = db.Column(db.Numeric(3, 1), nullable=True)
    sprawdzian_pytanie_3 = db.Column(db.Text,         nullable=True)
    sprawdzian_ocena_3   = db.Column(db.Numeric(3, 1), nullable=True)

    lacznie_godzin = db.Column('lacznie_godzin', db.Integer, default=0)
    zapisano_o     = db.Column('zapisano_o', db.DateTime, server_default=db.func.now())

    # Komentarze procesowe
    komentarze_admina       = db.Column('komentarze_admina',       db.Text)
    komentarze_uopz         = db.Column('komentarze_uopz',         db.Text)
    powiadomiono_studenta_o = db.Column('powiadomiono_studenta_o', db.DateTime)
    komentarze_komisji      = db.Column('komentarze_komisji',      db.Text)
    decyzja_komisji         = db.Column('decyzja_komisji',         db.String(20))
    decyzja_komisji_o       = db.Column('decyzja_komisji_o',       db.DateTime)
    komentarze_dziekana     = db.Column('komentarze_dziekana',     db.Text)
    decyzja_dziekana        = db.Column('decyzja_dziekana',        db.String(20))
    decyzja_dziekana_o      = db.Column('decyzja_dziekana_o',      db.DateTime)

    # Relacje
    student   = db.relationship('Uzytkownik', foreign_keys=[student_id], lazy='select')
    uopz      = db.relationship('Uzytkownik', foreign_keys=[uopz_id],    lazy='select')
    firma     = db.relationship('Firma',      foreign_keys=[firma_id],   lazy='select')
    wpisy_dziennika = db.relationship('WpisDziennika', backref='zapis', lazy='select', cascade='all, delete-orphan')
    oceny     = db.relationship('OcenaPraktyki', backref='zapis', lazy='select', cascade='all, delete-orphan')
    harmonogram = db.relationship('HarmonogramPraktyki', backref='zapis', lazy='select', cascade='all, delete-orphan')
    sprawozdanie = db.relationship('Sprawozdanie', backref='zapis', uselist=False, lazy='select', cascade='all, delete-orphan')

    # Compat — stare nazwy atrybutów (do usunięcia po migracji kontrolerów)
    @property
    def internship_id(self):
        return self.praktyka_id

    @internship_id.setter
    def internship_id(self, v):
        self.praktyka_id = v

    @property
    def track_type(self):
        return self.sciezka

    @track_type.setter
    def track_type(self, v):
        self.sciezka = v

    @hybrid_property
    def enrolled_at(self):
        return self.zapisano_o

    @enrolled_at.expression
    def enrolled_at(cls):
        return cls.zapisano_o

    @property
    def total_hours_logged(self):
        return self.lacznie_godzin

    # ── Obliczone oceny (hybrid) ──────────────────────────────────────────────

    @hybrid_property
    def ocena_e(self):
        """Średnia ze sprawdzianów (instancja)."""
        oceny = [
            float(v) for v in (
                self.sprawdzian_ocena_1,
                self.sprawdzian_ocena_2,
                self.sprawdzian_ocena_3,
            ) if v is not None
        ]
        return round(sum(oceny) / len(oceny), 2) if oceny else None

    @ocena_e.expression
    def ocena_e(cls):
        """Średnia ze sprawdzianów (SQL)."""
        from sqlalchemy import case, cast, func
        liczba = (
            case((cls.sprawdzian_ocena_1.isnot(None), 1), else_=0) +
            case((cls.sprawdzian_ocena_2.isnot(None), 1), else_=0) +
            case((cls.sprawdzian_ocena_3.isnot(None), 1), else_=0)
        )
        suma = (
            func.coalesce(cast(cls.sprawdzian_ocena_1, db.Float), 0) +
            func.coalesce(cast(cls.sprawdzian_ocena_2, db.Float), 0) +
            func.coalesce(cast(cls.sprawdzian_ocena_3, db.Float), 0)
        )
        return func.round(cast(suma / func.nullif(liczba, 0), db.Numeric(5, 2)), 2)

    @hybrid_property
    def ocena_k(self):
        """Ocena końcowa: 0.4E + 0.1S + 0.2U + 0.3Z."""
        e = self.ocena_e
        s = float(self.ocena_sprawozdania) if self.ocena_sprawozdania is not None else None
        u = float(self.ocena_uopz) if self.ocena_uopz is not None else None
        z = float(self.ocena_zopz) if self.ocena_zopz is not None else None
        if None in (e, s, u, z):
            return None
        return round(0.4 * e + 0.1 * s + 0.2 * u + 0.3 * z, 2)

    @ocena_k.expression
    def ocena_k(cls):
        from sqlalchemy import case, cast, func
        e = cls.ocena_e
        s = cast(cls.ocena_sprawozdania, db.Float)
        u = cast(cls.ocena_uopz, db.Float)
        z = cast(cls.ocena_zopz, db.Float)
        return case(
            (
                e.isnot(None) &
                cls.ocena_sprawozdania.isnot(None) &
                cls.ocena_uopz.isnot(None) &
                cls.ocena_zopz.isnot(None),
                func.round(cast(0.4 * e + 0.1 * s + 0.2 * u + 0.3 * z, db.Numeric(5, 2)), 2),
            ),
            else_=None,
        )


class HarmonogramPraktyki(db.Model):
    """Harmonogram realizacji efektów uczenia dla jednego zapisu."""
    __tablename__ = 'harmonogram_praktyk'

    id          = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id    = db.Column('zapis_id', UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False)
    efekt_id    = db.Column('efekt_id', db.Integer, db.ForeignKey('efekty_uczenia.id'), nullable=False)
    nazwa_dzialu      = db.Column(db.String(255), nullable=False)
    przykladowe_prace = db.Column(db.Text, nullable=False)
    liczba_dni        = db.Column(db.Integer, nullable=False, default=0)

    efekt = db.relationship('EfektUczenia', lazy='select')

    # Compat
    @property
    def enrollment_id(self):
        return self.zapis_id

    @enrollment_id.setter
    def enrollment_id(self, v):
        self.zapis_id = v

    @property
    def learning_outcome_id(self):
        return self.efekt_id

    @learning_outcome_id.setter
    def learning_outcome_id(self, v):
        self.efekt_id = v


class Sprawozdanie(db.Model):
    """Sprawozdanie studenta z odbytej praktyki."""
    __tablename__ = 'sprawozdania'

    id                      = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id                = db.Column('zapis_id', UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False, unique=True)
    charakterystyka_miejsca = db.Column(db.Text, nullable=True)
    opis_i_analiza          = db.Column(db.Text, nullable=True)
    zaktualizowano          = db.Column('zaktualizowano', db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    @property
    def enrollment_id(self):
        return self.zapis_id


class IndywidualnyProgram(db.Model):
    """Indywidualny program praktyki (opcjonalny)."""
    __tablename__ = 'programy_indywidualne'

    id           = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id     = db.Column('zapis_id', UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False, unique=True)
    status       = db.Column(db.String(30), nullable=False, default='DRAFT')
    zatwierdzony_przez_uopz = db.Column(db.Boolean, default=False)
    zatwierdzono_o = db.Column(db.DateTime, nullable=True)
    komentarz_uopz = db.Column(db.Text, nullable=True)
    utworzono    = db.Column(db.DateTime, server_default=db.func.now())

    zapis = db.relationship('ZapisPraktyki', backref=db.backref('indywidualny_program', passive_deletes=True))

    @property
    def enrollment_id(self):
        return self.zapis_id


class NumerPisma(db.Model):
    """Kolejny numer pisma administracyjnego dla dokumentu."""
    __tablename__ = 'numery_pism'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id      = db.Column('zapis_id', UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False)
    typ_dokumentu = db.Column('typ_dokumentu', db.String(50), nullable=False)
    numer         = db.Column(db.String(100), nullable=False)
    wygenerowano  = db.Column('wygenerowano', db.DateTime, server_default=db.func.now())

    zapis = db.relationship('ZapisPraktyki')

    @property
    def enrollment_id(self):
        return self.zapis_id

    @property
    def document_type(self):
        return self.typ_dokumentu
