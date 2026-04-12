import os


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
    SESSION_COOKIE_NAME = 'admin_session'

    SECRET_KEY               = _require('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI  = _require('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Microsoft Entra ID (Azure AD) — OAuth 2.0
    AZURE_CLIENT_ID     = _require('AZURE_CLIENT_ID')
    AZURE_CLIENT_SECRET = _require('AZURE_CLIENT_SECRET')
    AZURE_TENANT_ID     = _require('AZURE_TENANT_ID')


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