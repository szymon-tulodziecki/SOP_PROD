"""Shared configuration base for admin and student Flask apps.

Each app extends BaseConfig with its own session cookie name and config map.
Sensitive values come from Docker Swarm secrets via core.secrets — never
from environment or .env files in production.
"""
from __future__ import annotations

import os

from core.secrets import get_database_url, get_secret


class BaseConfig:
    """Configuration shared by all Flask apps in the SOP system."""

    SECRET_KEY = get_secret('secret_key')
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    AZURE_CLIENT_ID = get_secret('azure_client_id')
    AZURE_CLIENT_SECRET = get_secret('azure_client_secret')
    AZURE_TENANT_ID = get_secret('azure_tenant_id')

    TEX_SERVICE_URL = os.environ['TEX_SERVICE_URL']
    FILESERVER_URL = os.environ['FILESERVER_URL']

    RATELIMIT_STORAGE_URI = os.environ.get(
        'CELERY_BROKER_URL',
        os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
    )

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None


class DevelopmentMixin:
    DEBUG = True
    ENV = 'development'


class ProductionMixin:
    DEBUG = False
    ENV = 'production'
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'


def make_config_map(base: type) -> dict:
    """Builds the {env: config_class} map for a given app's BaseConfig subclass."""
    dev = type('DevelopmentConfig', (DevelopmentMixin, base), {})
    prod = type('ProductionConfig', (ProductionMixin, base), {})
    return {'development': dev, 'production': prod, 'default': dev}
