#!/usr/bin/env bash
# scripts/uptime_check.sh
#
# Cykliczny health-check serwisów SOP. Loguje status do ~/logs/uptime.log,
# bez wysyłania maili (SMTP nieskonfigurowany). Cron uruchamia co 5 minut.
#
# Sprawdza:
#   - admin   (http://localhost:8080/health)
#   - student (http://localhost:8081/health)
#   - db      (docker exec sop_db pg_isready)
#   - redis   (docker exec sop_redis redis-cli ping)
#   - tex     (docker exec sop_tex_service curl)
#   - fileserver (docker exec sop_fileserver curl)

set -uo pipefail

LOG_DIR="${LOG_DIR:-$HOME/logs}"
LOG_FILE="$LOG_DIR/uptime.log"
TIMEOUT="${TIMEOUT:-5}"

mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { printf '[%s] %s\n' "$(ts)" "$*" >> "$LOG_FILE"; }

check_http() {
    local name="$1" url="$2"
    if curl -sf --max-time "$TIMEOUT" "$url" >/dev/null 2>&1; then
        printf 'OK '
        return 0
    else
        log "DOWN  $name ($url)"
        printf 'DOWN '
        return 1
    fi
}

check_docker() {
    local name="$1" cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        printf 'OK '
        return 0
    else
        log "DOWN  $name (kontener nie odpowiada)"
        printf 'DOWN '
        return 1
    fi
}

# Sprawdza status healthcheck Dockera dla kontenera. Obsługuje "healthy",
# "starting" oraz brak healthchecka (status="none").
check_docker_health() {
    local name="$1" container="$2"
    local health
    health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || echo "missing")
    case "$health" in
        healthy|running) printf 'OK '; return 0 ;;
        starting)        printf 'INIT '; return 0 ;;
        *)               log "DOWN  $name (health=$health)"; printf 'DOWN '; return 1 ;;
    esac
}

STATUS_LINE="$(ts) "
DOWN=0

STATUS_LINE+="admin="
check_http "admin"   "http://localhost:8080/health" || DOWN=$((DOWN+1))
STATUS_LINE+=" student="
check_http "student" "http://localhost:8081/health" || DOWN=$((DOWN+1))
STATUS_LINE+=" db="
check_docker "db"    "docker exec sop_db pg_isready -U ans_admin -d ans_praktyki" || DOWN=$((DOWN+1))
STATUS_LINE+=" redis="
check_docker "redis" "docker exec sop_redis redis-cli ping" || DOWN=$((DOWN+1))
STATUS_LINE+=" tex="
check_docker_health "tex" "sop_tex_service" || DOWN=$((DOWN+1))
STATUS_LINE+=" fileserver="
check_docker_health "fileserver" "sop_fileserver" || DOWN=$((DOWN+1))

# Każdorazowy zapis tylko gdy coś jest down — w przeciwnym razie tylko raz dziennie,
# żeby log nie puchł.
LAST_OK_FILE="$LOG_DIR/.uptime_last_ok_day"
TODAY=$(date '+%Y-%m-%d')

if [[ "$DOWN" -gt 0 ]]; then
    log "STATUS $STATUS_LINE (DOWN=$DOWN)"
    rm -f "$LAST_OK_FILE"
elif [[ ! -f "$LAST_OK_FILE" || "$(cat "$LAST_OK_FILE" 2>/dev/null)" != "$TODAY" ]]; then
    log "STATUS $STATUS_LINE (wszystko OK)"
    echo "$TODAY" > "$LAST_OK_FILE"
fi
