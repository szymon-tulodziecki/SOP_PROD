# SOP — System Obsługi Praktyk

Aplikacja webowa do obsługi praktyk zawodowych studentów kierunku Informatyka
w Instytucie Informatyki Stosowanej im. Krzysztofa Brzeskiego ANS w Elblągu.

System wspiera pełen cykl pracy z praktyką:
- zgłaszanie i akceptację miejsc praktyk (ścieżki: standardowa, praca zawodowa/staż, działalność gospodarcza),
- prowadzenie dziennika praktyk,
- ocenianie efektów uczenia się przez opiekuna i komisję,
- generowanie dokumentów PDF na bazie szablonów LaTeX,
- powiadomienia i zadania cykliczne (Celery + Redis),
- integrację z Microsoft Entra ID (Azure AD) do logowania pracowników.

## Architektura

Projekt składa się z kilku serwisów uruchamianych przez Docker Compose:

| Serwis | Port (host) | Opis |
|--------|-------------|------|
| `admin` | 5000 | Panel administracyjny (UOPZ, komisja, dziekan) — Flask |
| `student` | 5001 | Panel studenta — Flask |
| `tex-service` | — (wewn.) | Mikroserwis kompilujący szablony LaTeX do PDF (LuaLaTeX) |
| `fileserver` | — (wewn.) | Szyfrowany magazyn plików z kluczem API |
| `celery-worker` | — (wewn.) | Przetwarzanie zadań w tle (PDF, maile) |
| `celery-beat` | — (wewn.) | Harmonogram zadań cyklicznych |
| `db` | — (wewn.) | PostgreSQL 16 |
| `redis` | — (wewn.) | Broker Celery + cache |

Wszystkie serwisy poza `admin` i `student` działają w sieci `internal` bez
dostępu do internetu. Kontenery uruchamiane są z `read_only`, `cap_drop: ALL`
i `no-new-privileges`.

## Szybki start

Wymagania: Docker Desktop (Windows/macOS) lub Docker Engine + Compose plugin (Linux).

1. Skopiuj plik z przykładowymi zmiennymi i uzupełnij wartości:
   ```bash
   cp .env.example .env
   ```
   Wygeneruj losowe wartości dla `SECRET_KEY`, `FILE_ENCRYPTION_KEY`
   (klucz Fernet, 32 bajty base64) oraz `FILESERVER_API_KEY`.
   Uzupełnij poświadczenia Azure AD (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`,
   `AZURE_TENANT_ID`).

2. Zbuduj i uruchom:
   ```bash
   docker compose build
   docker compose up -d
   ```

3. Aplikacje będą dostępne pod adresami:
   - panel administracyjny — http://localhost:5000
   - panel studenta — http://localhost:5001

Schemat bazy inicjalizowany jest przy pierwszym starcie z pliku
`database/init.sql` (mapowanego do `/docker-entrypoint-initdb.d/`).

### Czysty restart od zera

```bash
docker compose down --volumes
docker compose build --no-cache
docker compose up -d
```

## Zmienne środowiskowe

Minimalna lista (pełna w `.env.example`):

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — konto bazy.
- `SECRET_KEY` — klucz sesji Flask.
- `FILE_ENCRYPTION_KEY` — klucz Fernet do szyfrowania plików w `fileserver`.
- `FILESERVER_API_KEY` — klucz uwierzytelniający wywołania do `fileserver`.
- `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` — MSAL / SSO.
- `FLASK_ENV` — `production` / `development` / `testing`.

Pliku `.env` nigdy nie commituj.

## Struktura katalogów

```
.
├── app_admin/         # Aplikacja administracyjna (Flask)
│   ├── routes/        # Blueprinty: pulpit, zarządzanie, ocenianie, dziennik, dokumenty
│   ├── templates/     # Szablony Jinja2
│   └── static/
├── app_student/       # Aplikacja studencka (Flask)
├── core/              # Wspólna logika
│   ├── modele/        # Modele SQLAlchemy (użytkownicy, praktyki, dziennik, dokumenty, firmy)
│   ├── repozytoria/   # Warstwa dostępu do danych (Repository pattern)
│   ├── uslugi/        # Logika biznesowa (workflow, ocenianie, dokumenty)
│   ├── autoryzacja.py # Blueprint logowania + MSAL
│   ├── pliki.py       # Obsługa uploadów przez fileserver
│   └── szyfrowanie.py # Fernet wrapper
├── tex_service/       # Mikroserwis LaTeX → PDF
│   └── templates/     # Szablony .tex.j2 załączników (ZAL_1…ZAL_9, ZAL_4B itd.)
├── fileserver/        # Szyfrowany magazyn plików (Flask + Fernet)
├── celery_worker/     # Dockerfile workera Celery
├── celery_app.py      # Konfiguracja Celery i zadania w tle
├── database/
│   └── init.sql       # Schemat bazy ładowany przy pierwszym starcie
├── docker-compose.yml
├── .env.example
└── tests/             # Testy e2e (Playwright) — nie wchodzą w obraz produkcyjny
```

## Modele domenowe (skrót)

- **User** — użytkownicy z rolami `ADMIN`, `UOPZ`, `COMMISSION`, `DEAN`, `SUPERVISOR`, `STUDENT`.
- **Enrollment (Zapis)** — zgłoszenie studenta na praktykę; maszyna stanów:
  `PENDING → AWAITING_APPROVAL → IN_PROGRESS → COMPLETED`,
  dla ścieżek „praca/staż" i „działalność gospodarcza" dochodzą stany
  `COMMISSION_REVIEW → DEAN_APPROVAL`.
- **JournalEntry** — wpisy w dzienniku praktyk.
- **Evaluation / LearningOutcomeResult** — oceny efektów uczenia się
  (`ACHIEVED`, `PARTIALLY_ACHIEVED`, `NOT_ACHIEVED`).
- **Document** — dynamicznie generowane załączniki (ZAL_1 … ZAL_9, ZAL_2A, ZAL_4A, ZAL_4B, ZAL_7A)
  w zależności od `path_type` (`STANDARD`, `EMPLOYMENT`, `OWN_BUSINESS`).

## Testy e2e

Testy end-to-end w `tests/` używają Playwrighta i osobnej nakładki Compose
(`docker-compose.test.yml` + `tests/seed_test.sql`). Katalog `tests/` nie
powinien trafiać do obrazów produkcyjnych. Artefakty (`test-results/`,
`playwright-report/`, `node_modules/`) są ignorowane przez `.gitignore`.

## Licencja

Projekt wewnętrzny Instytutu Informatyki Stosowanej ANS w Elblągu.
