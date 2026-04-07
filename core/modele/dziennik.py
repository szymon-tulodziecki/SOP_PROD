"""core/modele/dziennik.py

Modele domenowe: Dziennik praktyki, Efekty uczenia, Oceny.
"""
import uuid
import enum

from sqlalchemy.dialects.postgresql import UUID
from core.extensions import db


class WynikOceny(enum.Enum):
    OSIAGNIETO     = 'ACHIEVED'
    CZESCIOWO      = 'PARTIALLY_ACHIEVED'
    NIE_OSIAGNIETO = 'NOT_ACHIEVED'


class EfektUczenia(db.Model):
    """Efekty uczenia się — słownik (tabela referencyjna)."""
    __tablename__ = 'efekty_uczenia'

    id   = db.Column(db.Integer, primary_key=True)
    opis = db.Column('opis', db.Text, nullable=False)

    # Compat
    @property
    def description(self):
        return self.opis

    @property
    def kod(self) -> str:
        return str(self.id).zfill(2)


# Tabela asocjacyjna: wpis ↔ efekty
wpisy_efekty = db.Table(
    'wpisy_efekty',
    db.Column(
        'wpis_id',
        UUID(as_uuid=True),
        db.ForeignKey('wpisy_dziennika.id', ondelete='CASCADE'),
        primary_key=True,
    ),
    db.Column(
        'efekt_id',
        db.Integer,
        db.ForeignKey('efekty_uczenia.id'),
        primary_key=True,
    ),
)


class WpisDziennika(db.Model):
    """Pojedynczy wpis w dzienniku praktyki studenta."""
    __tablename__ = 'wpisy_dziennika'

    id            = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id      = db.Column('zapis_id', UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False)
    data_wpisu    = db.Column('data_wpisu', db.Date, nullable=False)
    liczba_godzin = db.Column('liczba_godzin', db.Integer, nullable=False)
    opis          = db.Column('opis', db.Text, nullable=False)

    efekty_uczenia = db.relationship('EfektUczenia', secondary=wpisy_efekty, lazy='subquery')

    # Compat
    @property
    def enrollment_id(self):
        return self.zapis_id

    @property
    def entry_date(self):
        return self.data_wpisu

    @property
    def duration_hours(self):
        return self.liczba_godzin

    @property
    def description(self):
        return self.opis


class OcenaPraktyki(db.Model):
    """Ocena osiągnięcia efektu uczenia dla jednego zapisu."""
    __tablename__ = 'oceny_praktyk'

    id       = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zapis_id = db.Column('zapis_id', UUID(as_uuid=True), db.ForeignKey('zapisy_praktyk.id', ondelete='CASCADE'), nullable=False)
    efekt_id = db.Column('efekt_id', db.Integer, db.ForeignKey('efekty_uczenia.id'), nullable=False)
    wynik    = db.Column(
        'wynik',
        db.Enum(WynikOceny, name='wynik_oceny', values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    uwagi = db.Column('uwagi', db.Text, nullable=True)

    efekt = db.relationship('EfektUczenia', lazy='select')

    # Compat
    @property
    def enrollment_id(self):
        return self.zapis_id

    @property
    def learning_outcome_id(self):
        return self.efekt_id

    @property
    def result(self):
        return self.wynik

    @result.setter
    def result(self, v):
        self.wynik = v

    @property
    def evaluator_notes(self):
        return self.uwagi

    @evaluator_notes.setter
    def evaluator_notes(self, v):
        self.uwagi = v
