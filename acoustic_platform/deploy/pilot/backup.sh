#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT_DIR"

log() {
  printf '%s\n' "$*"
}

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

load_env_if_present() {
  if [ -f .env ]; then
    set -a
    . ./.env
    set +a
  fi
}

require_relative_path() {
  case "$2" in
    /*) die "$1 must stay repo-relative for the field release scripts: $2" ;;
  esac
}

app_is_running() {
  container_id="$(docker compose ps -q app 2>/dev/null || true)"
  if [ -z "$container_id" ]; then
    return 1
  fi
  [ "$(docker inspect -f '{{.State.Status}}' "$container_id" 2>/dev/null || true)" = "running" ]
}

restart_if_needed() {
  if [ "${APP_WAS_RUNNING:-0}" -eq 1 ] && [ "${BSP_RESTART_AFTER_BACKUP:-1}" -eq 1 ]; then
    docker compose up -d app >/dev/null
    log "App container restarted after backup."
  fi
}

trap restart_if_needed 0 HUP INT TERM

load_env_if_present

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_DIR:-${BSP_BACKUP_DIR:-deploy/pilot/backups}}"
ARCHIVE="$BACKUP_DIR/biodiversity-field-survey-release-$STAMP.tar.gz"
BSP_APP_DATA_DIR="${BSP_APP_DATA_DIR:-./deploy/pilot/volumes/app-data}"
BSP_BACKEND_DATA_DIR="${BSP_BACKEND_DATA_DIR:-./deploy/pilot/volumes/backend-data}"
BSP_CONFIG_DIR="${BSP_CONFIG_DIR:-./deploy/pilot/volumes/config}"
BSP_LOG_DIR="${BSP_LOG_DIR:-./deploy/pilot/volumes/logs}"

require_relative_path "BACKUP_DIR" "$BACKUP_DIR"
require_relative_path "BSP_APP_DATA_DIR" "$BSP_APP_DATA_DIR"
require_relative_path "BSP_BACKEND_DATA_DIR" "$BSP_BACKEND_DATA_DIR"
require_relative_path "BSP_CONFIG_DIR" "$BSP_CONFIG_DIR"
require_relative_path "BSP_LOG_DIR" "$BSP_LOG_DIR"

mkdir -p "$BACKUP_DIR"

APP_WAS_RUNNING=0
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && app_is_running; then
  APP_WAS_RUNNING=1
  log "Stopping app container for a consistent filesystem backup."
  docker compose stop app >/dev/null
fi

set --
[ -f .env ] && set -- "$@" .env

for rel_path in \
  "$BSP_APP_DATA_DIR" \
  "$BSP_BACKEND_DATA_DIR" \
  "$BSP_CONFIG_DIR" \
  "$BSP_LOG_DIR"
do
  if [ -e "$rel_path" ]; then
    set -- "$@" "$rel_path"
  fi
done

[ "$#" -gt 0 ] || die "Nothing to back up. Create the field release volume directories first."

tar -czf "$ARCHIVE" \
  "$@"

log "Backup created at $ARCHIVE"
