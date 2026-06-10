#!/usr/bin/env bash
# Set up cloudflared Quick Tunnel forwarding the local 8000/443 to public https URL.
set +e
LOG=/var/log/gm-deploy/cloudflared_setup.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "==== START $(date -Is) ===="

CF_BIN=/usr/local/bin/cloudflared

echo "---- step 1: download cloudflared ----"
if [ -x "$CF_BIN" ]; then
  echo "already present: $($CF_BIN --version 2>&1 | head -1)"
else
  # Try GitHub direct first (slow but reliable in CN sometimes)
  for URL in \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" \
    "https://ghproxy.com/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" \
    "https://mirror.ghproxy.com/https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"; do
    echo "trying $URL"
    if curl -sSL --connect-timeout 10 --max-time 300 -o "$CF_BIN" "$URL"; then
      if [ -s "$CF_BIN" ] && [ "$(stat -c%s "$CF_BIN" 2>/dev/null)" -gt 10000000 ]; then
        echo "downloaded $(stat -c%s "$CF_BIN") bytes"
        break
      else
        echo "download too small ($(stat -c%s "$CF_BIN") bytes), retry"
        rm -f "$CF_BIN"
      fi
    else
      echo "curl rc=$? failed"
    fi
  done
  chmod +x "$CF_BIN"
  ls -la "$CF_BIN"
fi

if [ ! -x "$CF_BIN" ]; then
  echo "FATAL: cloudflared download failed on all mirrors"
  exit 1
fi

echo "---- step 2: cloudflared version ----"
$CF_BIN --version 2>&1 | head -3

echo "---- step 3: launch quick tunnel pointing at nginx 443 (so APK gets full HTTPS chain) ----"
# Quick tunnel: connect Cloudflare edge -> our local 127.0.0.1:443
# We forward to the nginx HTTPS port (with --no-tls-verify since cert is self-signed)
# so APK can use the public trycloudflare URL with proper Cloudflare-issued cert.
TUNNEL_LOG=/var/log/gm-deploy/cloudflared.log
: > "$TUNNEL_LOG"

# Kill any prior tunnel
pkill -KILL -f 'cloudflared tunnel' 2>/dev/null
sleep 1

setsid nohup "$CF_BIN" tunnel --url http://127.0.0.1:8000 --no-autoupdate \
  >> "$TUNNEL_LOG" 2>&1 </dev/null &
disown
sleep 2

echo "---- step 4: wait for tunnel URL ----"
TUNNEL_URL=""
for i in $(seq 1 30); do
  TUNNEL_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1)
  if [ -n "$TUNNEL_URL" ]; then
    echo "found URL after ${i}s: $TUNNEL_URL"
    break
  fi
  sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
  echo "FAIL: no tunnel URL found"
  echo '~~ cloudflared.log ~~'
  tail -30 "$TUNNEL_LOG"
  exit 1
fi

echo "---- step 5: verify tunnel from inside ----"
sleep 3
for i in 1 2 3 4 5; do
  RESP=$(curl -sS -m 8 "${TUNNEL_URL}/api/health" 2>&1)
  RC=$?
  if [ $RC -eq 0 ] && [ -n "$RESP" ]; then
    echo "attempt $i (rc=0): ${RESP:0:160}..."
    break
  fi
  echo "attempt $i failed rc=$RC, sleeping 3s"
  sleep 3
done

echo "---- step 6: persist tunnel URL marker ----"
echo "$TUNNEL_URL" > /opt/gm-backend/.tunnel.url

echo "---- step 7: cloudflared.log tail ----"
tail -20 "$TUNNEL_LOG"

echo "==== END $(date -Is) TUNNEL_URL=$TUNNEL_URL ===="
echo "TUNNEL_URL_FINAL=$TUNNEL_URL"
