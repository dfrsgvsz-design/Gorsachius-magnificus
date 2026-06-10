#!/usr/bin/env bash
# Nginx + self-signed SSL + reverse proxy 443 -> 127.0.0.1:8000 (FastAPI uvicorn).
set -e
LOG=/var/log/gm-deploy/nginx_setup.log
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "==== START $(date -Is) ===="

echo "---- step 1: yum install nginx + openssl ----"
yum install -y nginx openssl 2>&1 | tail -10
nginx -v 2>&1
openssl version

echo "---- step 2: generate self-signed cert ----"
SSL_DIR=/etc/nginx/ssl
mkdir -p "$SSL_DIR"
if [ ! -f "$SSL_DIR/gm.crt" ]; then
  openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
    -keyout "$SSL_DIR/gm.key" \
    -out "$SSL_DIR/gm.crt" \
    -subj "/CN=36.139.152.185/O=Gorsachius Magnificus Survey/C=CN" \
    -addext "subjectAltName=IP:36.139.152.185,DNS:gm-backend.local" 2>&1 | tail -3
  chmod 600 "$SSL_DIR/gm.key"
fi
ls -la "$SSL_DIR/"
openssl x509 -in "$SSL_DIR/gm.crt" -noout -subject -issuer -dates -ext subjectAltName

echo "---- step 3: nginx site config ----"
cat > /etc/nginx/conf.d/gm-backend.conf <<'NGINX'
# HTTP -> HTTPS redirect
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 301 https://$host$request_uri;
}

# HTTPS reverse proxy to FastAPI uvicorn
server {
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/gm.crt;
    ssl_certificate_key /etc/nginx/ssl/gm.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    client_max_body_size 50M;

    # Strict timeouts to avoid worker exhaustion
    proxy_connect_timeout 60s;
    proxy_send_timeout    300s;
    proxy_read_timeout    300s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # WebSocket upgrade
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX

# Disable default vhost on port 80 if it exists
if [ -f /etc/nginx/nginx.conf ]; then
  sed -i '/^\s*server\s*{/,/^\s*}/ {
    /listen.*80 default_server/d
    /listen.*\[::\]:80 default_server/d
  }' /etc/nginx/nginx.conf 2>/dev/null || true
fi

echo "---- step 4: nginx config test ----"
nginx -t 2>&1

# If main nginx.conf has duplicate default server block, comment out the default server in it
if ! nginx -t 2>&1 | grep -q 'syntax is ok'; then
  echo "nginx -t failed, applying fallback (move our conf into stand-alone setup)"
  # Find and remove default server block in nginx.conf
  python3 - <<'PY'
import re
p = '/etc/nginx/nginx.conf'
src = open(p).read()
# Comment out 'listen 80 default_server' lines in main nginx.conf to avoid duplicate
src = re.sub(r'(\s+)(listen\s+\[?:?:?]?:?\s*80(\s+default_server)?\s*;)', r'\1# \2  # disabled by gm-backend setup', src)
open(p, 'w').write(src)
print('patched nginx.conf')
PY
  nginx -t 2>&1
fi

echo "---- step 5: enable + start nginx ----"
systemctl enable nginx
systemctl restart nginx
sleep 2
systemctl status nginx --no-pager | head -10

echo "---- step 6: listen check ----"
ss -tlnp 2>/dev/null | grep -E ':80|:443'

echo "---- step 7: local probe https://127.0.0.1/api/health (-k self-signed) ----"
for i in 1 2 3 4 5; do
  RESP=$(curl -sS -k -m 5 https://127.0.0.1/api/health 2>&1)
  RC=$?
  if [ $RC -eq 0 ] && [ -n "$RESP" ]; then
    echo "attempt $i (rc=0): ${RESP:0:160}..."
    break
  fi
  echo "attempt $i failed rc=$RC"
  sleep 1
done

echo "---- step 8: also probe via IP 36.139.152.185 from inside ----"
curl -sS -k -m 5 https://36.139.152.185/api/health 2>&1 | head -c 200
echo ""

echo "---- step 9: firewalld setup ----"
systemctl enable firewalld 2>&1 | tail -2
systemctl start firewalld
sleep 1
firewall-cmd --state
firewall-cmd --permanent --add-port=80/tcp 2>&1
firewall-cmd --permanent --add-port=443/tcp 2>&1
firewall-cmd --reload
firewall-cmd --list-ports

echo "==== END $(date -Is) ===="
