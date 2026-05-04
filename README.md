# SOP — Instrukcja wdrożenia produkcyjnego

System Obsługi Praktyk — Instytut Informatyki Stosowanej ANS w Elblągu.

---

## 1. Wymagania sprzętowe

### Minimalna maszyna produkcyjna (pojedynczy węzeł Swarm)

| Zasób | Minimum | Zalecane |
|-------|---------|----------|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Dysk (system + obrazy) | 30 GB SSD | 60 GB SSD |
| Dysk (dane — wolumeny) | 20 GB | 50 GB |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| Docker Engine | ≥ 25.0 | najnowszy stabilny |

> Serwis `tex-service` (LuaLaTeX) jest najcięższy pamięciowo — może potrzebować do 512 MB
> przy kompilacji. Przy dużym ruchu warto skalować jego repliki.

### Zależności zewnętrzne

- **Rejestr kontenerów** — np. GitHub Container Registry (`ghcr.io`) lub własny Harbor.
  Adres rejestru ustawiany przez zmienną `REGISTRY` przed deployem.
- **Microsoft Entra ID** — aplikacja zarejestrowana w tenantcie `ans-elblag.pl`
  (patrz sekcja 3.3).
- **Reverse proxy** — Nginx lub Traefik przed portami `5000`/`5001` z certyfikatem TLS.
  System **nie** serwuje HTTPS bezpośrednio.

---

## 2. Przygotowanie maszyny

```bash
# Aktualizacja systemu
sudo apt update && sudo apt upgrade -y

# Docker Engine (jeśli nie zainstalowany)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Weryfikacja
docker --version
```

### Inicjalizacja Docker Swarm (jednorazowo)

```bash
# Pobierz publiczny IP maszyny
PUBLIC_IP=$(curl -s ifconfig.me)

docker swarm init --advertise-addr $PUBLIC_IP
```

Jeśli planujesz klaster wielu węzłów, skopiuj komendę `docker swarm join --token ...`
wyświetloną po inicjalizacji i wykonaj ją na pozostałych maszynach.

---

## 3. Konfiguracja jednorazowa

### 3.1 Klucze i sekrety Swarm

Wszystkie wrażliwe wartości trafiają do Docker Swarm secrets — **nigdy** do plików `.env`
ani zmiennych środowiskowych. Są montowane jako pliki w `/run/secrets/<nazwa>` wewnątrz
kontenerów i odczytywane przez `core/secrets.py`.

Wymagane sekrety:

| Nazwa sekretu | Opis | Jak wygenerować |
|---------------|------|-----------------|
| `postgres_password` | Hasło użytkownika bazy danych | `openssl rand -hex 32` |
| `secret_key` | Klucz sesji Flask | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `file_encryption_key` | Klucz Fernet (szyfrowanie plików studentów) | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `fileserver_api_key` | Klucz API między Flask a fileserverem | `openssl rand -hex 32` |
| `azure_client_id` | Client ID aplikacji Entra ID | z portalu Azure (sekcja 3.3) |
| `azure_client_secret` | Client Secret aplikacji Entra ID | z portalu Azure (sekcja 3.3) |
| `azure_tenant_id` | Tenant ID — `ans-elblag.pl` | z portalu Azure (sekcja 3.3) |

```bash
# Przykład tworzenia sekretów (zastąp wartości rzeczywistymi)
printf "TUTAJ_SILNE_HASLO"    | docker secret create postgres_password -
printf "TUTAJ_KLUCZ_SESJI"    | docker secret create secret_key -
printf "TUTAJ_KLUCZ_FERNET"   | docker secret create file_encryption_key -
printf "TUTAJ_KLUCZ_API"      | docker secret create fileserver_api_key -
printf "CLIENT_ID_Z_AZURE"    | docker secret create azure_client_id -
printf "CLIENT_SECRET_Z_AZURE"| docker secret create azure_client_secret -
printf "TENANT_ID_Z_AZURE"    | docker secret create azure_tenant_id -

# Weryfikacja (wartości NIE są wyświetlane — tylko nazwy)
docker secret ls
```

> ⚠️ **Klucz Fernet (`file_encryption_key`) szyfruje dokumenty studentów.**
> Jego utrata oznacza trwałą utratę dostępu do wszystkich przesłanych plików.
> Zapisz go w bezpiecznym miejscu (menedżer haseł instytucjonalny, sejf).

### 3.2 Inicjalizacja bazy danych

Schemat bazy (tabele, indeksy, constrainty) inicjalizowany jest automatycznie przez
PostgreSQL przy pierwszym starcie z pliku `database/init.sql`.

```bash
# Uruchom stos — PostgreSQL zainicjuje schemat automatycznie
docker stack deploy -c docker-stack.yml sop

# Zaczekaj ~30 sekund, sprawdź logi bazy
docker service logs sop_db
```

Jeśli przenosisz dane z istniejącej bazy:

```bash
# Dump z poprzedniego środowiska
pg_dump -U ans_admin -h STARY_HOST ans_praktyki > backup.sql

# Restore na produkcji (po starcie kontenera db)
cat backup.sql | docker exec -i $(docker ps -qf name=sop_db) \
  psql -U ans_admin ans_praktyki
```

### 3.3 Rejestracja aplikacji w Microsoft Entra ID

W portalu [portal.azure.com](https://portal.azure.com) dla tenanta `ans-elblag.pl`:

1. **App registrations → New registration**
   - Name: `SOP — System Obsługi Praktyk`
   - Supported account types: `Accounts in this organizational directory only (ans-elblag.pl)`
   - Redirect URI: `Web` → `https://TWOJA_DOMENA/ms-callback`

2. **Certificates & secrets → New client secret**
   - Expiry: 24 miesiące — **zanotuj datę wygaśnięcia**
   - Zapisz wartość `Value` (nie `Secret ID`) → to jest `azure_client_secret`

3. **Overview** → skopiuj:
   - `Application (client) ID` → `azure_client_id`
   - `Directory (tenant) ID` → `azure_tenant_id`

4. **API permissions** → upewnij się że jest `Microsoft Graph → User.Read (Delegated)`

> URI callbacku musi być publicznym adresem panelu administracyjnego (`admin` app, port 5000).
> Panel studenta korzysta z tego samego Redirect URI — jeśli domeny są różne,
> dodaj obie w portalu Azure.

---

## 4. Budowanie i publikowanie obrazów

```bash
export REGISTRY=ghcr.io/TWOJA_ORGANIZACJA   # lub własny rejestr
export IMAGE_TAG=v1.0.0

# Logowanie do rejestru
docker login $REGISTRY

# Budowanie obrazów (na maszynie deweloperskiej lub w CI)
docker build -t $REGISTRY/sop-admin:$IMAGE_TAG      -f app_admin/Dockerfile      .
docker build -t $REGISTRY/sop-student:$IMAGE_TAG    -f app_student/Dockerfile    .
docker build -t $REGISTRY/sop-celery:$IMAGE_TAG     -f celery_worker/Dockerfile  .
docker build -t $REGISTRY/sop-tex:$IMAGE_TAG        -f documents_tex/Dockerfile  .
docker build -t $REGISTRY/sop-fileserver:$IMAGE_TAG -f fileserver/Dockerfile     .

# Push do rejestru
docker push $REGISTRY/sop-admin:$IMAGE_TAG
docker push $REGISTRY/sop-student:$IMAGE_TAG
docker push $REGISTRY/sop-celery:$IMAGE_TAG
docker push $REGISTRY/sop-tex:$IMAGE_TAG
docker push $REGISTRY/sop-fileserver:$IMAGE_TAG
```

Na maszynie produkcyjnej zaloguj się do rejestru, żeby Swarm mógł pobrać obrazy:

```bash
docker login $REGISTRY
```

---

## 5. Deploy

```bash
# Na maszynie produkcyjnej
export REGISTRY=ghcr.io/TWOJA_ORGANIZACJA
export IMAGE_TAG=v1.0.0

docker stack deploy -c docker-stack.yml sop
```

Sprawdzenie stanu (poczekaj ~60 sekund na pełny start):

```bash
docker stack services sop        # lista serwisów i liczba replik
docker service ps sop_admin      # instancje serwisu admin
docker service logs sop_admin    # logi (ostatnie 100 linii)
```

Oczekiwany stan:

```
NAME                  MODE         REPLICAS
sop_admin             replicated   2/2
sop_student           replicated   2/2
sop_celery-worker     replicated   2/2
sop_celery-beat       replicated   1/1
sop_db                replicated   1/1
sop_redis             replicated   1/1
sop_fileserver        replicated   1/1
sop_tex-service       replicated   1/1
```

---

## 6. Sieć i reverse proxy

### Porty wyeksponowane na hoście

| Port hosta | Serwis | Opis |
|------------|--------|------|
| `5000` | `admin` | Panel UOPZ / komisja / dyrektor |
| `5001` | `student` | Panel studenta |

Pozostałe serwisy (`db`, `redis`, `fileserver`, `tex-service`, `celery-*`) działają
wyłącznie w sieci `internal` (Docker overlay) — **niedostępne z zewnątrz**.

### Nginx (przykładowa konfiguracja TLS)

```nginx
# /etc/nginx/sites-available/sop-admin
server {
    listen 443 ssl http2;
    server_name admin.sop.ans-elblag.pl;

    ssl_certificate     /etc/letsencrypt/live/admin.sop.ans-elblag.pl/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/admin.sop.ans-elblag.pl/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
server {
    listen 80;
    server_name admin.sop.ans-elblag.pl;
    return 301 https://$host$request_uri;
}
```

```nginx
# /etc/nginx/sites-available/sop-student
server {
    listen 443 ssl http2;
    server_name sop.ans-elblag.pl;

    ssl_certificate     /etc/letsencrypt/live/sop.ans-elblag.pl/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/sop.ans-elblag.pl/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:5001;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
server {
    listen 80;
    server_name sop.ans-elblag.pl;
    return 301 https://$host$request_uri;
}
```

Certyfikaty Let's Encrypt:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d sop.ans-elblag.pl -d admin.sop.ans-elblag.pl
```

### Firewall (ufw)

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP → redirect HTTPS
sudo ufw allow 443/tcp   # HTTPS
# Porty 5000/5001 NIE powinny być dostępne z zewnątrz.
# Nginx na tym samym hoście komunikuje się przez 127.0.0.1.
sudo ufw enable
```

> Jeśli Nginx jest na osobnym serwerze, otwórz porty `5000`/`5001` tylko dla jego IP:
> `sudo ufw allow from NGINX_IP to any port 5000`

---

## 7. Aktualizacja aplikacji (rolling update bez downtime)

```bash
export REGISTRY=ghcr.io/TWOJA_ORGANIZACJA
export IMAGE_TAG=v1.1.0

# Zbuduj i wypchnij nowe obrazy
docker build -t $REGISTRY/sop-admin:$IMAGE_TAG   -f app_admin/Dockerfile   . \
  && docker push $REGISTRY/sop-admin:$IMAGE_TAG
docker build -t $REGISTRY/sop-student:$IMAGE_TAG -f app_student/Dockerfile . \
  && docker push $REGISTRY/sop-student:$IMAGE_TAG
docker build -t $REGISTRY/sop-celery:$IMAGE_TAG  -f celery_worker/Dockerfile . \
  && docker push $REGISTRY/sop-celery:$IMAGE_TAG

# Na maszynie produkcyjnej — rolling update
docker stack deploy -c docker-stack.yml sop
```

Swarm startuje nową replikę przed wyłączeniem starej (`order: start-first`).
W razie błędu automatycznie przywraca poprzednią wersję (`failure_action: rollback`).

Ręczny rollback:

```bash
docker service rollback sop_admin
docker service rollback sop_student
```

---

## 8. Zmiana haseł i rotacja kluczy

### Hasło bazy danych

```bash
# 1. Zmień hasło w PostgreSQL
docker exec -it $(docker ps -qf name=sop_db) \
  psql -U ans_admin -c "ALTER USER ans_admin PASSWORD 'NOWE_HASLO';"

# 2. Zaktualizuj sekret Swarm (sekrety są immutable — usuń i utwórz nowy)
docker service scale sop_admin=0 sop_student=0 sop_celery-worker=0 sop_celery-beat=0
docker secret rm postgres_password
printf "NOWE_HASLO" | docker secret create postgres_password -
docker stack deploy -c docker-stack.yml sop
```

### Klucz sesji Flask (`secret_key`)

Zmiana unieważnia wszystkie aktywne sesje — użytkownicy zostaną wylogowani.

```bash
docker service scale sop_admin=0 sop_student=0
docker secret rm secret_key
python3 -c "import secrets; print(secrets.token_hex(32))" | docker secret create secret_key -
docker stack deploy -c docker-stack.yml sop
```

### Client Secret Azure AD (wygasa co 24 miesiące)

1. W portalu Azure wygeneruj **nowy** secret (stary możesz chwilowo zostawić aktywny).
2. Zaktualizuj sekret Swarm:
   ```bash
   docker service scale sop_admin=0 sop_student=0
   docker secret rm azure_client_secret
   printf "NOWY_SECRET" | docker secret create azure_client_secret -
   docker stack deploy -c docker-stack.yml sop
   ```
3. Usuń stary secret z portalu Azure.

### Klucz Fernet (`file_encryption_key`)

> ⚠️ **NIE rotuj tego klucza bez uprzedniej migracji danych.**
> Zmiana klucza bez re-szyfrowania istniejących plików spowoduje trwałą utratę
> dostępu do wszystkich dokumentów studentów.

---

## 9. Kopie zapasowe

### Baza danych

```bash
# Dump z datą (uruchom na maszynie produkcyjnej)
docker exec $(docker ps -qf name=sop_db) \
  pg_dump -U ans_admin ans_praktyki | gzip > backup_$(date +%Y%m%d_%H%M).sql.gz

# Restore
gunzip -c backup_20260501_1200.sql.gz | docker exec -i $(docker ps -qf name=sop_db) \
  psql -U ans_admin ans_praktyki
```

Zalecane: cron z backupem co dobę + transfer na zewnętrzny storage.

```bash
# Przykład wpisu w crontab (codziennie o 2:00)
0 2 * * * docker exec $(docker ps -qf name=sop_db) pg_dump -U ans_admin ans_praktyki \
  | gzip > /backup/sop_$(date +\%Y\%m\%d).sql.gz
```

### Pliki studentów (wolumin `fileserver_data`)

```bash
docker run --rm \
  -v sop_fileserver_data:/source:ro \
  -v /backup:/dest \
  alpine tar czf /dest/fileserver_$(date +%Y%m%d).tar.gz -C /source .
```

### Klucze Swarm secrets

Sekrety są przechowywane zaszyfrowane w Raft logu Swarma — brak prostego eksportu.
**Zapisz oryginalne wartości przy tworzeniu** (menedżer haseł, sejf instytucjonalny).

---

## 10. Monitoring i diagnostyka

```bash
# Stan serwisów i replik
docker stack services sop

# Logi serwisu na żywo
docker service logs -f --tail=200 sop_admin
docker service logs -f --tail=200 sop_celery-worker

# Healthcheck endpointy
curl -f http://localhost:5000/health && echo "admin OK"
curl -f http://localhost:5001/health && echo "student OK"

# Wykorzystanie zasobów
docker stats $(docker ps --filter name=sop -q)
```

### Typowe problemy

| Objaw | Przyczyna | Rozwiązanie |
|-------|-----------|-------------|
| Serwis utknął w `Preparing` | Obraz nie do pobrania z rejestru | Sprawdź `docker login` i nazwy obrazów |
| `No such secret` przy starcie | Sekret nie istnieje w Swarmie | `docker secret ls`, utwórz brakujący |
| `502 Bad Gateway` z Nginx | Flask nie odpowiada na porcie | `docker service logs sop_admin` |
| Logowanie: `invalid_client` | Wygasły Client Secret Azure | Zaktualizuj sekret (sekcja 8) |
| PDF się nie generuje | `tex-service` niedostępny | `docker service logs sop_tex-service` |
| Celery taski nie są przetwarzane | Redis niedostępny | `docker service logs sop_redis` |
| Dokumenty studentów nie otwierają się | Zły `file_encryption_key` | Klucz musi być identyczny jak przy zapisie pliku |

---

## 11. Podsumowanie sekretów

Po konfiguracji `docker secret ls` powinien zwrócić:

```
NAME
azure_client_id
azure_client_secret
azure_tenant_id
file_encryption_key
fileserver_api_key
postgres_password
secret_key
```

Żaden sekret nie pojawia się jako wartość w `docker-stack.yml` — tylko nazwa referencji.
Zmienne środowiskowe (nie-sekretne) są w blokach `environment:` w `docker-stack.yml`
i mogą być commitowane do repozytorium.
#
