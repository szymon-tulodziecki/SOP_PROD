import os
from datetime import timedelta


class Config:
    # Osobne nazwy ciasteczek dla admina i studenta
    SESSION_COOKIE_NAME = 'student_session'

    # Podstawowe zabezpieczenie sesji i formularzy WTF
    SECRET_KEY = os.environ.get('SECRET_KEY', 'student-tajny-klucz-tylko-na-dev-xd')

    # Konfiguracja połączenia z bazą danych
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'postgresql+pg8000://ans_admin:secure_password_123@localhost:5432/ans_praktyki'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # External services
    TEX_SERVICE_URL = os.environ.get('TEX_SERVICE_URL', 'http://tex-service:5002')

    # Security
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None


class DevelopmentConfig(Config):
    DEBUG = True
    ENV = 'development'


class ProductionConfig(Config):
    DEBUG = False
    ENV = 'production'
    SESSION_COOKIE_SECURE = True


config_dict = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
