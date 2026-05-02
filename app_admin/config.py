import os
from core.secrets import get_secret, get_database_url


class Config:
    SESSION_COOKIE_NAME = 'admin_session'

    SECRET_KEY               = get_secret('secret_key')
    SQLALCHEMY_DATABASE_URI  = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    AZURE_CLIENT_ID     = get_secret('azure_client_id')
    AZURE_CLIENT_SECRET = get_secret('azure_client_secret')
    AZURE_TENANT_ID     = get_secret('azure_tenant_id')

    RATELIMIT_STORAGE_URI = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    TEX_SERVICE_URL  = os.environ['TEX_SERVICE_URL']
    FILESERVER_URL   = os.environ['FILESERVER_URL']


class DevelopmentConfig(Config):
    DEBUG = True
    ENV = 'development'


class ProductionConfig(Config):
    DEBUG = False
    ENV = 'production'
    SESSION_COOKIE_SECURE   = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'

CONFIGURATION_MAP = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
