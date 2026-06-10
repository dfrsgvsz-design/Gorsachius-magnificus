#!/usr/bin/env bash
# Persist cloudflared as systemd service.
# Note: Quick tunnel URLs are EPHEMERAL — they change every restart.
# This unit ensures the tunnel stays up while the machine is up; if the
# machine reboots, the URL changes and APK needs to be re-built.
# For a stable URL, use a Cloudflare named tunnel + your own domain.
set -e
LOG=/var/log/gm-deploy/cloudflared_persist.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "==== START $(date -Is) ===="

echo "---- step 1: kill ad-hoc tunnel from cloudflared_setup.sh ----"
pkill -KILL -f 'cloudflared tunnel' 2>/dev/null
sleep 1
pgrep -af cloudflared || echo NONE

echo "---- step 2: write systemd unit ----"
cat > /etc/systemd/system/cloudflared-tunnel.service <<'UNIT'
[Unit]
Description=Cloudflared Quick Tunnel for gm-backend (ephemeral URL)
After=network-online.target gm-backend.service
Wants=network-online.target
PartOf=gm-backend.service

[Service]
Type=simple
User=gm-backend
Group=gm-backend
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/gm-backend/cloudflared.log
StandardError=append:/var/log/gm-backend/cloudflared.log
# Hardening
ProtectSystem=strict
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT

# Ensure log file exists
touch /var/log/gm-backend/cloudflared.log
chown gm-backend:gm-backend /var/log/gm-backend/cloudflared.log

echo "---- step 3: enable + start ----"
systemctl daemon-reload
systemctl enable cloudflared-tunnel.service
systemctl restart cloudflared-tunnel.service
sleep 6

echo "---- step 4: status ----"
systemctl status cloudflared-tunnel.service --no-pager | head -20

echo "---- step 5: extract tunnel URL ----"
TUNNEL_URL=""
for i in $(seq 1 20); do
  TUNNEL_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' /var/log/gm-backend/cloudflared.log 2>/dev/null | tail -1)
  if [ -n "$TUNNEL_URL" ]; then
    echo "URL after ${i}s: $TUNNEL_URL"
    break
  fi
  sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
  echo "FAIL: no URL"
  tail -20 /var/log/gm-backend/cloudflared.log
  exit 1
fi

echo "$TUNNEL_URL" > /opt/gm-backend/.tunnel.url
chown gm-backend:gm-backend /opt/gm-backend/.tunnel.url

echo "---- step 6: verify tunnel from inside ----"
sleep 3
for i in 1 2 3 4 5; do
  RESP=$(curl -sS -m 8 "${TUNNEL_URL}/api/health" 2>&1)
  RC=$?
  if [ $RC -eq 0 ] && [ -n "$RESP" ]; then
    echo "attempt $i (rc=0): ${RESP:0:160}..."
    break
  fi
  echo "attempt $i failed rc=$RC"
  sleep 3
done

echo "==== END $(date -Is) TUNNEL_URL=$TUNNEL_URL ===="
echo "TUNNEL_URL_FINAL=$TUNNEL_URL"
