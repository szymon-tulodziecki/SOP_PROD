"""core/services/notifications.py

Powiadomienia e-mail o zdarzeniach workflow praktyk.

Każda funkcja notify_* buduje treść i kolejkuje wysyłkę w tasku Celery
`send_email` — nigdy nie blokuje żądania HTTP i nigdy nie rzuca wyjątku
na zewnątrz (awaria powiadomienia nie może przerwać przejścia workflow).

Wywoływać PO db.session.commit() — treść czyta zatwierdzone dane zapisu.

E-maile są zawsze po polsku (język dokumentacji przebiegu praktyki).
Uwaga: reguła "bez inline CSS" dotyczy szablonów aplikacji (CSP) — klienci
pocztowi nie wczytują zewnętrznych arkuszy, więc e-mail ma minimalny
styl inline na kontenerze.
"""

from __future__ import annotations

import logging
import os
from html import escape

logger = logging.getLogger(__name__)

# Publiczny adres systemu (np. https://praktyki.ans-elblag.pl) — do linków w e-mailach.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

STUDENT_PANEL_PATH = "/praktyki-student/panel/"
ADMIN_PANEL_PATH = "/praktyki-admin/panel/"
AGREEMENT_FORM_PATH = "/praktyki-student/porozumienie/"


def student_panel_url() -> str:
    return f"{PUBLIC_BASE_URL}{STUDENT_PANEL_PATH}" if PUBLIC_BASE_URL else ""


def admin_panel_url() -> str:
    return f"{PUBLIC_BASE_URL}{ADMIN_PANEL_PATH}" if PUBLIC_BASE_URL else ""


def agreement_form_url(token: str) -> str:
    """Publiczny link formularza porozumienia dla osoby upoważnionej."""
    return f"{PUBLIC_BASE_URL}{AGREEMENT_FORM_PATH}{token}"


def _render_email(title: str, paragraphs: list[str], cta_url: str = "", cta_label: str = "") -> str:
    """Minimalny szablon HTML e-maila. paragraphs mogą zawierać gotowy HTML
    zbudowany wyłącznie z przefiltrowanych (escape) danych."""
    parts = [
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;'
        'margin:0 auto;padding:24px;color:#1e293b;">',
        f'<h2 style="color:#0f4c81;">{escape(title)}</h2>',
    ]
    parts.extend(f"<p>{p}</p>" for p in paragraphs)
    if cta_url:
        parts.append(
            f'<p><a href="{escape(cta_url)}" style="display:inline-block;'
            "padding:10px 20px;background:#0f4c81;color:#ffffff;"
            f'text-decoration:none;border-radius:6px;">{escape(cta_label)}</a></p>'
        )
    parts.append(
        '<hr style="border:none;border-top:1px solid #e2e8f0;">'
        '<p style="font-size:12px;color:#64748b;">Wiadomość wygenerowana automatycznie '
        "przez System Obsługi Praktyk ANS w Elblągu. Prosimy na nią nie odpowiadać.</p>"
        "</div>"
    )
    return "".join(parts)


def _enqueue(to, subject: str, html_body: str) -> None:
    """Kolejkuje wysyłkę w Celery; każdy błąd kończy się tylko wpisem w logu."""
    try:
        from celery_app import send_email

        send_email.delay(to, subject, html_body)
    except Exception:
        logger.exception("Nie udało się zakolejkować e-maila '%s' do %s", subject, to)


def _active_emails_with_role(role) -> list[str]:
    """Adresy aktywnych użytkowników mających rolę (główną lub z user_roles)."""
    from core.extensions import db
    from core.models import User, UserRoleAssoc

    rows = (
        db.session.query(User.email)
        .outerjoin(UserRoleAssoc, UserRoleAssoc.user_id == User.id)
        .filter(User.is_active.is_(True))
        .filter((User.role == role) | (UserRoleAssoc.role == role))
        .distinct()
        .all()
    )
    return [r.email for r in rows]


def _student_name(enrollment) -> str:
    s = enrollment.student
    return f"{s.first_name} {s.last_name}" if s else ""


def _opis_zgloszenia(enrollment) -> str:
    """Wspólny wiersz opisujący zgłoszenie: student + firma (jeśli podana)."""
    czesci = [f"Student: <strong>{escape(_student_name(enrollment))}</strong>"]
    firma = enrollment.company_display_name
    if firma:
        czesci.append(f"Zakład pracy: <strong>{escape(firma)}</strong>")
    return "<br>".join(czesci)


# ── Zdarzenia workflow ────────────────────────────────────────────────────────


def notify_submitted_to_supervisor(enrollment) -> None:
    """Ścieżka A: zgłoszenie czeka na akceptację opiekuna UOPZ."""
    try:
        supervisor = enrollment.supervisor
        if not supervisor or not supervisor.email:
            return
        html = _render_email(
            "Nowe zgłoszenie praktyki do akceptacji",
            [
                "W systemie praktyk pojawiło się zgłoszenie oczekujące na Twoją akceptację.",
                _opis_zgloszenia(enrollment),
            ],
            cta_url=admin_panel_url(),
            cta_label="Przejdź do panelu",
        )
        _enqueue(supervisor.email, "SOP: nowe zgłoszenie praktyki do akceptacji", html)
    except Exception:
        logger.exception("notify_submitted_to_supervisor failed")


def notify_submitted_to_committee(enrollment) -> None:
    """Ścieżki B/C: wniosek trafił do weryfikacji komisji."""
    try:
        recipients = _active_emails_with_role(_role("KOMISJA"))
        if not recipients:
            return
        html = _render_email(
            "Nowy wniosek do weryfikacji komisji",
            [
                "W systemie praktyk pojawił się wniosek oczekujący na weryfikację komisji.",
                _opis_zgloszenia(enrollment),
            ],
            cta_url=admin_panel_url(),
            cta_label="Przejdź do panelu",
        )
        _enqueue(recipients, "SOP: nowy wniosek do weryfikacji komisji", html)
    except Exception:
        logger.exception("notify_submitted_to_committee failed")


def notify_sent_to_director(enrollment) -> None:
    """Wniosek czeka na decyzję Dyrektora Instytutu."""
    try:
        recipients = _active_emails_with_role(_role("DYREKTOR"))
        if not recipients:
            return
        html = _render_email(
            "Wniosek oczekuje na decyzję Dyrektora",
            [
                "Komisja przekazała wniosek do ostatecznej decyzji.",
                _opis_zgloszenia(enrollment),
            ],
            cta_url=admin_panel_url(),
            cta_label="Przejdź do panelu",
        )
        _enqueue(recipients, "SOP: wniosek oczekuje na decyzję Dyrektora", html)
    except Exception:
        logger.exception("notify_sent_to_director failed")


def notify_student_revision(enrollment, comment: str = "") -> None:
    """Zgłoszenie zwrócone studentowi do poprawy/uzupełnienia."""
    try:
        if not enrollment.student or not enrollment.student.email:
            return
        paragraphs = ["Twoje zgłoszenie praktyki zostało zwrócone do uzupełnienia."]
        if comment:
            paragraphs.append(f"Komentarz: <em>{escape(comment)}</em>")
        paragraphs.append("Zaloguj się do systemu, popraw zgłoszenie i wyślij je ponownie.")
        html = _render_email(
            "Zgłoszenie wymaga uzupełnień",
            paragraphs,
            cta_url=student_panel_url(),
            cta_label="Przejdź do panelu studenta",
        )
        _enqueue(enrollment.student.email, "SOP: Twoje zgłoszenie wymaga uzupełnień", html)
    except Exception:
        logger.exception("notify_student_revision failed")


def notify_student_approved(enrollment) -> None:
    """Zgłoszenie zaakceptowane — praktyka rusza (IN_PROGRESS)."""
    try:
        if not enrollment.student or not enrollment.student.email:
            return
        html = _render_email(
            "Zgłoszenie praktyki zaakceptowane",
            [
                "Twoje zgłoszenie praktyki zostało zaakceptowane. "
                "Możesz rozpocząć uzupełnianie dziennika praktyk w systemie.",
            ],
            cta_url=student_panel_url(),
            cta_label="Przejdź do panelu studenta",
        )
        _enqueue(enrollment.student.email, "SOP: zgłoszenie praktyki zaakceptowane", html)
    except Exception:
        logger.exception("notify_student_approved failed")


def notify_student_rejected(enrollment, comment: str = "") -> None:
    """Zgłoszenie odrzucone."""
    try:
        if not enrollment.student or not enrollment.student.email:
            return
        paragraphs = ["Twoje zgłoszenie praktyki zostało odrzucone."]
        if comment:
            paragraphs.append(f"Uzasadnienie: <em>{escape(comment)}</em>")
        paragraphs.append("W razie pytań skontaktuj się z opiekunem praktyk lub dziekanatem.")
        html = _render_email(
            "Zgłoszenie praktyki odrzucone",
            paragraphs,
            cta_url=student_panel_url(),
            cta_label="Przejdź do panelu studenta",
        )
        _enqueue(enrollment.student.email, "SOP: zgłoszenie praktyki odrzucone", html)
    except Exception:
        logger.exception("notify_student_rejected failed")


# ── Porozumienia (dziekanat ↔ zakład pracy) ──────────────────────────────────


def notify_agreement_recipient(agreement, token: str) -> None:
    """Wysyła osobie upoważnionej link do formularza porozumienia."""
    try:
        students = ", ".join(
            f"{ae.enrollment.student.first_name} {ae.enrollment.student.last_name}"
            for ae in agreement.enrollments
            if ae.enrollment and ae.enrollment.student
        )
        html = _render_email(
            "Porozumienie w sprawie praktyk studenckich",
            [
                "Akademia Nauk Stosowanych w Elblągu zaprasza do zawarcia porozumienia "
                "w sprawie praktyk zawodowych studentów.",
                f'Zakład pracy: <strong>{escape(agreement.company_name or "")}</strong>',
                f"Studenci: <strong>{escape(students)}</strong>",
                "Prosimy o uzupełnienie danych porozumienia pod poniższym linkiem. "
                "Link jest unikalny i przeznaczony wyłącznie dla Państwa.",
            ],
            cta_url=agreement_form_url(token),
            cta_label="Uzupełnij porozumienie",
        )
        _enqueue(
            agreement.recipient_email,
            "ANS Elbląg: porozumienie w sprawie praktyk studenckich",
            html,
        )
    except Exception:
        logger.exception("notify_agreement_recipient failed")


def notify_agreement_filled(agreement) -> None:
    """Informuje dziekanat, że zakład pracy uzupełnił porozumienie."""
    try:
        recipients = _active_emails_with_role(_role("DZIEKANAT"))
        recipients += _active_emails_with_role(_role("ADMIN"))
        recipients = sorted(set(recipients))
        if not recipients:
            return
        html = _render_email(
            "Porozumienie uzupełnione przez zakład pracy",
            [
                f'Zakład pracy <strong>{escape(agreement.company_name or "")}</strong> '
                "uzupełnił dane porozumienia w sprawie praktyk.",
                "Porozumienie jest gotowe do wygenerowania i podpisu.",
            ],
            cta_url=admin_panel_url(),
            cta_label="Przejdź do panelu",
        )
        _enqueue(recipients, "SOP: porozumienie uzupełnione przez zakład pracy", html)
    except Exception:
        logger.exception("notify_agreement_filled failed")


def _role(name: str):
    from core.models import UserRole

    return UserRole[name]
