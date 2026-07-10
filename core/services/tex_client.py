"""Wspólny klient tex_service — jedyne miejsce z adresem, timeoutami i obsługą
błędów HTTP. Używany przez oba appy webowe i taski Celery.

Użycie:
    from core.services.tex_client import TexServiceError, generuj_pdf
    pdf = generuj_pdf('zal8_protokol.tex.j2', context, filename='zal8_protokol.pdf')
"""
from __future__ import annotations

import os
import unicodedata
from urllib.parse import quote

import httpx

_MIME_PDF = 'application/pdf'


class TexServiceError(Exception):
    """tex_service zwrócił błąd albo jest nieosiągalny.

    status_code — kod HTTP odpowiedzi (None gdy połączenie w ogóle nie doszło),
    error_detail — treść pola 'error' z JSON-owej odpowiedzi błędu (jeśli była).
    """

    def __init__(self, message: str, status_code: int | None = None,
                 error_detail: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_detail = error_detail


def generuj_pdf(template: str, context: dict, filename: str | None = None,
                timeout: float = 60.0) -> bytes:
    """Kompiluje nazwany szablon w tex_service i zwraca bajty PDF.

    Rzuca TexServiceError zarówno przy odpowiedzi != 200, jak i przy braku
    połączenia — rozróżnienie po `status_code` wyjątku.
    """
    payload: dict = {'template': template, 'context': context}
    if filename:
        payload['filename'] = filename
    try:
        resp = httpx.post(
            f"{os.environ['TEX_SERVICE_URL']}/generuj",
            json=payload,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise TexServiceError(str(exc)) from exc

    if resp.status_code != 200:
        detail = None
        if 'application/json' in resp.headers.get('content-type', ''):
            try:
                detail = resp.json().get('error')
            except ValueError:
                pass
        raise TexServiceError(
            f'tex_service zwrócił {resp.status_code} dla {template}',
            status_code=resp.status_code,
            error_detail=detail,
        )
    return resp.content


def dyspozycja_pdf(base_name: str, last_name: str | None = None) -> str:
    """Nagłówek Content-Disposition zgodny z RFC 6266/5987 (polskie znaki).

    Bez last_name zwraca prostą wersję `attachment; filename="base_name"`.
    """
    if last_name is None:
        return f'attachment; filename="{base_name}"'
    full_name = f"{base_name}_{last_name}.pdf"
    ascii_fallback = (
        unicodedata.normalize('NFKD', full_name)
        .encode('ascii', 'ignore').decode('ascii')
        .strip() or 'dokument.pdf'
    )
    utf8_encoded = quote(full_name, safe='')
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{utf8_encoded}"


def odpowiedz_pdf(pdf: bytes, disposition: str):
    """Buduje odpowiedź Flaska z gotowym PDF-em (import lokalny — moduł
    działa też w workerze Celery bez kontekstu aplikacji)."""
    from flask import make_response
    response = make_response(pdf)
    response.headers['Content-Type'] = _MIME_PDF
    response.headers['Content-Disposition'] = disposition
    return response
