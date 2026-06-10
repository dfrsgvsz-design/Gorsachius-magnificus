#!/usr/bin/env bash
# Finalize deployment: untar models, verify imports, create user, install systemd unit, start, health check.
set +e   # don't fail-fast — we want to see all error context
LOG=/var/log/gm-deploy/finalize.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "==== START $(date -Is) ===="

ROOT=/opt/gm-backend

echo "---- step 1: untar backend_models if not present ----"
if [ ! -d "$ROOT/backend/models" ]; then
  cd "$ROOT/backend" && tar xzf /root/backend_models.tar.gz
fi
ls -la "$ROOT/backend/models"

echo "---- step 2: verify backend.main import ----"
cd "$ROOT"
.venv/bin/python -c 'import backend.main; print("backend.main OK")' 2>&1 | tail -25

import_rc=$?
echo "[import rc=$import_rc]"
if [ $import_rc -ne 0 ]; then
  echo "ABORT: import still failing"
  exit 1
fi

echo "---- step 3: create gm-backend user ----"
if ! id gm-backend >/dev/null 2>&1; then
  useradd --system --home "$ROOT" --shell /usr/sbin/nologin gm-backend
fi
id gm-backend

echo "---- step 4: chown + chmod ----"
chown -R gm-backend:gm-backend "$ROOT"
chmod +x "$ROOT/start_linux.sh"

echo "---- step 5: log dir ----"
mkdir -p /var/log/gm-backend
chown gm-backend:gm-backend /var/log/gm-backend

echo "---- step 6: .env ----"
if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/env.production.template" "$ROOT/.env"
  sed -i 's|CORS_ORIGINS=https://36.139.152.185|CORS_ORIGINS=https://36.139.152.185,http://36.139.152.185|' "$ROOT/.env"
  chown gm-backend:gm-backend "$ROOT/.env"
fi
echo "PYTHONPATH=$ROOT" >> "$ROOT/.env"
sort -u "$ROOT/.env" > "$ROOT/.env.tmp" && mv "$ROOT/.env.tmp" "$ROOT/.env"
chown gm-backend:gm-backend "$ROOT/.env"
cat "$ROOT/.env"

echo "---- step 7: install systemd unit ----"
cp "$ROOT/gm-backend.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable gm-backend
systemctl restart gm-backend
sleep 5

echo "---- step 8: status ----"
systemctl status gm-backend --no-pager | head -25

echo "---- step 9: listen check ----"
ss -tlnp 2>/dev/null | grep -E ':8000|:80|:443' || echo 'nothing on 8000/80/443 yet'

echo "---- step 10: /api/health probe (10 attempts) ----"
HEALTH=fail
for i in 1 2 3 4 5 6 7 8 9 10; do
  RESP=$(curl -sS -m 4 http://127.0.0.1:8000/api/health 2>&1)
  RC=$?
  if [ $RC -eq 0 ] && [ -n "$RESP" ]; then
    echo "attempt $i RESP=$RESP"
    HEALTH=ok
    break
  fi
  echo "attempt $i failed (rc=$RC)"
  sleep 2
done

echo "---- step 11: log tails ----"
ls -lh /var/log/gm-backend/ 2>/dev/null
echo '~~ stderr.log ~~'
tail -40 /var/log/gm-backend/stderr.log 2>/dev/null || echo 'no stderr.log'
echo '~~ stdout.log ~~'
tail -10 /var/log/gm-backend/stdout.log 2>/dev/null || echo 'no stdout.log'

echo "==== END $(date -Is) HEALTH=$HEALTH ===="
