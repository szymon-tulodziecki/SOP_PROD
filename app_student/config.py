import os
from datetime import timedelta


def _require(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(
            f"Zmienna środowiskowa {name!r} nie jest ustawiona. "
            "Uzupełnij plik .env lub zmienne środowiskowe kontenera."
        )
    return v


class Config:
    # Osobne nazwy ciasteczek dla admina i studenta
    SESSION_COOKIE_NAME = 'student_session'

    SECRET_KEY               = _require('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI  = _require('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Microsoft Entra ID (Azure AD) — OAuth 2.0
    AZURE_CLIENT_ID     = _require('AZURE_CLIENT_ID')
    AZURE_CLIENT_SECRET = _require('AZURE_CLIENT_SECRET')
    AZURE_TENANT_ID     = _require('AZURE_TENANT_ID')

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # External services
    TEX_SERVICE_URL = os.environ.get('TEX_SERVICE_URL', 'http://tex-service:5002')

    # Rate limiting (flask-limiter + Redis)
    RATELIMIT_STORAGE_URI = os.environ.get('CELERY_BROKER_URL', os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))

    # Security
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None


class DevelopmentConfig(Config):
    DEBUG = True
    ENV = 'development'


class ProductionConfig(Config):
    DEBUG = False
    ENV = 'production'
    SESSION_COOKIE_SECURE   = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'


config_dict = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
