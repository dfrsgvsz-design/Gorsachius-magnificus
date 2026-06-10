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

wait_for_container_health() {
  container_id="$1"
  timeout_seconds="$2"
  deadline=$(( $(date +%s) + timeout_seconds ))

  while [ "$(date +%s)" -le "$deadline" ]; do
    state="$(docker inspect -f '{{.State.Status}}' "$container_id" 2>/dev/null || true)"
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' "$container_id" 2>/dev/null || true)"

    if [ "$state" = "running" ] && { [ "$health" = "healthy" ] || [ "$health" = "running" ]; }; then
      return 0
    fi

    if [ "$state" = "exited" ] || [ "$state" = "dead" ]; then
      return 1
    fi

    sleep 5
  done

  return 1
}

validate_archive_paths() {
  tar -tzf "$1" | while IFS= read -r entry; do
    case "$entry" in
      ""|.env|./.env|deploy|deploy/|./deploy|./deploy/|deploy/pilot|deploy/pilot/|./deploy/pilot|./deploy/pilot/|deploy/pilot/volumes|deploy/pilot/volumes/|./deploy/pilot/volumes|./deploy/pilot/volumes/|deploy/pilot/volumes/app-data|deploy/pilot/volumes/app-data/*|./deploy/pilot/volumes/app-data|./deploy/pilot/volumes/app-data/*|deploy/pilot/volumes/backend-data|deploy/pilot/volumes/backend-data/*|./deploy/pilot/volumes/backend-data|./deploy/pilot/volumes/backend-data/*|deploy/pilot/volumes/config|deploy/pilot/volumes/config/*|./deploy/pilot/volumes/config|./deploy/pilot/volumes/config/*|deploy/pilot/volumes/logs|deploy/pilot/volumes/logs/*|./deploy/pilot/volumes/logs|./deploy/pilot/volumes/logs/*)
        ;;
      /*|*\\*|..|../*|*/..|*/../*)
        printf 'Unsafe archive entry rejected: %s\n' "$entry" >&2
        exit 1
        ;;
      *)
        printf 'Unexpected archive entry rejected: %s\n' "$entry" >&2
        exit 1
        ;;
    esac
  done
}

restore_dir() {
  rel_path="$1"
  src="$EXTRACT_DIR/$rel_path"
  dest="$ROOT_DIR/$rel_path"
  parent_dir="$(dirname "$dest")"

  rm -rf "$dest"
  mkdir -p "$parent_dir"

  if [ -d "$src" ]; then
    cp -a "$src" "$dest"
  else
    mkdir -p "$dest"
  fi
}

FORCE=0
if [ "${1:-}" = "--yes" ]; then
  FORCE=1
  shift
fi

if [ "$#" -ne 1 ]; then
  die "Usage: $0 [--yes] /path/to/backup.tar.gz"
fi

ARCHIVE="$1"
[ -f "$ARCHIVE" ] || die "Backup archive not found: $ARCHIVE"

command -v docker >/dev/null 2>&1 || die "Docker is required for restore."
docker compose version >/dev/null 2>&1 || die "Docker Compose plugin is required."
docker info >/dev/null 2>&1 || die "Docker daemon is not reachable."

if [ "$FORCE" -ne 1 ]; then
  printf 'Restore will replace live field release data using %s. Continue? [y/N] ' "$ARCHIVE"
  read -r reply
  case "$reply" in
    y|Y|yes|YES) ;;
    *) die "Restore cancelled." ;;
  esac
fi

validate_archive_paths "$ARCHIVE"

load_env_if_present

BSP_APP_DATA_DIR="${BSP_APP_DATA_DIR:-./deploy/pilot/volumes/app-data}"
BSP_BACKEND_DATA_DIR="${BSP_BACKEND_DATA_DIR:-./deploy/pilot/volumes/backend-data}"
BSP_CONFIG_DIR="${BSP_CONFIG_DIR:-./deploy/pilot/volumes/config}"
BSP_LOG_DIR="${BSP_LOG_DIR:-./deploy/pilot/volumes/logs}"
BSP_HEALTH_TIMEOUT="${BSP_HEALTH_TIMEOUT:-180}"

require_relative_path "BSP_APP_DATA_DIR" "$BSP_APP_DATA_DIR"
require_relative_path "BSP_BACKEND_DATA_DIR" "$BSP_BACKEND_DATA_DIR"
require_relative_path "BSP_CONFIG_DIR" "$BSP_CONFIG_DIR"
require_relative_path "BSP_LOG_DIR" "$BSP_LOG_DIR"

if [ "${SKIP_PRE_RESTORE_BACKUP:-0}" != "1" ]; then
  log "Creating a safety backup before replacing live field release data."
  BSP_RESTART_AFTER_BACKUP=0 sh deploy/pilot/backup.sh
fi

EXTRACT_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$EXTRACT_DIR"
}
trap cleanup 0 HUP INT TERM

tar -xzf "$ARCHIVE" -C "$EXTRACT_DIR"

docker compose down --remove-orphans

restore_dir "$BSP_APP_DATA_DIR"
restore_dir "$BSP_BACKEND_DATA_DIR"
restore_dir "$BSP_CONFIG_DIR"
restore_dir "$BSP_LOG_DIR"

if [ ! -f .env ] && [ -f "$EXTRACT_DIR/.env" ]; then
  cp "$EXTRACT_DIR/.env" .env
  log "Restored .env because it was missing on this host."
elif [ "${RESTORE_ENV:-0}" = "1" ] && [ -f "$EXTRACT_DIR/.env" ]; then
  cp "$EXTRACT_DIR/.env" .env
  log "Restored .env from the backup archive."
else
  log "Kept the current .env. Set RESTORE_ENV=1 if you want the archived .env restored."
fi

docker compose config -q
docker compose up -d --remove-orphans

APP_CONTAINER_ID="$(docker compose ps -q app)"
[ -n "$APP_CONTAINER_ID" ] || die "The app container did not start after restore."

if ! wait_for_container_health "$APP_CONTAINER_ID" "$BSP_HEALTH_TIMEOUT"; then
  docker compose ps >&2 || true
  docker compose logs --tail=120 app >&2 || true
  die "Restore completed the file copy but the app did not become healthy within ${BSP_HEALTH_TIMEOUT}s."
fi

log "Restore complete from $ARCHIVE"
