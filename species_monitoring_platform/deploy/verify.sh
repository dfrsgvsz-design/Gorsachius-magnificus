#!/usr/bin/env bash
# Verify backend import after shared/ added; restart systemd; probe /api/health.
set +e
LOG=/var/log/gm-deploy/verify.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "==== START $(date -Is) ===="

cd /opt/gm-backend

echo "---- shared/ tree ----"
find shared -name '*.py' | head -10
echo "(files: $(find shared -name '*.py' | wc -l))"

echo "---- backend.main import (no PYTHONPATH) ----"
.venv/bin/python -c 'import backend.main; print("backend.main OK")' 2>&1 | tail -15

echo "---- backend.main import (PYTHONPATH=/opt/gm-backend) ----"
PYTHONPATH=/opt/gm-backend .venv/bin/python -c 'import backend.main; print("backend.main OK")' 2>&1 | tail -15

echo "---- start_linux.sh content ----"
cat start_linux.sh

echo "---- ensure PYTHONPATH baked into start_linux.sh or .env ----"
if ! grep -q 'PYTHONPATH' .env; then
  echo 'PYTHONPATH=/opt/gm-backend' >> .env
fi
grep PYTHONPATH .env

echo "---- chown ----"
chown -R gm-backend:gm-backend /opt/gm-backend

echo "---- restart systemd ----"
systemctl restart gm-backend
sleep 4
systemctl status gm-backend --no-pager | head -25

echo "---- listen check ----"
ss -tlnp 2>/dev/null | grep -E ':8000|:80|:443' || echo 'nothing on 8000/80/443'

echo "---- /api/health probe (10 attempts) ----"
HEALTH=""
for i in 1 2 3 4 5 6 7 8 9 10; do
  RESP=$(curl -sS -m 4 http://127.0.0.1:8000/api/health 2>&1)
  RC=$?
  if [ $RC -eq 0 ] && [ -n "$RESP" ]; then
    echo "attempt $i: $RESP"
    HEALTH=ok
    break
  fi
  echo "attempt $i failed (rc=$RC): $RESP"
  sleep 2
done

echo "---- log tails ----"
ls -lh /var/log/gm-backend/ 2>/dev/null || true
tail -40 /var/log/gm-backend/stderr.log 2>/dev/null | tail -30 || echo 'no stderr.log'
tail -10 /var/log/gm-backend/stdout.log 2>/dev/null || echo 'no stdout.log'

echo "==== END $(date -Is) HEALTH=$HEALTH ===="
