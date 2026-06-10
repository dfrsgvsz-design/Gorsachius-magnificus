#!/usr/bin/env bash
# Phase 1: launch `cloudflared tunnel login` in background, capture browser URL.
# User opens URL in own browser, signs in to Cloudflare Dfrsgvsz@gmail.com,
# selects swdyx.eu.cc, clicks Authorize. cert.pem then lands in ~/.cloudflared/.
set +e
LOG=/var/log/gm-deploy/named_tunnel_phase1.log
: > "$LOG"

CF_DIR=/root/.cloudflared
mkdir -p "$CF_DIR"
chmod 700 "$CF_DIR"

echo "==== START $(date -Is) ====" | tee -a "$LOG"

# If cert.pem already exists, skip login.
if [ -f "$CF_DIR/cert.pem" ]; then
  echo "cert.pem already exists, skipping login" | tee -a "$LOG"
  ls -la "$CF_DIR/cert.pem" | tee -a "$LOG"
  exit 0
fi

# Kill any stale login process
pkill -KILL -f 'cloudflared tunnel login' 2>/dev/null
sleep 1

# Launch login in background, redirect output to log
echo "launching cloudflared tunnel login (headless)..." | tee -a "$LOG"
setsid nohup /usr/local/bin/cloudflared tunnel login \
  >> "$LOG" 2>&1 </dev/null &
LOGIN_PID=$!
disown
echo "LOGIN_PID=$LOGIN_PID" | tee -a "$LOG"
sleep 3

# Wait for the OAuth URL to appear in the log
URL=""
for i in $(seq 1 15); do
  URL=$(grep -oE 'https://dash\.cloudflare\.com/argotunnel\?[^[:space:]]+' "$LOG" 2>/dev/null | head -1)
  if [ -n "$URL" ]; then
    break
  fi
  sleep 1
done

if [ -z "$URL" ]; then
  echo "FAIL: did not capture OAuth URL after 15s. Log tail:" | tee -a "$LOG"
  tail -20 "$LOG"
  exit 1
fi

echo "" | tee -a "$LOG"
echo "================ OAUTH URL ================" | tee -a "$LOG"
echo "$URL" | tee -a "$LOG"
echo "===========================================" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Open this URL in your browser." | tee -a "$LOG"
echo "Sign in to Cloudflare (Dfrsgvsz@gmail.com)." | tee -a "$LOG"
echo "Select swdyx.eu.cc and click 'Authorize'." | tee -a "$LOG"
echo "cloudflared will then write cert.pem to $CF_DIR/" | tee -a "$LOG"

echo "OAUTH_URL_FINAL=$URL"
