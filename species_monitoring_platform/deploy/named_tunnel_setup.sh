#!/usr/bin/env bash
# Named tunnel setup for swdyx.eu.cc / gm-api.swdyx.eu.cc.
# Prerequisites:
#   - NS for swdyx.eu.cc successfully delegated to Cloudflare
#     (verified by `dig NS swdyx.eu.cc` returning kia/achiel.ns.cloudflare.com)
#   - User has authorised cloudflared via browser (cert.pem in /root/.cloudflared/)
#
# This script is idempotent: re-running it skips already-completed steps.
set +e
LOG=/var/log/gm-deploy/named_tunnel_setup.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

DOMAIN="swdyx.eu.cc"
HOSTNAME="gm-api.swdyx.eu.cc"
TUNNEL_NAME="gm-backend"
CF_DIR="/root/.cloudflared"

echo "==== START $(date -Is) ===="
echo "Target hostname: $HOSTNAME"
echo "Tunnel name:     $TUNNEL_NAME"

echo "---- step 1: verify cert.pem exists ----"
if [ ! -f "$CF_DIR/cert.pem" ]; then
  echo "FATAL: $CF_DIR/cert.pem missing."
  echo "Run: cloudflared tunnel login"
  echo "Open the printed URL in your browser, sign in to Cloudflare, select $DOMAIN, click Authorize."
  echo "cert.pem will be downloaded to $CF_DIR/."
  exit 1
fi
ls -la "$CF_DIR/cert.pem"

echo "---- step 2: NS active check ----"
NS_OK=0
for i in 1 2 3; do
  CURR_NS=$(dig +short NS "$DOMAIN" 2>/dev/null | sort)
  echo "attempt $i: NS = $CURR_NS"
  if echo "$CURR_NS" | grep -q 'cloudflare.com'; then
    NS_OK=1
    break
  fi
  sleep 3
done
if [ $NS_OK -ne 1 ]; then
  echo "WARN: NS for $DOMAIN does not yet point to Cloudflare. Continue anyway."
fi

echo "---- step 3: check existing tunnel ----"
EXISTING=$(/usr/local/bin/cloudflared tunnel list 2>/dev/null | grep -E "\\b${TUNNEL_NAME}\\b" | awk '{print $1}')
if [ -n "$EXISTING" ]; then
  echo "tunnel $TUNNEL_NAME already exists: $EXISTING"
  TUNNEL_UUID="$EXISTING"
else
  echo "creating new tunnel $TUNNEL_NAME"
  /usr/local/bin/cloudflared tunnel create "$TUNNEL_NAME" 2>&1
  TUNNEL_UUID=$(/usr/local/bin/cloudflared tunnel list 2>/dev/null | grep -E "\\b${TUNNEL_NAME}\\b" | awk '{print $1}')
fi
echo "TUNNEL_UUID=$TUNNEL_UUID"

if [ -z "$TUNNEL_UUID" ]; then
  echo "FATAL: tunnel UUID not obtained"
  exit 1
fi

echo "---- step 4: route DNS ----"
/usr/local/bin/cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME" 2>&1

echo "---- step 5: write config.yml ----"
cat > "$CF_DIR/config.yml" <<CONFIG
tunnel: $TUNNEL_UUID
credentials-file: $CF_DIR/$TUNNEL_UUID.json

# Suppress automatic edge config polling if it interferes with custom ingress
no-autoupdate: true

ingress:
  - hostname: $HOSTNAME
    service: http://127.0.0.1:8000
    originRequest:
      connectTimeout: 30s
      noHappyEyeballs: true
  - service: http_status:404
CONFIG
chown -R gm-backend:gm-backend "$CF_DIR"
ls -la "$CF_DIR/"

echo "---- step 6: validate config ----"
/usr/local/bin/cloudflared tunnel --config "$CF_DIR/config.yml" ingress validate 2>&1

echo "---- step 7: stop quick tunnel (will be replaced by named tunnel) ----"
systemctl stop cloudflared-tunnel.service
systemctl disable cloudflared-tunnel.service

echo "---- step 8: install new systemd unit (named tunnel) ----"
cat > /etc/systemd/system/cloudflared-tunnel.service <<'UNIT'
[Unit]
Description=Cloudflared Named Tunnel for gm-backend (gm-api.swdyx.eu.cc)
After=network-online.target gm-backend.service
Wants=network-online.target

[Service]
Type=simple
User=gm-backend
Group=gm-backend
ExecStart=/usr/local/bin/cloudflared --config /root/.cloudflared/config.yml tunnel run
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/gm-backend/cloudflared.log
StandardError=append:/var/log/gm-backend/cloudflared.log
# Hardening
ProtectSystem=strict
PrivateTmp=true
NoNewPrivileges=true
ReadWritePaths=/var/log/gm-backend /root/.cloudflared

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable cloudflared-tunnel.service
systemctl start cloudflared-tunnel.service
sleep 6

echo "---- step 9: status ----"
systemctl status cloudflared-tunnel --no-pager | head -20

echo "---- step 10: verify external reachability ----"
sleep 5
for i in 1 2 3 4 5 6; do
  RESP=$(curl -sS -m 8 "https://$HOSTNAME/api/health" 2>&1)
  RC=$?
  if [ $RC -eq 0 ] && [ -n "$RESP" ]; then
    echo "attempt $i (rc=0): ${RESP:0:200}..."
    break
  fi
  echo "attempt $i failed rc=$RC: $RESP"
  sleep 4
done

echo "---- step 11: persist marker ----"
echo "https://$HOSTNAME" > /opt/gm-backend/.tunnel.url
chown gm-backend:gm-backend /opt/gm-backend/.tunnel.url

echo "==== END $(date -Is) ===="
echo "PERMANENT_URL=https://$HOSTNAME"
