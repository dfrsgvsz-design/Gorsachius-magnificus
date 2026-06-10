#!/usr/bin/env bash
# Run from /opt/gm-backend after `python -m venv .venv && .venv/bin/pip install -r backend/requirements.txt`
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
export PYTHONUNBUFFERED=1
exec ./.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port "${APP_PORT:-8000}" --workers "${WEB_CONCURRENCY:-1}"