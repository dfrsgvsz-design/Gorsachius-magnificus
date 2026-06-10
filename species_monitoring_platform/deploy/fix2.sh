#!/usr/bin/env bash
# fix2: strip UTF-8 BOM from start_linux.sh (root cause of systemd 203/EXEC),
#       kill orphan uvicorn from earlier test, let systemd own the port.
set +e
LOG=/var/log/gm-deploy/fix2.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "==== START $(date -Is) ===="
ROOT=/opt/gm-backend

echo "---- step 1: identify orphan python on :8000 ----"
ss -tlnp 2>/dev/null | grep ':8000'
PIDS=$(lsof -ti:8000 2>/dev/null)
echo "lsof PIDs on :8000 -> $PIDS"

echo "---- step 2: stop systemd unit (so it doesn't keep flapping) ----"
systemctl stop gm-backend
sleep 1

echo "---- step 3: kill any orphan ----"
if [ -n "$PIDS" ]; then
  echo "killing $PIDS"
  kill -TERM $PIDS 2>&1
  sleep 2
  pgrep -f 'uvicorn.*backend.main' && kill -KILL $(pgrep -f 'uvicorn.*backend.main') 2>&1
fi
sleep 2
ss -tlnp 2>/dev/null | grep ':8000' || echo 'port 8000 free'

echo "---- step 4: strip BOM from start_linux.sh ----"
ls -la "$ROOT/start_linux.sh"
head -c 3 "$ROOT/start_linux.sh" | od -c | head -1
# Use sed to remove BOM
sed -i '1s/^\xEF\xBB\xBF//' "$ROOT/start_linux.sh"
echo "after BOM strip:"
head -c 3 "$ROOT/start_linux.sh" | od -c | head -1
file "$ROOT/start_linux.sh"
head -1 "$ROOT/start_linux.sh"

echo "---- step 5: same BOM scrub on .env (just in case) ----"
sed -i '1s/^\xEF\xBB\xBF//' "$ROOT/.env"
head -c 3 "$ROOT/.env" | od -c | head -1

echo "---- step 6: chmod + chown ----"
chmod +x "$ROOT/start_linux.sh"
chown gm-backend:gm-backend "$ROOT/start_linux.sh" "$ROOT/.env"
ls -la "$ROOT/start_linux.sh"

echo "---- step 7: dry-run as gm-backend (5 second timeout) ----"
timeout 4 sudo -u gm-backend "$ROOT/start_linux.sh" 2>&1 | head -20 &
DR_PID=$!
sleep 5
kill -KILL $DR_PID 2>/dev/null
pkill -KILL -f 'uvicorn.*backend.main' 2>/dev/null
sleep 2

echo "---- step 8: start systemd cleanly ----"
systemctl reset-failed gm-backend
systemctl daemon-reload
systemctl start gm-backend
sleep 6

echo "---- step 9: status ----"
systemctl status gm-backend --no-pager | head -20

echo "---- step 10: listen ----"
ss -tlnp 2>/dev/null | grep ':8000' || echo 'NO 8000'

echo "---- step 11: probe ----"
HEALTH=fail
for i in 1 2 3 4 5 6 7 8 9 10; do
  RESP=$(curl -sS -m 4 http://127.0.0.1:8000/api/health 2>&1)
  RC=$?
  if [ $RC -eq 0 ] && [ -n "$RESP" ]; then
    echo "attempt $i (rc=0): ${RESP:0:120}..."
    HEALTH=ok
    break
  fi
  echo "attempt $i failed rc=$RC"
  sleep 2
done

echo "---- step 12: log tails ----"
echo '~~ stderr.log ~~'
tail -30 /var/log/gm-backend/stderr.log 2>/dev/null
echo '~~ stdout.log ~~'
tail -10 /var/log/gm-backend/stdout.log 2>/dev/null

echo "==== END $(date -Is) HEALTH=$HEALTH ===="
