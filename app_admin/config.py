import os


class Config:
    # Podstawowe zabezpieczenie sesji i formularzy WTF (zmień na produkcji!)
    SECRET_KEY = os.environ.get('SECRET_KEY', 'super-tajny-klucz-tylko-na-dev-xd')

    # Konfiguracja połączenia z naszą bazą w kontenerze przy użyciu sterownika pg8000.
    # Uwaga: ponieważ na etapie dev odpalamy Flaska bezpośrednio na Windowsie,
    # uderzamy na localhost (port 5432, który Docker udostępnia na zewnątrz).
    # Docelowo, kiedy Flask trafi do swojego kontenera w docker-compose,
    # 'localhost' zostanie zastąpiony nazwą usługi bazy danych, czyli 'db'.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql+pg8000://ans_admin:secure_password_123@localhost:5432/ans_praktyki'
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