#!/usr/bin/env bash
# scripts/setup_swarm_secrets.sh
#
# Jednorazowa, interaktywna instalacja sekretów Docker Swarm dla SOP.
# - Pyta o trzy wartości z Azure (Tenant ID, Client ID, Client Secret)
# - Sam generuje pozostałe sekrety (klucz sesji, hasło bazy, klucz Fernet, API key)
# - Tworzy sekrety w Docker Swarm i nadpisuje istniejące (z rotacją).
#
# Wymagania: docker, openssl, python3 z modułem cryptography
#
# Użycie:
#   chmod +x scripts/setup_swarm_secrets.sh
#   ./scripts/setup_swarm_secrets.sh

set -euo pipefail

# ── kolory ────────────────────────────────────────────────────────────────────
RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'

info()  { printf "%s[i]%s %s\n"   "$YELLOW" "$NC" "$*"; }
ok()    { printf "%s[OK]%s %s\n"  "$GREEN"  "$NC" "$*"; }
fail()  { printf "%s[!]%s %s\n"   "$RED"    "$NC" "$*" >&2; }

require() {
    command -v "$1" >/dev/null 2>&1 || { fail "Brakuje polecenia: $1"; exit 1; }
}

require docker
require openssl
require python3

# ── sprawdzenie Swarma ────────────────────────────────────────────────────────
if ! docker info --format '{{.Swarm.LocalNodeState}}' 2>/dev/null | grep -q '^active$'; then
    fail "Docker nie jest w trybie Swarm. Uruchom najpierw: docker swarm init"
    exit 1
fi

# ── walidacja GUID ────────────────────────────────────────────────────────────
GUID_RE='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

read_guid() {
    local prompt="$1" var
    while true; do
        printf "%s: " "$prompt" >&2
        read -r var
        if [[ "$var" =~ $GUID_RE ]]; then
            printf '%s' "$var"
            return
        fi
        fail "Wartość nie wygląda na GUID (format: 00000000-0000-0000-0000-000000000000). Spróbuj ponownie."
    done
}

read_secret() {
    local prompt="$1" var
    while true; do
        printf "%s (nie pojawi się na ekranie): " "$prompt" >&2
        read -rs var
        printf "\n" >&2
        if [[ -n "$var" ]]; then
            printf '%s' "$var"
            return
        fi
        fail "Wartość nie może być pusta." >&2
    done
}

# ── tworzenie sekretu (z rotacją starego) ─────────────────────────────────────
put_secret() {
    local name="$1" value="$2"
    if docker secret inspect "$name" >/dev/null 2>&1; then
        info "Sekret '$name' już istnieje — rotuję (nowa wersja)."
        local old_id new_name
        new_name="${name}_$(date +%Y%m%d%H%M%S)"
        old_id=$(docker secret inspect "$name" --format '{{.ID}}')
        printf '%s' "$value" | docker secret create "$new_name" - >/dev/null
        ok "Utworzono '$new_name'. Stary sekret '$name' (ID $old_id) usuń ręcznie po wdrożeniu stack-u."
        info "Pamiętaj zaktualizować nazwę w docker-stack.yml (lub użyj ./scripts/rotate_secret.sh)."
    else
        printf '%s' "$value" | docker secret create "$name" - >/dev/null
        ok "Utworzono sekret '$name'."
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
echo
echo "=== Konfiguracja sekretów SOP w Docker Swarm ==="
echo "Wpisz dane z portalu Microsoft Entra ID (https://entra.microsoft.com)."
echo

AZURE_TENANT_ID=$(read_guid "Tenant ID (Identyfikator katalogu)")
AZURE_CLIENT_ID=$(read_guid "Client ID (Application ID)")
AZURE_CLIENT_SECRET=$(read_secret "Client Secret (Wartość — nie ID)")

echo
info "Generuję pozostałe sekrety lokalnie…"
SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n')
POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d '\n=+/' | cut -c1-32)
FILE_ENCRYPTION_KEY=$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
FILESERVER_API_KEY=$(openssl rand -hex 32)
ok "Wygenerowano: secret_key, postgres_password, file_encryption_key, fileserver_api_key."

echo
info "Tworzę sekrety w Docker Swarm…"
put_secret azure_tenant_id     "$AZURE_TENANT_ID"
put_secret azure_client_id     "$AZURE_CLIENT_ID"
put_secret azure_client_secret "$AZURE_CLIENT_SECRET"
put_secret secret_key          "$SECRET_KEY"
put_secret postgres_password   "$POSTGRES_PASSWORD"
put_secret file_encryption_key "$FILE_ENCRYPTION_KEY"
put_secret fileserver_api_key  "$FILESERVER_API_KEY"

# zerowanie zmiennych ze wrażliwymi danymi
unset AZURE_TENANT_ID AZURE_CLIENT_ID AZURE_CLIENT_SECRET
unset SECRET_KEY POSTGRES_PASSWORD FILE_ENCRYPTION_KEY FILESERVER_API_KEY

echo
ok "Gotowe. Aktualne sekrety w Swarmie:"
docker secret ls

cat <<'EOF'

Następny krok:
  docker stack deploy -c docker-stack.yml sop

EOF
