"""core/modele/praktyki.py

Modele domenowe: Praktyki, Zapisy i powiązane encje satelitarne.
"""
import uuid
import enum

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property

from core.extensions import db


# ── Enumy dziedziny praktyk ───────────────────────────────────────────────────

class StatusPraktyki(enum.Enum):
    AKTYWNA    = 'ACTIVE'
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
    STANDARDOWA        = 'STANDARD'
    ZATRUDNIENIE       = 'EMPLOYMENT'
    WLASNA_DZIALALNOSC = 'OWN_BUSINESS'


class TypZdarzenia(enum.Enum):
    ADMIN_KOMENTARZ        = 'ADMIN_KOMENTARZ'
    UOPZ_KOMENTARZ         = 'UOPZ_KOMENTARZ'
    POWIADOMIENIE_STUDENTA = 'POWIADOMIENIE_STUDENTA'
    KOMISJA_DECYZJA        = 'KOMISJA_DECYZJA'
    DZIEKAN_DECYZJA        = 'DZIEKAN_DECYZJA'


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
    rok_uczelniany = db.Column(db.String(9),  nullable=False)
    semestr        = db.Column(db.String(10), nullable=False)
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
    """Rdzeń zgłoszenia studenta do edycji praktyki."""
    __tablename__ = 'zapisy_praktyk'

    id          = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    praktyka_id = db.Column(UUID(as_uuid=True), db.ForeignKey('praktyki.id',    ondelete='CASCADE'), nullable=False)
    student_id  = db.Column(UUID(as_uuid=True), db.ForeignKey('uzytkownicy.id', ondelete='CASCADE'), nullable=False)
    uopz_id     = db.Column(UUID(as_uuid=True), db.ForeignKey('uzytkownicy.id', ondelete='SET NULL'), nullable=True)
    firma_id    = db.Column(UUID(as_uuid=True), db.ForeignKey('firmy.id',       ondelete='SET NULL'), nullable=True)

    status  = db.Column(
        db.Enum(StatusZapisu, name='status_zapisu', values_callable=lambda e: [x.value for x in e]),
        nullable=False, default=StatusZapisu.OCZEKUJACY,
    )
    sciezka = db.Column(
        db.Enum(SciezkaPraktyki, name='sciezka_praktyki', values_callable=lambda e: [x.value for x in e]),
        nullable=False, default=SciezkaPraktyki.STANDARDOWA,
    )

    termin_od        = db.Column(db.Date,        nullable=True)
    termin_do        = db.Column(db.Date,        nullable=True)
    specjalnosc      = db.Column(db.String(255), nullable=True)
    ubezpieczenie_nw = db.Column(db.Boolean,     default=False)

    lacznie_godzin = db.Column(db.Integer,  default=0)
    zapisano_o     = db.Column(db.DateTime, server_default=db.func.now())

    # ── Relacje do encji satelitarnych ────────────────────────
    student            = db.relationship('Uzytkownik',          foreign_keys=[student_id], lazy='select')
    uopz               = db.relationship('Uzytkownik',          foreign_keys=[uopz_id],    lazy='select')
    firma              = db.relationship('Firma',               foreign_keys=[firma_id],   lazy='select')
    dane_miejsca       = db.relationship('DaneMiejscaPraktyki', back_populates='zapis',    uselist=False, cascade='all, delete-orphan')
    uzasadnienie       = db.relationship('UzasadnienieSciezki', back_populates='zapis',    uselist=False, cascade='all, delete-orphan')
    sprawdzian         = db.relationship('Sprawdzian',          back_populates='zapis',    uselist=False, cascade='all, delete-orphan')
    oceny_koncowe      = db.relationship('OcenyKoncowe',        back_populates='zapis',    uselist=False, cascade='all, delete-orphan')
    zdarzenia          = db.relationship('ZdarzenieProces',     back_populates='zapis',    lazy='select', cascade='all, delete-orphan', order_by='ZdarzenieProces.wykonano_o')
    wpisy_dziennika    = db.relationship('WpisDziennika',       backref='zapis',           lazy='select', cascade='all, delete-orphan')
    oceny              = db.relationship('OcenaPraktyki',       backref='zapis',           lazy='select', cascade='all, delete-orphan')
    harmonogram        = db.relationship('HarmonogramPraktyki', backref='zapis',           lazy='select', cascade='all, delete-orphan')
    sprawozdanie       = db.relationship('Sprawozdanie',        backref='zapis',           uselist=False, lazy='select', cascade='all, delete-orphan')

    # ── Compat — stare nazwy atrybutów ───────────────────────
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

    # ── Skróty do odczytu danych z encji satelitarnych (compat dla g() i szablonów) ──

    # dane_miejsca
    @property
    def firma_nazwa(self): return self.dane_miejsca.firma_nazwa if self.dane_miejsca else None
    @property
    def firma_adres(self): return self.dane_miejsca.firma_adres if self.dane_miejsca else None
    @property
    def firma_miasto(self): return self.dane_miejsca.firma_miasto if self.dane_miejsca else None
    @property
    def firma_nip_krs(self): return self.dane_miejsca.firma_nip_krs if self.dane_miejsca else None
    @property
    def firma_upowazniony_osoba(self): return self.dane_miejsca.firma_upowazniony_osoba if self.dane_miejsca else None
    @property
    def firma_upowazniony_stanowisko(self): return self.dane_miejsca.firma_upowazniony_stanowisko if self.dane_miejsca else None
    @property
    def zopz_imie_nazwisko(self): return self.dane_miejsca.zopz_imie_nazwisko if self.dane_miejsca else None
    @property
    def zopz_stanowisko(self): return self.dane_miejsca.zopz_stanowisko if self.dane_miejsca else None
    @property
    def zopz_telefon(self): return self.dane_miejsca.zopz_telefon if self.dane_miejsca else None
    @property
    def zopz_email(self): return self.dane_miejsca.zopz_email if self.dane_miejsca else None

    # uzasadnienie ścieżki
    @property
    def uzasadnienie_sciezki(self): return self.uzasadnienie.uzasadnienie if self.uzasadnienie else None
    @property
    def zalaczniki_sciezki(self): return self.uzasadnienie.zalaczniki if self.uzasadnienie else None

    # oceny końcowe
    @property
    def ocena_sprawozdania(self): return self.oceny_koncowe.ocena_sprawozdania if self.oceny_koncowe else None
    @property
    def ocena_uopz(self): return self.oceny_koncowe.ocena_uopz if self.oceny_koncowe else None
    @property
    def ocena_zopz(self): return self.oceny_koncowe.ocena_zopz if self.oceny_koncowe else None
    @property
    def ocena_opisowa_uopz(self): return self.oceny_koncowe.ocena_opisowa_uopz if self.oceny_koncowe else None
    @property
    def ocena_opisowa_zopz(self): return self.oceny_koncowe.ocena_opisowa_zopz if self.oceny_koncowe else None

    # sprawdzian
    @property
    def sprawdzian_pytanie_1(self): return self.sprawdzian.pytanie_1 if self.sprawdzian else None
    @property
    def sprawdzian_ocena_1(self): return self.sprawdzian.ocena_1 if self.sprawdzian else None
    @property
    def sprawdzian_pytanie_2(self): return self.sprawdzian.pytanie_2 if self.sprawdzian else None
    @property
    def sprawdzian_ocena_2(self): return self.sprawdzian.ocena_2 if self.sprawdzian else None
    @property
    def sprawdzian_pytanie_3(self): return self.sprawdzian.pytanie_3 if self.sprawdzian else None
    @property
    def sprawdzian_ocena_3(self): return self.sprawdzian.ocena_3 if self.sprawdzian else None

    # ── Skróty do danych procesowych (odczytywane z event log) ───────────────

    def _ostatnie_zdarzenie(self, typ: TypZdarzenia):
        return next(
            (z for z in reversed(self.zdarzenia) if z.typ == typ),
            None,
        )

    @property
    def decyzja_komisji(self):
        z = self._ostatnie_zdarzenie(TypZdarzenia.KOMISJA_DECYZJA)
        return z.decyzja if z else None

    @property
    def komentarze_komisji(self):
        z = self._ostatnie_zdarzenie(TypZdarzenia.KOMISJA_DECYZJA)
        return z.komentarz if z else None

    @property
    def decyzja_komisji_o(self):
        z = self._ostatnie_zdarzenie(TypZdarzenia.KOMISJA_DECYZJA)
        return z.wykonano_o if z else None

    @property
    def decyzja_dziekana(self):
        z = self._ostatnie_zdarzenie(TypZdarzenia.DZIEKAN_DECYZJA)
        return z.decyzja if z else None

    @property
    def komentarze_dziekana(self):
        z = self._ostatnie_zdarzenie(TypZdarzenia.DZIEKAN_DECYZJA)
        return z.komentarz if z else None

    @property
    def decyzja_dziekana_o(self):
        z = self._ostatnie_zdarzenie(TypZdarzenia.DZIEKAN_DECYZJA)
        return z.wykonano_o if z else None

    @property
    def komentarze_admina(self):
        z = self._ostatnie_zdarzenie(TypZdarzenia.ADMIN_KOMENTARZ)
        return z.komentarz if z else None

    @property
    def komentarze_uopz(self):
        z = self._ostatnie_zdarzenie(TypZdarzenia.UOPZ_KOMENTARZ)
        return z.komentarz if z else None

    @property
    def powiadomiono_studenta_o(self):
        z = self._ostatnie_zdarzenie(TypZdarzenia.POWIADOMIENIE_STUDENTA)
        return z.wykonano_o if z else None

    # ── Oceny (przez encję OcenyKoncowe i Sprawdzian) ────────────────────────

    @hybrid_property
    def ocena_e(self):
        """Średnia ze sprawdzianu (instancja)."""
        if self.sprawdzian is None:
            return None
        oceny = [
            float(v) for v in (
                self.sprawdzian.ocena_1,
                self.sprawdzian.ocena_2,
                self.sprawdzian.ocena_3,
            ) if v is not None
        ]
        return round(sum(oceny) / len(oceny), 2) if oceny else None

    @hybrid_property
    def ocena_k(self):
        """Ocena końcowa: 0.4E + 0.1S + 0.2U + 0.3Z."""
        if self.oceny_koncowe is None:
            return None
        e = self.ocena_e
        s = float(self.oceny_koncowe.ocena_sprawozdania) if self.oceny_koncowe.ocena_sprawozdania is not None else None
        u = float(self.oceny_koncowe.ocena_uopz)         if self.oceny_koncowe.ocena_uopz         is not None else None
        z = float(self.oceny_koncowe.ocena_zopz)         if self.oceny_koncowe.ocena_zopz         is not None else None
        if None in (e, s, u, z):
            return None
        return round(0.4 * e + 0.1 * s + 0.2 * u + 0.3 * z, 2)


# ── Encje satelitarne zapisu ──────────────────────────────────────────────────

class DaneMiejscaPraktyki(db.Model):
    """Snapshot danych zakładu i ZOPZ kopiowany z formularza do dokumentów TeX."""
    __tablename__ = 'dane_miejsca_praktyki'

    id       = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id = db.Column(UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False, unique=True)

    firma_nazwa                  = db.Column(db.String(255), nullable=True)
    firma_adres                  = db.Column(db.String(255), nullable=True)
    firma_miasto                 = db.Column(db.String(255), nullable=True)
    firma_nip_krs                = db.Column(db.String(50),  nullable=True)
    firma_upowazniony_osoba      = db.Column(db.String(255), nullable=True)
    firma_upowazniony_stanowisko = db.Column(db.String(255), nullable=True)

    zopz_imie_nazwisko = db.Column(db.String(255), nullable=True)
    zopz_stanowisko    = db.Column(db.String(255), nullable=True)
    zopz_telefon       = db.Column(db.String(50),  nullable=True)
    zopz_email         = db.Column(db.String(255), nullable=True)

    zapis = db.relationship('ZapisPraktyki', back_populates='dane_miejsca')


class UzasadnienieSciezki(db.Model):
    """Uzasadnienie wyboru ścieżki B lub C (opcjonalne)."""
    __tablename__ = 'uzasadnienia_sciezki'

    id           = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id     = db.Column(UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False, unique=True)
    uzasadnienie = db.Column(db.Text, nullable=True)
    zalaczniki   = db.Column(db.Text, nullable=True)

    zapis = db.relationship('ZapisPraktyki', back_populates='uzasadnienie')


class Sprawdzian(db.Model):
    """Trzy pytania sprawdzające z ocenami (wystawiane przez UOPZ)."""
    __tablename__ = 'sprawdziany'

    id       = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id = db.Column(UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False, unique=True)

    pytanie_1 = db.Column(db.Text,          nullable=True)
    ocena_1   = db.Column(db.Numeric(3, 1), nullable=True)
    pytanie_2 = db.Column(db.Text,          nullable=True)
    ocena_2   = db.Column(db.Numeric(3, 1), nullable=True)
    pytanie_3 = db.Column(db.Text,          nullable=True)
    ocena_3   = db.Column(db.Numeric(3, 1), nullable=True)

    zapis = db.relationship('ZapisPraktyki', back_populates='sprawdzian')


class OcenyKoncowe(db.Model):
    """Oceny składowe finalne praktyki."""
    __tablename__ = 'oceny_koncowe'

    id       = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id = db.Column(UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False, unique=True)

    ocena_sprawozdania = db.Column(db.Numeric(3, 1), nullable=True)
    ocena_uopz         = db.Column(db.Numeric(3, 1), nullable=True)
    ocena_zopz         = db.Column(db.Numeric(3, 1), nullable=True)
    ocena_opisowa_uopz = db.Column(db.Text,          nullable=True)
    ocena_opisowa_zopz = db.Column(db.Text,          nullable=True)

    zapis = db.relationship('ZapisPraktyki', back_populates='oceny_koncowe')


class ZdarzenieProces(db.Model):
    """Event log przepływu pracy: komentarze, decyzje komisji i dziekana."""
    __tablename__ = 'zdarzenia_procesowe'

    id       = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id = db.Column(UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False)
    typ      = db.Column(
        db.Enum(TypZdarzenia, name='typ_zdarzenia', values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    decyzja           = db.Column(db.String(20), nullable=True)   # 'APPROVED' / 'REJECTED'
    komentarz         = db.Column(db.Text,       nullable=True)
    wykonane_przez_id = db.Column(UUID(as_uuid=True), db.ForeignKey('uzytkownicy.id', ondelete='SET NULL'), nullable=True)
    wykonano_o        = db.Column(db.DateTime,   server_default=db.func.now())

    zapis            = db.relationship('ZapisPraktyki',  back_populates='zdarzenia')
    wykonane_przez   = db.relationship('Uzytkownik',     foreign_keys=[wykonane_przez_id], lazy='select')


# ── Pozostałe modele ──────────────────────────────────────────────────────────

class HarmonogramPraktyki(db.Model):
    """Harmonogram realizacji efektów uczenia dla jednego zapisu."""
    __tablename__ = 'harmonogram_praktyk'

    id                = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id          = db.Column(UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False)
    efekt_id          = db.Column(db.Integer, db.ForeignKey('efekty_uczenia.id'), nullable=False)
    nazwa_dzialu      = db.Column(db.String(255), nullable=False)
    przykladowe_prace = db.Column(db.Text,        nullable=False)
    liczba_dni        = db.Column(db.Integer,     nullable=False, default=0)

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
    zapis_id                = db.Column(UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False, unique=True)
    charakterystyka_miejsca = db.Column(db.Text,     nullable=True)
    opis_i_analiza          = db.Column(db.Text,     nullable=True)
    zaktualizowano          = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    @property
    def enrollment_id(self):
        return self.zapis_id


class IndywidualnyProgram(db.Model):
    """Indywidualny program praktyki (opcjonalny)."""
    __tablename__ = 'programy_indywidualne'

    id                      = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id                = db.Column(UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False, unique=True)
    status                  = db.Column(db.String(30), nullable=False, default='DRAFT')
    zatwierdzony_przez_uopz = db.Column(db.Boolean,   default=False)
    zatwierdzono_o          = db.Column(db.DateTime,   nullable=True)
    komentarz_uopz          = db.Column(db.Text,       nullable=True)
    utworzono               = db.Column(db.DateTime,   server_default=db.func.now())

    zapis = db.relationship('ZapisPraktyki', backref=db.backref('indywidualny_program', passive_deletes=True))

    @property
    def enrollment_id(self):
        return self.zapis_id


class NumerPisma(db.Model):
    """Kolejny numer pisma administracyjnego dla dokumentu."""
    __tablename__ = 'numery_pism'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id      = db.Column(UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False)
    typ_dokumentu = db.Column(db.String(50),  nullable=False)
    numer         = db.Column(db.String(100), nullable=False)
    wygenerowano  = db.Column(db.DateTime,    server_default=db.func.now())

    zapis = db.relationship('ZapisPraktyki')

    @property
    def enrollment_id(self):
        return self.zapis_id

    @property
    def document_type(self):
        return self.typ_dokumentu
