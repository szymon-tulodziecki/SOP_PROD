"""core/szyfrowanie.py

Szyfrowanie plików przesyłanych przez studentów.

Format v2 (chunked AES-256-GCM) — obsługuje streaming deszyfrowania:
  Nagłówek: b'SOP1' + 4 bajty (chunk_size, big-endian uint32)
  Dla każdego chunku:
    4 bajty (długość zaszyfrowanego chunku, big-endian uint32)
    12 bajtów nonce (losowe, unikalne dla każdego chunku)
    N bajtów zaszyfrowanych danych + 16 bajtów tag GCM

Format v1 (Fernet, legacy) — rozpoznawany po braku nagłówka b'SOP1'.
Używany do odczytu istniejących plików; nowe pliki zawsze zapisywane jako v2.

Klucz pochodzi ze zmiennej środowiskowej FILE_ENCRYPTION_KEY (base64url, 32B).
"""
from __future__ import annotations

import os
import struct
import logging
from typing import Iterator

log = logging.getLogger(__name__)

MAGIC = b'SOP1'
CHUNK_SIZE = 64 * 1024
NONCE_SIZE = 12
TAG_SIZE = 16


# ── Klucz ────────────────────────────────────────────────────────────────────

def _get_key() -> bytes:
    """Zwraca 32-bajtowy klucz AES z sekretu 'file_encryption_key' (base64url)."""
    import base64
    from core.secrets import get_secret
    raw = get_secret('file_encryption_key')
    try:
        key = base64.urlsafe_b64decode(raw + '==')
        if len(key) >= 32:
            return key[:32]
    except Exception:
        pass
    raise RuntimeError(
        'Sekret file_encryption_key ma nieprawidłową wartość. '
        'Wymagany klucz base64url kodujący co najmniej 32 bajty.'
    )


_KEY: bytes | None = None


def _key() -> bytes:
    global _KEY
    if _KEY is None:
        _KEY = _get_key()
    return _KEY


# ── Szyfrowanie (v2 chunked) ──────────────────────────────────────────────────

def encrypt(data: bytes) -> bytes:
    """Szyfruje bajty — zwraca pełny token v2 (w pamięci, dla małych plików)."""
    return b''.join(_encrypt_chunks(iter([data])))


def encrypt_stream(source: Iterator[bytes]) -> Iterator[bytes]:
    """Generator: szyfruje dane strumieniowo chunk po chunk.

    source — iterator bajtów (np. file.read(CHUNK_SIZE) w pętli).
    Yields zaszyfrowane bajty gotowe do zapisu / przesłania.
    """
    yield from _encrypt_chunks(source)


def _encrypt_chunks(source: Iterator[bytes]) -> Iterator[bytes]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(_key())

    yield MAGIC
    yield struct.pack('>I', CHUNK_SIZE)

    buf = bytearray()
    for fragment in source:
        buf.extend(fragment)
        while len(buf) >= CHUNK_SIZE:
            chunk, buf = buf[:CHUNK_SIZE], buf[CHUNK_SIZE:]
            yield _encrypt_chunk(aesgcm, bytes(chunk))

    if buf:
        yield _encrypt_chunk(aesgcm, bytes(buf))


def _encrypt_chunk(aesgcm, plaintext: bytes) -> bytes:
    nonce = os.urandom(NONCE_SIZE)
    ct    = aesgcm.encrypt(nonce, plaintext, None)   # ct includes 16B tag
    blob  = nonce + ct
    return struct.pack('>I', len(blob)) + blob


# ── Deszyfrowanie ─────────────────────────────────────────────────────────────

def decrypt(token: bytes) -> bytes:
    """Odszyfrowuje token v2 lub v1 (Fernet) — zwraca plaintext w pamięci."""
    return b''.join(decrypt_stream(iter([token])))


def decrypt_stream(source: Iterator[bytes]) -> Iterator[bytes]:
    """Generator: odszyfrowuje strumieniowo.

    source — iterator zaszyfrowanych bajtów (np. chunki z httpx streaming).
    Yields odszyfrowane bajty.
    Obsługuje formaty v2 (SOP1) i v1 (Fernet) automatycznie.
    """
    buf = bytearray()

    def _read(n: int) -> bytes | None:
        while len(buf) < n:
            try:
                buf.extend(next(source))
            except StopIteration:
                return None
        chunk = bytes(buf[:n])
        del buf[:n]
        return chunk

    # Odczytaj pierwsze 4 bajty — magic lub Fernet
    magic = _read(4)
    if magic is None:
        return

    if magic != MAGIC:
        # v1 Fernet — wczytaj resztę i odszyfruj blokowo
        rest = bytearray(magic)
        for fragment in source:
            rest.extend(fragment)
        yield _decrypt_fernet(bytes(rest))
        return

    # v2: odczytaj chunk_size (nieużywany przy deszyfracji, ale w nagłówku)
    _read(4)   # chunk_size — zapisany dla przyszłych weryfikacji

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(_key())

    while True:
        len_bytes = _read(4)
        if len_bytes is None:
            break
        blob_len = struct.unpack('>I', len_bytes)[0]
        blob     = _read(blob_len)
        if blob is None:
            raise ValueError('Urwany strumień zaszyfrowanych danych')
        nonce     = blob[:NONCE_SIZE]
        ct_tag    = blob[NONCE_SIZE:]
        plaintext = aesgcm.decrypt(nonce, ct_tag, None)
        yield plaintext


def _decrypt_fernet(token: bytes) -> bytes:
    """Fernet (v1) — blokowe deszyfrowanie dla starszych plików."""
    from cryptography.fernet import Fernet
    from core.secrets import get_secret
    raw = get_secret('file_encryption_key', required=False)
    if raw:
        try:
            return Fernet(raw.encode()).decrypt(token)
        except Exception:
            pass
    raise ValueError('Nie można odszyfrować pliku v1 — nieprawidłowy klucz Fernet')
