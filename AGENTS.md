# SOP_PROD — instrukcje dla agentów AI

System Obsługi Praktyk ANS Elbląg. Flask (app_admin :5000 + app_student :5001,
wspólny kod w `core/`), PostgreSQL, Redis+Celery, fileserver (szyfrowane pliki),
tex_service (kompilacja PDF z LaTeX), nginx. Cały UI po polsku.

Szczegółowe notatki projektu (deploy, testy maili, dev lokalny) są w `CLAUDE.md`
— przeczytaj je przed większą zmianą. Poniżej twarde zasady, których NIE wolno
łamać niezależnie od zadania.

## Twarde zasady

1. **Zero inline CSS/JS w szablonach** — CSP działa bez `unsafe-inline`.
   Style do `core/static/` lub `app_*/static/`, skrypty do plików `.js`.
   Jedyny wyjątek: HTML e-maili w `core/services/notifications.py`.
2. **Sekrety**: `secrets/*`, `database/seed_admins.sql`, prywatne klucze Azure —
   NIGDY do gita. Nie wpisuj prawdziwych IP/haseł do plików w repo.
3. **i18n**: kluczem tłumaczenia jest polski tekst. Każdy nowy tekst UI dopisz
   do `core/i18n/en.py` i `core/i18n/uk.py` (klucze identyczne z PL pomijamy,
   np. 'E-mail', 'PDF'). Teksty używane w JS → tuple `JS_STRINGS`
   w `core/i18n/__init__.py`. E-maile i dokumenty LaTeX zostają po polsku.
4. **Statusy zapisów** zmieniaj wyłącznie przez FSM (`core/services/workflow.py`).
   Powiadomienia e-mail (`core/services/notifications.py`) wywołuj dopiero
   PO `db.session.commit()`.
5. **Migracje**: brak frameworka — nowy plik SQL w `database/migrations/`
   (idempotentny: `IF NOT EXISTS` / guard `duplicate_object`), zaktualizuj też
   `database/init.sql`.
6. **Po zmianie CSS** bump wersji cache: admin — parametr `v=` w
   `app_admin/templates/layouts/base_panel.html`; student — `CSS_BUNDLE_V`
   w `app_student/__init__.py`.

## Wspólne komponenty — używaj, nie kopiuj

- **Makra UI**: `core/templates/_makra.html`, importowane w szablonach obu appów:
  `{% import "_makra.html" as makra with context %}` (zawsze `with context`).
  Paginacja, pole wyszukiwania, przyciski filtrów statusu, formularz akcji
  z CSRF + potwierdzeniem, komunikaty flash. Nie wklejaj własnych kopii tych
  bloków do szablonów.
- **Pułapka**: `url_for(endpoint, strona=nr, **request.args)` wybucha
  TypeError (500), gdy parametr strony już jest w URL — używaj makra
  `makra.paginacja(obiekt_paginacji, 'endpoint', param='strona'|'page')`.
- **tex_service**: PDF-y generuj wyłącznie przez `core/services/tex_client.py`
  (`generuj_pdf(template, context, filename, timeout)` → bajty albo
  `TexServiceError` z `.status_code`/`.error_detail`; do odpowiedzi HTTP
  `odpowiedz_pdf` + `dyspozycja_pdf`). Nie wołaj httpx do tex-service wprost.
- **Role**: użytkownik ma rolę główną (`users.role`) + opcjonalne dodatkowe
  (tabela `user_roles`). Filtrowanie/uprawnienia muszą sprawdzać obie —
  wzorce: `UserRepository.search_page`, `notifications._active_emails_with_role`,
  `User.has_role`.

## Dev lokalnie (Windows, bez Dockera)

Lokalny Python nie ma `psycopg2`/`celery`/`redis`. Smoke testy uruchamiaj z env:
`DATABASE_URL=sqlite://`, `CELERY_BROKER_URL=memory://` (+ dummy `SECRET_KEY`,
`AZURE_*`, `TEX_SERVICE_URL`, `FILESERVER_URL`). Dotyczy to TYLKO testów poza
Dockerem — konfiguracji Dockera (redis://redis:6379/0) nie zmieniaj.

Weryfikacja minimalna po zmianach: utworzenie obu appów (`create_app()`),
kompilacja wszystkich szablonów (`app.jinja_env.get_template(...)`),
render zmienionych makr/szablonów w `test_request_context`.
