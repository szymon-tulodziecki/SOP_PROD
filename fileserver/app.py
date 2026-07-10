"""
fileserver/app.py

Prosty serwer plików dostępny tylko na sieci wewnętrznej Docker.
Pliki trafiają tu już zaszyfrowane — serwer nie zna klucza szyfrowania.

API (chronione X-API-Key):
  PUT    /files/<filename>   — zapisz plik
  GET    /files/<filename>   — pobierz plik
  DELETE /files/<filename>   — usuń plik
"""

import hmac
import os
from pathlib import Path
from flask import Flask, request, Response, jsonify, abort

app = Flask(__name__)

STORAGE = Path("/data/files")
STORAGE.mkdir(parents=True, exist_ok=True)


def _load_secret(name: str) -> str:
    """Reads from /run/secrets/<name>, {NAME}_FILE, or {NAME} env var."""
    p = Path(f"/run/secrets/{name}")
    if p.is_file():
        return p.read_text().strip()
    file_env = os.environ.get(f"{name.upper()}_FILE")
    if file_env:
        fp = Path(file_env)
        if fp.is_file():
            return fp.read_text().strip()
    return os.environ.get(name.upper(), "")


API_KEY = _load_secret("fileserver_api_key")
if not API_KEY:
    raise RuntimeError(
        "Sekret 'fileserver_api_key' jest niedostępny. "
        "Ustaw /run/secrets/fileserver_api_key, FILESERVER_API_KEY_FILE lub FILESERVER_API_KEY."
    )


def _auth():
    provided = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(provided, API_KEY):
        abort(403)


@app.route("/health")
def health():
    return jsonify({"ok": True})


def _safe_dest(filename: str) -> Path:
    """Zwraca bezpieczną ścieżkę lub przerywa z HTTP 400 (Path Traversal)."""
    dest = (STORAGE / filename).resolve()
    if not dest.is_relative_to(STORAGE.resolve()):
        abort(400)
    return dest


@app.route("/files/<path:filename>", methods=["PUT"])
def upload(filename):
    _auth()
    dest = _safe_dest(filename)
    dest.write_bytes(request.get_data())
    return jsonify({"ok": True}), 201


@app.route("/files/<path:filename>", methods=["GET"])
def download(filename):
    _auth()
    dest = _safe_dest(filename)
    if not dest.exists():
        abort(404)
    return Response(dest.read_bytes(), mimetype="application/octet-stream")


@app.route("/files/<path:filename>", methods=["DELETE"])
def delete(filename):
    _auth()
    dest = _safe_dest(filename)
    if dest.exists():
        dest.unlink()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003)
