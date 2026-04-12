"""
fileserver/app.py

Prosty serwer plików dostępny tylko na sieci wewnętrznej Docker.
Pliki trafiają tu już zaszyfrowane — serwer nie zna klucza szyfrowania.

API (chronione X-API-Key):
  PUT    /files/<filename>   — zapisz plik
  GET    /files/<filename>   — pobierz plik
  DELETE /files/<filename>   — usuń plik
"""
import os
from pathlib import Path
from flask import Flask, request, Response, jsonify, abort

app = Flask(__name__)

STORAGE = Path('/data/files')
STORAGE.mkdir(parents=True, exist_ok=True)

API_KEY = os.environ.get('FILESERVER_API_KEY', '')


def _auth():
    if request.headers.get('X-API-Key') != API_KEY:
        abort(403)


@app.route('/health')
def health():
    return jsonify({'ok': True})


@app.route('/files/<path:filename>', methods=['PUT'])
def upload(filename):
    _auth()
    dest = STORAGE / filename
    dest.write_bytes(request.get_data())
    return jsonify({'ok': True}), 201


@app.route('/files/<path:filename>', methods=['GET'])
def download(filename):
    _auth()
    dest = STORAGE / filename
    if not dest.exists():
        abort(404)
    return Response(dest.read_bytes(), mimetype='application/octet-stream')


@app.route('/files/<path:filename>', methods=['DELETE'])
def delete(filename):
    _auth()
    dest = STORAGE / filename
    if dest.exists():
        dest.unlink()
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)
