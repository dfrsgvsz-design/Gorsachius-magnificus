#!/usr/bin/env sh
# Daily backup for the systemd (non-docker) gm-backend layout on the ECS host.
# Archives SQLite stores, runtime data and .env from /opt/gm-backend, keeps the
# newest $KEEP archives, never touches .venv or model checkpoints (re-deployable
# from the repo bundle).
#
# Install on the server:
#   scp deploy/backup_remote.sh root@<host>:/opt/gm-backend/backup_remote.sh
#   ssh root@<host> 'chmod +x /opt/gm-backend/backup_remote.sh'
#   ssh root@<host> 'echo "30 3 * * * root /opt/gm-backend/backup_remote.sh >> /var/log/gm-backend/backup.log 2>&1" > /etc/cron.d/gm-backend-backup'
set -eu

APP_DIR="${APP_DIR:-/opt/gm-backend}"
BACKUP_DIR="${BACKUP_DIR:-/root/gm-backups}"
KEEP="${KEEP:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$BACKUP_DIR/gm-backend-$STAMP.tar.gz"

mkdir -p "$BACKUP_DIR"

# Consistent SQLite copies: snapshot DB files with the sqlite3 .backup API when
# available, otherwise fall back to a plain copy (WAL mode keeps this safe
# enough for a nightly baseline).
SNAP_DIR="$(mktemp -d)"
trap 'rm -rf "$SNAP_DIR"' EXIT

find "$APP_DIR" -name '*.db' -not -path '*/.venv/*' | while read -r db; do
  rel="$(echo "$db" | sed "s|^$APP_DIR/||; s|/|__|g")"
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$db" ".backup '$SNAP_DIR/$rel'" || cp -p "$db" "$SNAP_DIR/$rel"
  else
    cp -p "$db" "$SNAP_DIR/$rel"
  fi
done

tar -czf "$ARCHIVE" \
  --exclude='.venv' \
  --exclude='backend/checkpoints' \
  --exclude='*.pt' --exclude='*.pth' --exclude='*.onnx' \
  -C "$APP_DIR" data backend/data .env 2>/dev/null \
  -C "$SNAP_DIR" . || {
    # Some paths may not exist in every layout; retry with the minimum set.
    tar -czf "$ARCHIVE" -C "$SNAP_DIR" .
  }

# Rotate: keep newest $KEEP archives.
ls -1t "$BACKUP_DIR"/gm-backend-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) |
  while read -r old; do rm -f "$old"; done

echo "[backup] $(date -Iseconds) wrote $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1)), keeping $KEEP"
