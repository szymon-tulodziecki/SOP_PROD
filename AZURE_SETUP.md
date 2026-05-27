# Logowanie Microsoft (Entra ID) — konfiguracja SOP

Krótki przewodnik dla administratora: jak ustawić logowanie kontem Microsoft uczelni
i jak wgrać sekrety do Docker Swarm na serwerze produkcyjnym.

---

## 1. Co jest potrzebne

Aby logowanie przez Microsoft działało, musisz mieć:

1. **Dostęp administracyjny do Microsoft Entra ID** (Azure AD) dzierżawy ANS Elbląg.
2. **Trzy wartości** z portalu Azure, które zostaną wgrane jako Docker Secrets:
   - `AZURE_TENANT_ID` — identyfikator dzierżawy (GUID)
   - `AZURE_CLIENT_ID` — identyfikator zarejestrowanej aplikacji (GUID)
   - `AZURE_CLIENT_SECRET` — sekret klienta (wartość, nie ID)
3. **Domena uczelni** ustawiona w zmiennej `ALLOWED_EMAIL_DOMAIN` (np. `ans-elblag.pl`).
   Subdomeny (np. `student.ans-elblag.pl`) są akceptowane automatycznie.

---

## 2. Rejestracja aplikacji w Microsoft Entra ID

1. Wejdź na <https://entra.microsoft.com> → **Aplikacje** → **Rejestracje aplikacji** → **+ Nowa rejestracja**.
2. **Nazwa**: `SOP — ANS Elbląg` (dowolna).
3. **Obsługiwane typy kont**: **Konta tylko w tym katalogu organizacyjnym (jedna dzierżawa)**.
4. **Identyfikator URI przekierowania** — wybierz typ **Web** i dodaj **oba** adresy:
   - `https://<TWOJA_DOMENA>/praktyki-admin/auth/ms-callback`
   - `https://<TWOJA_DOMENA>/auth/ms-callback`

   Przykładowo dla testowego serwera:
   - `https://193.107.32.227/praktyki-admin/auth/ms-callback`
   - `https://193.107.32.227/auth/ms-callback`

   > **Uwaga:** Microsoft wymaga HTTPS. Dla localhost dopuszcza HTTP, ale na produkcji nigdy.
5. **Zarejestruj**.

Po rejestracji na zakładce **Przegląd** zobaczysz:
- **Identyfikator aplikacji (klienta)** → to jest `AZURE_CLIENT_ID`
- **Identyfikator katalogu (dzierżawy)** → to jest `AZURE_TENANT_ID`

### 2.1. Wygenerowanie sekretu klienta

1. **Certyfikaty i klucze tajne** → **+ Nowy klucz tajny klienta**.
2. **Opis**: `SOP prod` (lub data: `2026-05-26`).
3. **Wygaśnięcie**: 24 miesiące (notuj termin — trzeba odnowić przed wygaśnięciem).
4. **Dodaj** → skopiuj kolumnę **Wartość** (nie **Identyfikator klucza tajnego**!).
   Wartość pokazuje się **tylko raz** — po odświeżeniu portal pokaże już tylko maskę.

   Ta wartość to `AZURE_CLIENT_SECRET`.

### 2.2. Uprawnienia API

1. **Uprawnienia interfejsu API** → domyślnie powinno być `User.Read` (Microsoft Graph, delegated).
2. To wystarczy — SOP używa tylko `id_token` do odczytania adresu e-mail (`preferred_username`).
3. Jeżeli dzierżawa wymusza zgodę administratora, kliknij **Udziel zgody administratora dla
   <tenant>**.

### 2.3. Dodatkowe adresy zwrotne (fallback / dev)

Jeśli aplikacja działa na kilku domenach (np. produkcja + staging + lokalny dev), dodaj wszystkie
adresy w **Uwierzytelnianie** → **Identyfikatory URI przekierowania**. Microsoft sprawdza
**dokładne dopasowanie**, więc każda zmiana hosta/portu/ścieżki wymaga wpisu osobno.

Przykład:
```
https://praktyki.ans-elblag.pl/praktyki-admin/auth/ms-callback
https://praktyki.ans-elblag.pl/auth/ms-callback
https://193.107.32.227/praktyki-admin/auth/ms-callback
https://193.107.32.227/auth/ms-callback
http://localhost:5000/auth/ms-callback
http://localhost:5001/auth/ms-callback
```

---

## 3. Wgranie sekretów do Docker Swarm

Aplikacja czyta 7 sekretów z `/run/secrets/<nazwa>` w każdym kontenerze. Trzeba je
utworzyć **raz** w Swarmie przed pierwszym deployem.

### Najszybciej: jeden skrypt interaktywny

```bash
ssh sop@<host>
cd ~/sop_prod
./scripts/setup_swarm_secrets.sh
```

Skrypt zapyta tylko o **trzy wartości z Azure** (Tenant ID, Client ID, Client Secret),
pozostałe sekrety (`secret_key`, `postgres_password`, `file_encryption_key`,
`fileserver_api_key`) wygeneruje sam i wgra wszystko do Swarma. Jeśli sekret już
istnieje — utworzy nową wersję z sufiksem timestamp do podmiany w `docker-stack.yml`.

Sekcje 3.1–3.5 niżej opisują to samo robione ręcznie (gdyby skrypt nie działał).

---

### 3.1. Zaloguj się na serwer i wejdź do projektu

```bash
ssh sop@<host>
cd ~/sop_prod
```

### 3.2. Stwórz katalog z plikami sekretów

Każdy sekret to **plik tekstowy z jedną wartością** w katalogu `secrets/`:

```bash
mkdir -p secrets
nano secrets/azure_tenant_id.txt        # wklej GUID dzierżawy
nano secrets/azure_client_id.txt        # wklej GUID aplikacji
nano secrets/azure_client_secret.txt    # wklej wartość sekretu klienta z portalu
nano secrets/secret_key.txt             # wpisz długi losowy ciąg (≥ 64 znaki)
nano secrets/postgres_password.txt      # wpisz hasło do bazy (dowolny silny string)
nano secrets/file_encryption_key.txt    # patrz uwaga niżej
nano secrets/fileserver_api_key.txt     # wpisz losowy ciąg (np. 32+ znaków)
```

> **Uwaga dla `file_encryption_key`** — musi być kluczem Fernet (44 znaki, kończy się na `=`).
> Wygeneruj jednym poleceniem:
> ```bash
> python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
>   > secrets/file_encryption_key.txt
> ```
>
> Dla `secret_key` i `fileserver_api_key` możesz użyć:
> ```bash
> openssl rand -base64 48 > secrets/secret_key.txt
> openssl rand -hex 32    > secrets/fileserver_api_key.txt
> ```

### 3.3. Wgraj wszystkie sekrety jedną komendą

```bash
./scripts/create_swarm_secrets.sh
```

Skrypt przejdzie po liście, dla każdego pliku wykona `docker secret create`
i wypisze `OK <nazwa>` albo `SKIP <nazwa>` jeśli już istnieje.

### 3.4. Skasuj pliki z dysku

Sekrety są już w Swarmie — pliki nie są potrzebne i nie powinny zostać:

```bash
shred -u secrets/*.txt && rmdir secrets
```

### 3.5. Postaw stack

```bash
docker stack deploy -c docker-stack.yml sop
docker stack services sop          # podgląd statusu
docker service logs sop_admin -f   # logi panelu admina
```

### 3.6. Rotacja (np. wygasł `azure_client_secret`)

Wygeneruj nowy w portalu Azure, wpisz do pliku i:

```bash
echo '<nowa-wartosc>' > secrets/azure_client_secret.txt
./scripts/rotate_secret.sh azure_client_secret secrets/azure_client_secret.txt
shred -u secrets/azure_client_secret.txt
```

Skrypt tworzy nową wersję sekretu z sufiksem timestamp, robi rolling update usług
i usuwa starą wersję.

---

## 4. Weryfikacja

1. Wejdź na `https://<host>/praktyki-admin/` → powinien przekierować na `login.microsoftonline.com`.
2. Zaloguj się kontem z domeny uczelni.
3. Microsoft przekieruje na `/auth/ms-callback?code=...&state=...` — backend wymieni `code`
   na `id_token`, odczyta `preferred_username` i:
   - sprawdzi, czy domena e-maila jest na liście `ALLOWED_EMAIL_DOMAIN`,
   - znajdzie użytkownika po e-mailu w tabeli `users`,
   - sprawdzi, czy ma rolę dopuszczoną dla danego panelu
     (admin: `ADMIN`/`UOPZ`/`KOMISJA`/`DYREKTOR`; student: `STUDENT`).

### Typowe błędy

| Komunikat                                          | Co sprawdzić                                                            |
|----------------------------------------------------|-------------------------------------------------------------------------|
| `AADSTS50011: redirect_uri mismatch`               | Dodaj dokładny URL `…/auth/ms-callback` w **Uwierzytelnianie**.         |
| `AADSTS700016: app not found in tenant`            | Aplikacja w innej dzierżawie albo zły `AZURE_TENANT_ID`.                |
| `AADSTS7000215: Invalid client secret`             | Wygasł sekret klienta — wygeneruj nowy (pkt 2.1) i zrotuj (3.3).        |
| „Logowanie tylko dla kont uczelnianych"            | `ALLOWED_EMAIL_DOMAIN` nie obejmuje domeny tego konta.                  |
| „Twoje konto Microsoft nie jest zarejestrowane"    | Brak rekordu w `users` — dodaj przez panel admina (lub przez `init.sql` |
|                                                    | dla bootstrap-admina).                                                  |
| „Twoje konto nie ma dostępu do tego panelu"        | User ma tylko `STUDENT`, a wszedł na `/praktyki-admin/` (lub odwrotnie).|

---

## 5. Bootstrap pierwszego admina

Pierwszy admin musi być w bazie **przed** pierwszym logowaniem. Realne adresy
e-mail nie są commitowane do repo — trzymamy je w `database/seed_admins.sql`,
który jest w `.gitignore` i mountowany jako `zz_seed_admins.sql` do kontenera Postgresa
(prefiks `zz_` powoduje, że uruchamia się po `init.sql`).

Przed pierwszym `docker compose up` na serwerze utwórz ten plik:

```sql
-- database/seed_admins.sql
INSERT INTO users (email, password_hash, first_name, last_name, role, is_active, require_password_change)
VALUES
    ('<email@ans-elblag.pl>', '', '<Imie>', '<Nazwisko>', 'ADMIN', TRUE, FALSE)
ON CONFLICT (email) DO NOTHING;

INSERT INTO user_roles (user_id, role)
SELECT id, role FROM users
ON CONFLICT DO NOTHING;
```

`password_hash` zostaje pusty — konta MS nie używają lokalnego hasła.

Po pierwszym logowaniu admin dodaje resztę kont przez panel **Zarządzanie → Użytkownicy**
(lub import CSV studentów). Walidacja formularzy pilnuje, żeby e-mail był w domenie
uczelni — w przeciwnym razie zwraca błąd.
