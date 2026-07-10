"""core/services/mailer.py

Wysyłka e-maili przez Microsoft Graph API (flow client credentials).

Używa tej samej rejestracji aplikacji Entra ID co logowanie OAuth
(azure_client_id / azure_client_secret / azure_tenant_id), ale z uprawnieniem
aplikacyjnym Mail.Send i skrzynką nadawczą wskazaną w MAIL_SENDER.

Konfiguracja (env):
    MAIL_SENDER — adres skrzynki nadawczej (np. praktyki@ans-elblag.pl).
                  Pusty = wysyłka wyłączona; wiadomości trafiają tylko do logów.

Właściwa wysyłka odbywa się w tasku Celery `send_email` (celery_app.py) —
kod webowy nie blokuje żądań HTTP na komunikacji z Graph API.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

MAIL_SENDER = os.environ.get("MAIL_SENDER", "").strip()

_GRAPH_SCOPES = ["https://graph.microsoft.com/.default"]
_GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"

_msal_app_instance = None  # cache MSAL (wewnętrzny token cache przeżywa między wywołaniami)


class MailerError(RuntimeError):
    """Błąd wysyłki e-maila (konfiguracja, token lub Graph API)."""


def is_mail_enabled() -> bool:
    return bool(MAIL_SENDER)


def _msal_app():
    global _msal_app_instance
    if _msal_app_instance is None:
        import msal
        from core.secrets import get_secret

        _msal_app_instance = msal.ConfidentialClientApplication(
            client_id=get_secret("azure_client_id"),
            client_credential=get_secret("azure_client_secret"),
            authority=f"https://login.microsoftonline.com/{get_secret('azure_tenant_id')}",
        )
    return _msal_app_instance


def _acquire_app_token() -> str:
    result = _msal_app().acquire_token_for_client(scopes=_GRAPH_SCOPES)
    token = result.get("access_token")
    if not token:
        raise MailerError(
            f"Brak tokenu Graph: {result.get('error')} — {result.get('error_description')}"
        )
    return token


def send_mail_sync(to: str | list[str], subject: str, html_body: str) -> None:
    """Wysyła e-mail synchronicznie przez Graph API.

    Nie wywoływać bezpośrednio z widoków Flask — używać taska Celery
    `send_email`, który dodaje retry i nie blokuje odpowiedzi HTTP.
    """
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [r.strip() for r in recipients if r and r.strip()]
    if not recipients:
        raise MailerError("Brak adresata wiadomości.")

    if not is_mail_enabled():
        logger.info(
            "MAIL_SENDER nie ustawiony — pomijam wysyłkę '%s' do %s", subject, ", ".join(recipients)
        )
        return

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": r}} for r in recipients],
        },
        "saveToSentItems": True,
    }
    token = _acquire_app_token()
    resp = httpx.post(
        _GRAPH_SENDMAIL_URL.format(sender=MAIL_SENDER),
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code != 202:
        raise MailerError(f"Graph sendMail zwrócił {resp.status_code}: {resp.text[:500]}")
    logger.info("E-mail '%s' wysłany do %s", subject, ", ".join(recipients))
