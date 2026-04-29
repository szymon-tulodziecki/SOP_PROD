# Sekrety aplikacji SOP

Każdy sekret to osobny plik tekstowy zawierający wyłącznie wartość (bez cudzysłowów, bez nowej linii na końcu).

## Wymagane pliki

| Plik | Opis |
|------|------|
| `secret_key.txt` | Klucz Flask (sesje, CSRF) — generuj: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `postgres_password.txt` | Hasło PostgreSQL |
| `file_encryption_key.txt` | Klucz AES-256 (base64url 32B) — generuj: `python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` |
| `azure_client_id.txt` | Azure AD — Client ID aplikacji |
| `azure_client_secret.txt` | Azure AD — Client Secret |
| `azure_tenant_id.txt` | Azure AD — Tenant ID |
| `fileserver_api_key.txt` | Klucz API do wewnętrznego fileserwera |

## Tworzenie sekretów (jednorazowe)

```bash
# Wygeneruj i zapisz (przykład)
python -c "import secrets; print(secrets.token_hex(32))" > secrets/secret_key.txt
python -c "import secrets; print(secrets.token_hex(24))" > secrets/postgres_password.txt
python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())" > secrets/file_encryption_key.txt
python -c "import secrets; print(secrets.token_hex(24))" > secrets/fileserver_api_key.txt
# azure_* — skopiuj z Azure Portal
```

## Bezpieczeństwo

- Pliki `*.txt` są wykluczone przez `.gitignore` — nigdy nie trafiają do repozytorium
- W środowisku produkcyjnym (Docker Swarm) pliki są zarządzane przez `docker secret create`
- W środowisku lokalnym (Compose) pliki są bind-mountowane z tego katalogu
