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
| `admin` | 8080 | Panel administracyjny (UOPZ, komisja, dyrektor) — Flask |
| `student` | 8081 | Panel studenta — Flask |
| `tex-service` | — (wewn.) | Mikroserwis kompilujący szablony LaTeX do PDF (LuaLaTeX) |
| `fileserver` | — (wewn.) | Szyfrowany magazyn plików z kluczem API |
| `celery-worker` | — (wewn.) | Przetwarzanie zadań w tle (PDF i zadania konserwacyjne) |
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
   Uzupełnij podstawowe wartości `POSTGRES_USER`, `POSTGRES_DB` i `FLASK_ENV`.
   Sekrety używane przez Compose są czytane z plików w katalogu `secrets/`.
   Wygeneruj losowe wartości dla `secret_key.txt`, `file_encryption_key.txt`
   (klucz Fernet, 32 bajty base64), `fileserver_api_key.txt` oraz
   `postgres_password.txt`.
   Uzupełnij poświadczenia Azure AD (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`,
   `AZURE_TENANT_ID`) w odpowiadających im plikach sekretów.

2. Zbuduj i uruchom:
   ```bash
   docker compose build
   docker compose up -d
   ```

3. Aplikacje będą dostępne pod adresami:
   - panel administracyjny — http://localhost:8080
   - panel studenta — http://localhost:8081

Schemat bazy inicjalizowany jest przy pierwszym starcie z pliku
`database/init.sql` (mapowanego do `/docker-entrypoint-initdb.d/`).

### Czysty restart od zera

```bash
docker compose down --volumes
docker compose build --no-cache
docker compose up -d
```

## Zmienne środowiskowe i sekrety

Minimalna lista zmiennych konfiguracyjnych znajduje się w `.env.example`.
Wrażliwe wartości w `docker-compose.yml` są podawane przez pliki sekretów
z katalogu `secrets/`.

- `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` — parametry bazy.
- `FLASK_ENV` — `production`, `development` albo `testing`.
- `TEX_SERVICE_URL`, `FILESERVER_URL` — adresy usług w sieci Docker.
- `postgres_password.txt` — hasło bazy PostgreSQL.
- `secret_key.txt` — klucz sesji Flask.
- `file_encryption_key.txt` — klucz Fernet do szyfrowania plików przed zapisem w `fileserver`.
- `fileserver_api_key.txt` — klucz uwierzytelniający wywołania do `fileserver`.
- `azure_client_id.txt`, `azure_client_secret.txt`, `azure_tenant_id.txt` — MSAL / Microsoft Entra ID.

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
├── fileserver/        # Wewnętrzny magazyn zaszyfrowanych plików (Flask)
├── celery_worker/     # Dockerfile workera Celery
├── celery_app.py      # Konfiguracja Celery i zadania w tle
├── database/
│   └── init.sql       # Schemat bazy ładowany przy pierwszym starcie
├── docker-compose.yml
└── .env.example
```

## Modele domenowe (skrót)

- **User** — użytkownicy z rolami `ADMIN`, `UOPZ`, `KOMISJA`, `DYREKTOR`, `STUDENT`.
- **Enrollment (Zapis)** — zgłoszenie studenta na praktykę; maszyna stanów:
  `PENDING → AWAITING_APPROVAL → IN_PROGRESS → COMPLETED`,
  dla ścieżek „praca/staż" i „działalność gospodarcza" dochodzą stany
  `COMMISSION_REVIEW → DIRECTOR_APPROVAL`.
- **JournalEntry** — wpisy w dzienniku praktyk.
- **Evaluation / LearningOutcomeResult** — oceny efektów uczenia się
  (`ACHIEVED`, `PARTIALLY_ACHIEVED`, `NOT_ACHIEVED`).
- **UploadedDocument / DocumentAuditLog** — przesłane pliki studentów i audyt operacji na dokumentach.
- **Dokumenty PDF** — dynamicznie generowane załączniki (ZAL_1 … ZAL_9, ZAL_2A, ZAL_4A, ZAL_4B, ZAL_7A)
  dobierane przez `core.uslugi.documents` według `path_type` (`STANDARD`, `EMPLOYMENT`, `OWN_BUSINESS`).

## Licencja

Projekt wewnętrzny Instytutu Informatyki Stosowanej ANS w Elblągu.
