"""core/secrets.py

Centralny loader sekretów.

Kolejność wyszukiwania (pierwsze trafienie wygrywa):
  1. /run/secrets/<name>   — Docker Secret (plik montowany przez daemon)
  2. {NAME}_FILE env var   — ścieżka do pliku (testy/dev bez Swarm)
  3. {NAME} env var        — bezpośrednia wartość (.env w dev)

Użycie:
    from core.secrets import get_secret, get_database_url

    SECRET_KEY = get_secret('secret_key')
    DB_URL     = get_database_url()
"""

from __future__ import annotations

import os
from pathlib import Path

_SECRETS_DIR = Path("/run/secrets")
_PLACEHOLDER_PREFIXES = ("CHANGE_ME", "changeme", "example", "password")


def _is_production() -> bool:
    return os.environ.get("FLASK_ENV", "").lower() == "production"


def _validate_secret(name: str, value: str) -> str:
    if not _is_production():
        return value

    stripped = (value or "").strip()
    if not stripped:
        raise RuntimeError(f"Sekret '{name}' jest pusty w środowisku produkcyjnym.")
    if any(stripped.startswith(prefix) for prefix in _PLACEHOLDER_PREFIXES):
        raise RuntimeError(f"Sekret '{name}' ma wartość przykładową w środowisku produkcyjnym.")
    if name == "secret_key" and len(stripped) < 32:
        raise RuntimeError("SECRET_KEY musi mieć co najmniej 32 znaki w środowisku produkcyjnym.")
    return stripped


def get_secret(name: str, *, required: bool = True, default: str = "") -> str:
    """Zwraca wartość sekretu `name` (lowercase, np. 'secret_key').

    Raises RuntimeError jeśli `required=True` i sekret jest niedostępny.
    """
    # 1. Docker Secret file
    candidate = _SECRETS_DIR / name
    if candidate.is_file():
        return _validate_secret(name, candidate.read_text())

    upper = name.upper()

    # 2. Pośrednia zmienna *_FILE wskazująca na plik
    file_env = os.environ.get(f"{upper}_FILE")
    if file_env:
        p = Path(file_env)
        if p.is_file():
            return _validate_secret(name, p.read_text())

    # 3. Bezpośrednia zmienna środowiskowa
    val = os.environ.get(upper, default)
    if not val and required:
        raise RuntimeError(
            f"Sekret '{name}' jest niedostępny. "
            f"Ustaw /run/secrets/{name}, {upper}_FILE lub {upper}."
        )
    if not val:
        return val
    return _validate_secret(name, val)


def get_database_url() -> str:
    """Zwraca SQLAlchemy DATABASE_URL.

    Jeśli DATABASE_URL jest ustawiony (np. w dev przez .env), używa go.
    W przeciwnym razie buduje URL z komponentów, czytając hasło z sekretu.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    user = os.environ.get("POSTGRES_USER", "ans_admin")
    password = get_secret("postgres_password")
    host = os.environ.get("POSTGRES_HOST", "db")
    port = os.environ.get("POSTGRES_PORT", "5432")
    dbname = os.environ.get("POSTGRES_DB", "ans_praktyki")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
