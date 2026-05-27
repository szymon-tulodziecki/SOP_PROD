#!/usr/bin/env bash
# scripts/install_cron.sh
#
# Instaluje wpisy cron dla użytkownika `sop`:
#   - backup bazy: codziennie 03:00
#   - uptime-check: co 5 minut
#
# Idempotentny — można odpalać wielokrotnie, wpisy nie duplikują się.
#
# Użycie:
#   chmod +x scripts/*.sh
#   ./scripts/install_cron.sh
#   crontab -l   # weryfikacja

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/sop_prod}"
MARKER="# === SOP cron jobs (managed by install_cron.sh) ==="

NEW_BLOCK=$(cat <<EOF
$MARKER
# Backup bazy codziennie o 03:00
0 3 * * * $PROJECT_DIR/scripts/backup_db.sh
# Uptime check co 5 minut
*/5 * * * * $PROJECT_DIR/scripts/uptime_check.sh
# Sprzątanie logów codziennie o 04:00
0 4 * * * $PROJECT_DIR/scripts/cleanup_logs.sh >> $HOME/logs/cleanup.log 2>&1
# === END SOP cron jobs ===
EOF
)

# Usuń stary blok jeśli istnieje, dopisz nowy
EXISTING=$(crontab -l 2>/dev/null || true)
FILTERED=$(printf '%s\n' "$EXISTING" | sed "/^$MARKER\$/,/^# === END SOP cron jobs ===\$/d")

{
    printf '%s\n' "$FILTERED" | sed '/^$/N;/^\n$/D'
    printf '%s\n' "$NEW_BLOCK"
} | crontab -

echo "Cron zainstalowany. Aktualne wpisy:"
crontab -l
