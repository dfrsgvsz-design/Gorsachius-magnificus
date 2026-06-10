# gm-backend deploy bundle

Contents of this archive (for the remote `Administrator@36.139.152.185` server):

```
backend/                          FastAPI Python source (~3 MB, no caches/tests/logs)
backend/checkpoints/
  best_model.pth                  43.5 MB  CNN student model (mandatory)
  species_mapping.json            <0.1 MB  species_id -> name (mandatory)
backend/data/
  china_birds.json                0.5 MB   reference list
  vertebrate_export_profiles.json 0.1 MB
backend/requirements.txt          Python deps (CPU torch wheel works without GPU)
env.production.template           Copy to .env on the server, then edit CORS_ORIGINS
start_linux.sh                    systemd ExecStart entry (chmod +x first)
gm-backend.service                /etc/systemd/system/gm-backend.service
start_windows.ps1                 Windows alternative (use NSSM to wrap as service)
```

## Linux install (Ubuntu/Debian/CentOS)

```bash
sudo mkdir -p /opt/gm-backend && sudo chown $(whoami) /opt/gm-backend
cd /opt/gm-backend
tar xzf ~/gm-server-bundle.tar.gz
chmod +x start_linux.sh
cp env.production.template .env
nano .env       # edit CORS_ORIGINS

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r backend/requirements.txt

sudo useradd --system --home /opt/gm-backend --shell /usr/sbin/nologin gm-backend
sudo chown -R gm-backend:gm-backend /opt/gm-backend
sudo mkdir -p /var/log/gm-backend && sudo chown gm-backend:gm-backend /var/log/gm-backend
sudo cp gm-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gm-backend
sudo systemctl status gm-backend
curl -sS http://127.0.0.1:8000/api/health | head
```

## Windows Server install

```powershell
$dir = 'C:\gm-backend'
New-Item -ItemType Directory -Path $dir -Force | Out-Null
Set-Location $dir
tar xzf "$env:USERPROFILE\gm-server-bundle.tar.gz"
Copy-Item env.production.template .env
notepad .env

python -m venv .venv
.\.venv\Scripts\pip install --upgrade pip
.\.venv\Scripts\pip install -r backend\requirements.txt
```

Wrap in NSSM as a Windows service:

1. Download nssm.cc and put nssm.exe on PATH
2. `nssm install gm-backend C:\gm-backend\.venv\Scripts\python.exe`
3. `nssm set gm-backend AppParameters "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000"`
4. `nssm set gm-backend AppDirectory C:\gm-backend`
5. `nssm start gm-backend`

## Open firewall

Linux ufw:
```bash
sudo ufw allow 443/tcp comment 'gm-backend HTTPS'
```

Windows:
```powershell
New-NetFirewallRule -DisplayName 'gm-backend HTTPS' -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow
```

## HTTPS via nginx + self-signed cert (no domain)

```bash
sudo apt install -y nginx
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/gm.key -out /etc/nginx/ssl/gm.crt \
  -subj "/CN=36.139.152.185" \
  -addext "subjectAltName=IP:36.139.152.185"
```

Nginx site config writes a `server` block on port 443 with `ssl_certificate /etc/nginx/ssl/gm.crt`, `ssl_certificate_key /etc/nginx/ssl/gm.key`, `client_max_body_size 50M`, and `proxy_pass http://127.0.0.1:8000;` with WebSocket upgrade headers.

The APK then needs `network_security_config.xml` to trust the self-signed cert (or use a real domain + Let's Encrypt).
