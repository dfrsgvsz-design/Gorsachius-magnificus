#!/usr/bin/env bash
# fix1: 
#   - install eval_type_backport (FastAPI/Pydantic PEP 604 runtime support on py3.9)
#   - rewrite .env without sort -u corruption
#   - inspect start_linux.sh + ExecStart 203/EXEC root cause
#   - chown + restart + tail logs
set +e
LOG=/var/log/gm-deploy/fix1.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "==== START $(date -Is) ===="
ROOT=/opt/gm-backend
cd "$ROOT"

echo "---- step 1: pip install eval_type_backport ----"
.venv/bin/pip install --no-cache-dir \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --trusted-host pypi.tuna.tsinghua.edu.cn \
  eval_type_backport 2>&1 | tail -5

echo "---- step 2: inspect start_linux.sh ----"
ls -la "$ROOT/start_linux.sh"
file "$ROOT/start_linux.sh"
echo "---- shebang ----"
head -1 "$ROOT/start_linux.sh" | od -c | head -2
echo "---- CRLF? strip ----"
sed -i 's/\r$//' "$ROOT/start_linux.sh"
file "$ROOT/start_linux.sh"

echo "---- step 3: ensure executable ----"
chmod +x "$ROOT/start_linux.sh"
ls -la "$ROOT/start_linux.sh"

echo "---- step 4: rewrite .env (deduped, sorted, valid) ----"
cat > "$ROOT/.env" <<'ENV'
APP_PORT=8000
WEB_CONCURRENCY=1
CORS_ORIGINS=https://36.139.152.185,http://36.139.152.185,http://localhost:5173,capacitor://localhost,https://localhost
BIRD_API_KEY=
XC_API_KEY=
BIRD_PLATFORM_RUNTIME_DIR=/opt/gm-backend/runtime
BIRD_PLATFORM_DATA_DIR=/opt/gm-backend/data
BIRD_PLATFORM_OUTPUT_DIR=/opt/gm-backend/output
PYTHONPATH=/opt/gm-backend
ENV
chown gm-backend:gm-backend "$ROOT/.env"
echo '~~ .env contents ~~'
cat "$ROOT/.env"

echo "---- step 5: chown all ----"
chown -R gm-backend:gm-backend "$ROOT"

echo "---- step 6: import probe (will it work now with eval_type_backport?) ----"
.venv/bin/python -c 'import backend.main; print("backend.main OK")' 2>&1 | tail -10

echo "---- step 7: try direct exec as gm-backend ----"
sudo -u gm-backend "$ROOT/start_linux.sh" --version 2>&1 | head -5 &
START_PID=$!
sleep 3
if kill -0 $START_PID 2>/dev/null; then
  kill $START_PID 2>/dev/null
fi

echo "---- step 8: restart systemd ----"
systemctl daemon-reload
systemctl restart gm-backend
sleep 6

echo "---- step 9: status ----"
systemctl status gm-backend --no-pager | head -30

echo "---- step 10: listen ----"
ss -tlnp 2>/dev/null | grep -E ':8000' || echo 'NO 8000'

echo "---- step 11: probe ----"
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

echo "---- step 12: log tails ----"
echo '~~ stderr.log ~~'
tail -50 /var/log/gm-backend/stderr.log 2>/dev/null
echo '~~ journalctl ~~'
journalctl -u gm-backend --no-pager -n 30 2>/dev/null

echo "==== END $(date -Is) HEALTH=$HEALTH ===="
