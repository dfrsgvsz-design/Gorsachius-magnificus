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

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

require_relative_path() {
  case "$2" in
    /*) die "$1 must stay repo-relative for the field release scripts: $2" ;;
  esac
}

resolve_path() {
  case "$1" in
    /*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$ROOT_DIR" "${1#./}" ;;
  esac
}

load_env() {
  set -a
  . ./.env
  set +a
}

validate_release_env() {
  [ -n "${CORS_ORIGINS:-}" ] || die "CORS_ORIGINS must be set in .env before a controlled go-live deployment."
  case "$CORS_ORIGINS" in
    *localhost*|*127.0.0.1*)
      die "CORS_ORIGINS must use the real field client origin, VPN hostname, or reverse-proxy origin. localhost values are not allowed for controlled go-live."
      ;;
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

require_cmd docker
docker compose version >/dev/null 2>&1 || die "Docker Compose plugin is required."
docker info >/dev/null 2>&1 || die "Docker daemon is not reachable."

if [ ! -f .env ]; then
  die "Missing .env. Copy .env.field-release.template to .env and fill in the real release values before deploying."
fi

load_env
validate_release_env

APP_PORT="${APP_PORT:-8000}"
BSP_APP_DATA_DIR="${BSP_APP_DATA_DIR:-./deploy/pilot/volumes/app-data}"
BSP_BACKEND_DATA_DIR="${BSP_BACKEND_DATA_DIR:-./deploy/pilot/volumes/backend-data}"
BSP_CONFIG_DIR="${BSP_CONFIG_DIR:-./deploy/pilot/volumes/config}"
BSP_LOG_DIR="${BSP_LOG_DIR:-./deploy/pilot/volumes/logs}"
BSP_CHECKPOINTS_DIR="${BSP_CHECKPOINTS_DIR:-./backend/checkpoints}"
BSP_BACKUP_DIR="${BSP_BACKUP_DIR:-./deploy/pilot/backups}"
BSP_HEALTH_TIMEOUT="${BSP_HEALTH_TIMEOUT:-180}"

require_relative_path "BSP_APP_DATA_DIR" "$BSP_APP_DATA_DIR"
require_relative_path "BSP_BACKEND_DATA_DIR" "$BSP_BACKEND_DATA_DIR"
require_relative_path "BSP_CONFIG_DIR" "$BSP_CONFIG_DIR"
require_relative_path "BSP_LOG_DIR" "$BSP_LOG_DIR"
require_relative_path "BSP_CHECKPOINTS_DIR" "$BSP_CHECKPOINTS_DIR"
require_relative_path "BSP_BACKUP_DIR" "$BSP_BACKUP_DIR"

for dir_path in \
  "$BSP_APP_DATA_DIR" \
  "$BSP_BACKEND_DATA_DIR" \
  "$BSP_CONFIG_DIR" \
  "$BSP_LOG_DIR" \
  "$BSP_BACKUP_DIR"
do
  mkdir -p "$(resolve_path "$dir_path")"
done

CHECKPOINT_DIR="$(resolve_path "$BSP_CHECKPOINTS_DIR")"
[ -d "$CHECKPOINT_DIR" ] || die "Checkpoint directory not found: $CHECKPOINT_DIR"
[ -f "$CHECKPOINT_DIR/best_model.pth" ] || die "Missing checkpoint file: $CHECKPOINT_DIR/best_model.pth"
[ -f "$CHECKPOINT_DIR/species_mapping.json" ] || die "Missing checkpoint file: $CHECKPOINT_DIR/species_mapping.json"

docker compose config -q

docker compose up -d --build --remove-orphans

APP_CONTAINER_ID="$(docker compose ps -q app)"
[ -n "$APP_CONTAINER_ID" ] || die "The app container did not start."

if ! wait_for_container_health "$APP_CONTAINER_ID" "$BSP_HEALTH_TIMEOUT"; then
  docker compose ps >&2 || true
  docker compose logs --tail=120 app >&2 || true
  die "Field release deployment did not become healthy within ${BSP_HEALTH_TIMEOUT}s."
fi

docker compose ps

if command -v curl >/dev/null 2>&1; then
  curl -fsS "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null || die "Container is up but the host health endpoint is not responding."
fi

log "Field release deployment is healthy: http://127.0.0.1:${APP_PORT}/api/health"
