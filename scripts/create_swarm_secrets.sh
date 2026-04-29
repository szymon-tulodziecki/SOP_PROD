#!/usr/bin/env bash
# scripts/create_swarm_secrets.sh
#
# Jednorazowe tworzenie sekretów Docker Swarm na węźle manager.
# Uruchom PRZED: docker stack deploy -c docker-stack.yml sop
#
# Użycie:
#   chmod +x scripts/create_swarm_secrets.sh
#   ./scripts/create_swarm_secrets.sh
#
# Jeśli sekret już istnieje, skrypt pomija go (idempotentny).

set -euo pipefail

SECRETS_DIR="${1:-./secrets}"

create_secret() {
    local name="$1"
    local file="$SECRETS_DIR/$name.txt"

    if ! test -f "$file"; then
        echo "ERROR: Brak pliku $file" >&2
        exit 1
    fi

    if docker secret inspect "$name" &>/dev/null; then
        echo "SKIP  $name (już istnieje)"
    else
        docker secret create "$name" "$file"
        echo "OK    $name"
    fi
}

echo "=== Tworzenie sekretów Docker Swarm ==="
echo "Katalog sekretów: $SECRETS_DIR"
echo

create_secret secret_key
create_secret postgres_password
create_secret file_encryption_key
create_secret azure_client_id
create_secret azure_client_secret
create_secret azure_tenant_id
create_secret fileserver_api_key

echo
echo "=== Gotowe. Aktualny stan sekretów ==="
docker secret ls
