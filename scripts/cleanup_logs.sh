#!/usr/bin/env bash
# scripts/cleanup_logs.sh
#
# Automatyczne sprzątanie logów żeby nie zapchać dysku.
# Cron uruchamia codziennie o 04:00 (patrz install_cron.sh).
#
# Co robi:
#   1. Przycina ~/logs/uptime.log i ~/backups/backup.log do ostatnich N linii
#      (gdy plik przekroczy limit rozmiaru).
#   2. Czyści docker container logs (przez `docker logs` → truncate).
#   3. Logi aplikacji (app_admin, app_student) rotują się same przez
#      RotatingFileHandler (1 MB × 5 plików = ~5 MB max).

set -uo pipefail

LOG_DIR="${LOG_DIR:-$HOME/logs}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
MAX_LINES="${MAX_LINES:-5000}"     # ile linii zostawić w długich logach
MAX_SIZE_MB="${MAX_SIZE_MB:-10}"   # próg powyżej którego trimujemy

ts() { date '+%Y-%m-%d %H:%M:%S'; }
report() { printf '[%s] %s\n' "$(ts)" "$*"; }

trim_log() {
    local file="$1"
    [[ -f "$file" ]] || return 0
    local size_mb
    size_mb=$(( $(stat -c '%s' "$file") / 1024 / 1024 ))
    if [[ "$size_mb" -ge "$MAX_SIZE_MB" ]]; then
        tail -n "$MAX_LINES" "$file" > "${file}.tmp" && mv "${file}.tmp" "$file"
        report "TRIM $file (>${MAX_SIZE_MB} MB) → ostatnie $MAX_LINES linii"
    fi
}

# 1. Logi host-cron
trim_log "$LOG_DIR/uptime.log"
trim_log "$BACKUP_DIR/backup.log"

# 2. Logi kontenerów dockerowych — przycinamy te które rozjeżdżają się powyżej 50 MB
for container in $(docker ps --format '{{.Names}}' 2>/dev/null); do
    log_path=$(docker inspect --format='{{.LogPath}}' "$container" 2>/dev/null || true)
    if [[ -n "$log_path" && -f "$log_path" ]]; then
        size_mb=$(( $(sudo stat -c '%s' "$log_path" 2>/dev/null || stat -c '%s' "$log_path" 2>/dev/null || echo 0) / 1024 / 1024 ))
        if [[ "$size_mb" -ge 50 ]]; then
            # truncate wymaga roota — wymaga uprawnień sudo bez hasła do truncate
            sudo truncate -s 0 "$log_path" 2>/dev/null \
                && report "TRUNC docker log $container (${size_mb} MB)" \
                || report "SKIP  docker log $container (${size_mb} MB) — brak sudo"
        fi
    fi
done

report "DONE cleanup_logs"
