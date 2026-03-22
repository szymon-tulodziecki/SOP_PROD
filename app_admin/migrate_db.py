import sys
import os

from app_admin.extensions import db
from sqlalchemy import text
from app_admin import create_app

app = create_app()

with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE users ADD COLUMN wymagana_zmiana_hasla BOOLEAN DEFAULT TRUE'))
        db.session.commit()
    except Exception as e:
        print("users:", e)
        db.session.rollback()

    try:
        db.session.execute(text('ALTER TABLE companies ADD COLUMN zatwierdzone BOOLEAN DEFAULT TRUE'))
        db.session.execute(text('ALTER TABLE companies ADD COLUMN dodane_przez_id UUID REFERENCES users(id)'))
        db.session.commit()
    except Exception as e:
        print("companies:", e)
        db.session.rollback()

    try:
        db.session.execute(text('ALTER TABLE internships ADD COLUMN zopz_imie VARCHAR(100)'))
        db.session.execute(text('ALTER TABLE internships ADD COLUMN zopz_nazwisko VARCHAR(100)'))
        db.session.execute(text('ALTER TABLE internships ADD COLUMN zopz_stanowisko VARCHAR(255)'))
        db.session.execute(text('ALTER TABLE internships ADD COLUMN zopz_email VARCHAR(255)'))
        db.session.execute(text('ALTER TABLE internships ADD COLUMN zopz_telefon VARCHAR(30)'))
        db.session.execute(text('ALTER TABLE internships ADD COLUMN zaklad_wymaga_zatwierdzenia BOOLEAN DEFAULT FALSE'))
    except Exception as e:
        print("internships add:", e)
        db.session.rollback()

    try:
        db.session.execute(text('ALTER TABLE internships DROP COLUMN zopz_id'))
        db.session.commit()
    except Exception as e:
        print("internships drop:", e)
        db.session.rollback()

print("Baza danych zaktualizowana.")
