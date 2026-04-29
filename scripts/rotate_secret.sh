#!/usr/bin/env bash
# scripts/rotate_secret.sh — rotacja jednego sekretu bez downtime
#
# Użycie:
#   ./scripts/rotate_secret.sh <nazwa_sekretu> <plik_nowej_wartosci>
#
# Przykład (rotacja klucza szyfrowania):
#   python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())" > /tmp/new_key.txt
#   ./scripts/rotate_secret.sh file_encryption_key /tmp/new_key.txt
#
# UWAGA: Rotacja FILE_ENCRYPTION_KEY wymaga re-szyfrowania wszystkich plików
#        przed usunięciem starego sekretu. Rotuj pozostałe bez ograniczeń.

set -euo pipefail

SECRET_NAME="${1:?Podaj nazwę sekretu}"
NEW_VALUE_FILE="${2:?Podaj ścieżkę do pliku z nową wartością}"

if ! test -f "$NEW_VALUE_FILE"; then
    echo "ERROR: Plik $NEW_VALUE_FILE nie istnieje" >&2
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OLD_NAME="${SECRET_NAME}_old_${TIMESTAMP}"

echo "=== Rotacja sekretu: $SECRET_NAME ==="

# 1. Utwórz nowy sekret z datą jako tymczasową nazwą
TEMP_NAME="${SECRET_NAME}_new_${TIMESTAMP}"
docker secret create "$TEMP_NAME" "$NEW_VALUE_FILE"
echo "Utworzono tymczasowy sekret: $TEMP_NAME"

# 2. Zaktualizuj serwisy korzystające z sekretu
echo
echo "Aktualizuj serwisy ręcznie (rolling update):"
echo "  docker service update --secret-rm $SECRET_NAME --secret-add source=$TEMP_NAME,target=$SECRET_NAME <nazwa_serwisu>"
echo
echo "Po weryfikacji że serwisy działają poprawnie:"
echo "  docker secret rm $SECRET_NAME"
echo "  docker secret create $SECRET_NAME $NEW_VALUE_FILE"
echo "  docker service update --secret-rm $TEMP_NAME --secret-add $SECRET_NAME <nazwa_serwisu>"
echo "  docker secret rm $TEMP_NAME"
