import os
from datetime import timedelta
from core.secrets import get_secret, get_database_url


class Config:
    SESSION_COOKIE_NAME = 'student_session'

    SECRET_KEY               = get_secret('secret_key')
    SQLALCHEMY_DATABASE_URI  = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    AZURE_CLIENT_ID     = get_secret('azure_client_id')
    AZURE_CLIENT_SECRET = get_secret('azure_client_secret')
    AZURE_TENANT_ID     = get_secret('azure_tenant_id')

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


CONFIGURATION_MAP = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
