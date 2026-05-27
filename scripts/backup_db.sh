#!/usr/bin/env bash
# scripts/backup_db.sh
#
# Dump bazy Postgresa z kontenera sop_db do ~/backups/ z 14-dniową retencją.
# Uruchamiany przez cron (patrz scripts/install_cron.sh).
#
# Format pliku: backup_YYYY-MM-DD_HHMM.sql.gz
# Logi: ~/backups/backup.log

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
CONTAINER="${DB_CONTAINER:-sop_db}"
DB_USER="${DB_USER:-ans_admin}"
DB_NAME="${DB_NAME:-ans_praktyki}"
LOG_FILE="$BACKUP_DIR/backup.log"

mkdir -p "$BACKUP_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { printf '[%s] %s\n' "$(ts)" "$*" >> "$LOG_FILE"; }

STAMP=$(date '+%Y-%m-%d_%H%M')
OUT="$BACKUP_DIR/backup_${STAMP}.sql.gz"

log "START backup → $OUT"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    log "ERROR: kontener '$CONTAINER' nie jest uruchomiony"
    exit 1
fi

if docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --clean --if-exists \
   | gzip > "$OUT"; then
    SIZE=$(du -h "$OUT" | cut -f1)
    log "OK    backup ukończony ($SIZE)"
else
    log "ERROR pg_dump nie powiódł się"
    rm -f "$OUT"
    exit 1
fi

# Usuń pliki starsze niż RETENTION_DAYS
DELETED=$(find "$BACKUP_DIR" -maxdepth 1 -name 'backup_*.sql.gz' -mtime "+${RETENTION_DAYS}" -print -delete | wc -l)
if [[ "$DELETED" -gt 0 ]]; then
    log "CLEAN usunięto $DELETED starych backup-ów (>${RETENTION_DAYS} dni)"
fi

log "END   (aktualnie w katalogu: $(ls -1 "$BACKUP_DIR"/backup_*.sql.gz 2>/dev/null | wc -l) plików)"
