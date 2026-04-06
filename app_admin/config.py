import os


class Config:
    # Osobne nazwy ciasteczek dla admina i studenta, żeby nie "nadpisywały się" nazzajem na localhost
    SESSION_COOKIE_NAME = 'admin_session'
    # Podstawowe zabezpieczenie sesji i formularzy WTF (zmień na produkcji!)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'super-tajny-klucz-tylko-na-dev-xd')

    # Konfiguracja połączenia z bazą danych — sterownik psycopg2 (C, wydajny)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql+psycopg2://ans_admin:secure_password_123@localhost:5432/ans_praktyki'
    )

    # Wyłączamy system zdarzeń SQLAlchemy, którego nie używamy (oszczędza pamięć)
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True
    ENV = 'development'


class ProductionConfig(Config):
    DEBUG = False
    ENV = 'production'
    # Na produkcji wymusimy silniejsze zabezpieczenia ciasteczek (tylko HTTPS)
    SESSION_COOKIE_SECURE = True


# Słownik ułatwiający Fabryce Aplikacji wybór odpowiedniej klasy
config_dict = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}