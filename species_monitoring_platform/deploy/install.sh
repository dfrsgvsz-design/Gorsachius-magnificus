#!/usr/bin/env bash
# Final install: verify imports, .env, user, log dir, systemd unit, start, health check.
set -e
LOG=/var/log/gm-deploy/install.log
mkdir -p /var/log/gm-deploy
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "==== START $(date -Is) ===="

cd /opt/gm-backend

echo "---- venv pkg count ----"
.venv/bin/pip list 2>/dev/null | wc -l

echo "---- key imports ----"
.venv/bin/python - <<'PY'
import importlib
mods = ['fastapi','uvicorn','pydantic','torch','torchaudio','torchvision',
        'librosa','soundfile','timm','numpy','scipy','sklearn','pandas',
        'matplotlib','httpx','requests','PIL','jwt','passlib','bcrypt',
        'aiosqlite','websockets']
for m in mods:
    importlib.import_module(m)
import torch, fastapi
print('ALL_IMPORTS_OK torch=%s fastapi=%s' % (torch.__version__, fastapi.__version__))
PY

echo "---- backend.main import ----"
.venv/bin/python -c 'import backend.main; print("backend.main OK")' || {
  echo 'backend.main import FAILED, attempting with PYTHONPATH'
  PYTHONPATH=/opt/gm-backend .venv/bin/python -c 'import backend.main; print("backend.main OK with PYTHONPATH")'
}

echo "---- create runtime dirs ----"
mkdir -p runtime data output
chmod 755 runtime data output

echo "---- write .env ----"
if [ ! -f .env ]; then
  cp env.production.template .env
  # CORS_ORIGINS already includes capacitor://localhost + http://localhost.
  # Ensure http://36.139.152.185 (port 80 fallback) is also allowed.
  sed -i 's|CORS_ORIGINS=https://36.139.152.185|CORS_ORIGINS=https://36.139.152.185,http://36.139.152.185|' .env
fi
cat .env | grep -E '^(APP_PORT|CORS_ORIGINS)='

echo "---- create gm-backend user ----"
id gm-backend >/dev/null 2>&1 || useradd --system --home /opt/gm-backend --shell /usr/sbin/nologin gm-backend
chown -R gm-backend:gm-backend /opt/gm-backend
mkdir -p /var/log/gm-backend
chown gm-backend:gm-backend /var/log/gm-backend

echo "---- chmod start_linux.sh ----"
chmod +x start_linux.sh

echo "---- install systemd unit ----"
cp gm-backend.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable gm-backend
systemctl restart gm-backend
sleep 3

echo "---- systemctl status ----"
systemctl status gm-backend --no-pager | head -25

echo "---- listen check ----"
ss -tlnp 2>/dev/null | grep -E ':8000|:80|:443' || true

echo "---- /api/health probe ----"
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sS -m 3 http://127.0.0.1:8000/api/health 2>&1 | head -3; then
    echo "HEALTH_OK on attempt $i"
    break
  fi
  echo "attempt $i failed, retrying..."
  sleep 2
done

echo "---- log tails ----"
ls -lh /var/log/gm-backend/
tail -30 /var/log/gm-backend/stderr.log 2>/dev/null || echo 'no stderr.log'
tail -10 /var/log/gm-backend/stdout.log 2>/dev/null || echo 'no stdout.log'

echo "==== END $(date -Is) ===="
echo "INSTALL_DONE_RC_$?"
