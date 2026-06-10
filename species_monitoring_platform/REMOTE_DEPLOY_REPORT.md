# 远程部署完成报告 — 36.139.152.185

**日期**: 2026-04-26
**目标**: gm-backend 部署到 BigCloud ECS (root@36.139.152.185)
**结果**: ✅ **Host 层 100% 跑通** ⚠️ **需用户在云 ECS 控制台开 80/443 入站**

---

## 一、远程环境

| 项目 | 状态 |
|---|---|
| **OS** | BigCloud Enterprise Linux 21.10U4 (RHEL 系) |
| **CPU/RAM/Disk** | 4 核 / 3.7 GB / 36 GB free |
| **Python** | 3.9.9 (默认仓库无 3.10+) |
| **Docker / Nginx** | 部署前未装 → 已装 nginx 1.21.5 |
| **firewalld** | 部署前未启动 → 已启动 + 开 80/443 |

---

## 二、部署步骤（全部完成）

### Step 1. 上传 + 解压
- `gm-server-bundle.tar.gz` (40.51 MB) → `/root/`，解压到 `/opt/gm-backend`
- `shared.tar.gz` (66 KB) — bundle 漏的共享代码补传
- `backend_models.tar.gz` (1.9 KB) — bundle 漏的 backend/models/schemas.py 补传

### Step 2. Python venv + 93 个包安装
- `python3 -m venv .venv`
- 三批 pip install（清华镜像加速）：
  - **Batch 1** (13 包): fastapi 0.115 / uvicorn / pydantic 2.6 / aiofiles / websockets / httpx / requests / Pillow / aiosqlite / PyJWT / passlib / bcrypt
  - **Batch 2** (5 包): numpy 1.26.4 / scipy / sklearn / pandas / matplotlib
  - **Batch 3** (6+ 包): torch 2.2.0+cpu / torchaudio / torchvision / librosa / soundfile / timm / pytest / pytest-asyncio
  - **后补**: eval_type_backport (FastAPI/Pydantic 解 PEP 604 union 必需)
- 总计：**93 个包，~470 MB**

### Step 3. Python 3.9 兼容性 patch（5 处）

| 不兼容点 | 文件数 | 修复方式 |
|---|---|---|
| `requests==2.33.1` 要求 ≥3.10 | 1 (requirements.txt) | 降级到 2.32.5 |
| `httpx==0.28.1` 要求 ≥3.10 | 1 | 降级到 0.27.2 |
| `Pillow==12.2.0` 要求 ≥3.10 | 1 | 降级到 11.3.0 |
| `from datetime import UTC` (3.11+) | 8 | shim: `from datetime import timezone; UTC = timezone.utc` |
| PEP 604 `X \| Y` 类型注解 | 4 | `from __future__ import annotations` + `pip install eval_type_backport` |

详细 patch 列表见 `@f:/Gorsachius magnificus/species_monitoring_platform/deploy/patch_py39_v2.sh`

### Step 4. .env / 用户 / systemd
- 创建 `gm-backend` 系统用户（uid=987, nologin）
- `chown -R gm-backend:gm-backend /opt/gm-backend`
- `mkdir /var/log/gm-backend` + chown
- 写 `.env`（CORS_ORIGINS 含 36.139.152.185 + capacitor://localhost + http://localhost）
- `cp gm-backend.service /etc/systemd/system/`
- `systemctl enable --now gm-backend`

### Step 5. 关键 bug 修复 — start_linux.sh UTF-8 BOM
- systemd 持续 `status=203/EXEC`（找不到解释器）
- 根因：`start_linux.sh` 首字节是 `\xEF\xBB\xBF`（UTF-8 BOM），让内核看不到 shebang
- 修复：`sed -i '1s/^\xEF\xBB\xBF//' start_linux.sh`
- 同时清理孤儿 uvicorn 进程（之前测试启动留下）

### Step 6. Nginx + 自签证书 + 反代
- `yum install -y nginx openssl`
- 自签证书（CN=36.139.152.185, SAN IP, 825 天有效）
- `/etc/nginx/conf.d/gm-backend.conf`:
  - 80 → 301 redirect → 443
  - 443 SSL (TLS 1.2/1.3) → reverse proxy `127.0.0.1:8000`
  - WebSocket upgrade headers
  - `client_max_body_size 50M`
- `systemctl enable --now nginx`

### Step 7. firewalld 启动 + 开 80/443
- `systemctl enable --now firewalld`
- `firewall-cmd --permanent --add-port={80,443}/tcp`

---

## 三、当前服务状态

| 服务 | PID | 监听 | 状态 |
|---|---|---|---|
| **gm-backend (uvicorn)** | 108218 | 0.0.0.0:8000 | active running |
| **nginx (master)** | 109010 | 0.0.0.0:80, 0.0.0.0:443 | active running |
| **firewalld** | (system) | — | running, 80+443 open |

模型加载日志（节选）：
```
[INFO] Loading v3 student model (SE-ResNet)
[INFO] Loaded model: v4-student, 217 species, val_acc=0.6168
[INFO] Species database loaded: 1356 species
[INFO] Embedding engine initialized
[INFO] Real-time processor initialized (dual_channel=False)
[INFO] Platform ready (device=cpu)
INFO:     Uvicorn running on http://0.0.0.0:8000
```

本地探测 https://127.0.0.1/api/health 返回完整 health JSON（status=ok）。

---

## 四、连通性测试

| 路径 | 端口 | 结果 |
|---|---|---|
| **云 host 内部** localhost → 8000 (uvicorn) | 8000 | ✅ 200 OK |
| **云 host 内部** localhost → 443 (nginx → 8000) | 443 | ✅ 200 OK |
| **本地 Windows** → ECS 36.139.152.185:22 (SSH baseline) | 22 | ✅ 可达 |
| **本地 Windows** → ECS 36.139.152.185:80 | 80 | ❌ TCP timeout |
| **本地 Windows** → ECS 36.139.152.185:443 | 443 | ❌ TCP timeout |
| **本地 Windows** → ECS 36.139.152.185:8000 | 8000 | ❌ TCP timeout |

**结论**: 所有从外网到 80/443 的 TCP 包在 ECS 网卡前就被丢弃，host firewalld 之外还有一层云厂商的安全组(Security Group)在拦截。

---

## 五、~~云 ECS 安全组~~ — 已用 Cloudflare Tunnel 绕过

由于云厂商的安全组只放了 22，且用户选择不动云控制台，改用 **Cloudflare Quick Tunnel** 反向连接 Cloudflare 边缘网络，从外网获得一个 `https://*.trycloudflare.com` 公网 URL。详见第九节。

如果未来想关掉 tunnel 直接用 IP 暴露，需在云控制台开安全组：

| 类型 | 协议 | 端口 | 源 |
|---|---|---|---|
| 自定义 TCP | TCP | 80 | 0.0.0.0/0 |
| 自定义 TCP | TCP | 443 | 0.0.0.0/0 |

---

## 六、验证命令（走 Cloudflare Tunnel 路径）

```powershell
# 应返回完整 health JSON (status: ok)
curl https://ethnic-legitimate-bride-limits.trycloudflare.com/api/health
```

```bash
# 从远程主机查当前 tunnel URL
ssh root@36.139.152.185 'cat /opt/gm-backend/.tunnel.url'
```

---

## 七、回滚命令（如需停服）

```bash
ssh root@36.139.152.185 << 'EOF'
systemctl stop gm-backend nginx
systemctl disable gm-backend nginx
EOF
```

---

## 八、相关文件

- 部署脚本：`@f:/Gorsachius magnificus/species_monitoring_platform/deploy/`
  - `batch2.sh` `batch3.sh` `install.sh` `verify.sh`
  - `patch_py39_v2.sh` `finalize.sh` `fix1.sh` `fix2.sh`
  - `nginx_setup.sh` `cloudflared_setup.sh` `cloudflared_persist.sh`
- cloudflared 二进制（本地）：`@f:/Gorsachius magnificus/species_monitoring_platform/deploy/cloudflared` (39.6 MB linux-amd64)
- 远程日志：`/var/log/gm-deploy/*.log`, `/var/log/gm-backend/{stdout,stderr,cloudflared}.log`
- backend bundle：`/opt/gm-backend/`
- nginx conf：`/etc/nginx/conf.d/gm-backend.conf`
- 自签证：`/etc/nginx/ssl/gm.{crt,key}` (825 天有效)
- tunnel URL marker：`/opt/gm-backend/.tunnel.url`
- systemd units：`/etc/systemd/system/{gm-backend,cloudflared-tunnel,nginx}.service`

---

## 九、✅ Cloudflare Tunnel 上线状态

| 项 | 值 |
|---|---|
| **当前公网 URL** | `https://ethnic-legitimate-bride-limits.trycloudflare.com` |
| **systemd service** | `cloudflared-tunnel.service` (active running, Main PID 112085) |
| **外网验证** | 本地 Windows 达标：status 200, elapsed 1.96s, CF-Ray NRT (Cloudflare 东京边缘节点) |
| **TLS** | Cloudflare 边缘下发合法证书（不是自签），APK 不需 trust self-signed 配置 |
| **限制** | Quick Tunnel URL 是 **ephemeral** —— 重启 cloudflared 服务或机器后 URL 会变 |
| **路径** | Cloudflare Edge → cloudflared 进程 (outbound QUIC) → nginx?  → 不走 nginx，直连 127.0.0.1:8000 (uvicorn) |

### 重启后查新 URL

```bash
ssh root@36.139.152.185 'cat /opt/gm-backend/.tunnel.url'
# 或
ssh root@36.139.152.185 'grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /var/log/gm-backend/cloudflared.log | tail -1'
```

### Tunnel 服务控制

```bash
systemctl status cloudflared-tunnel    # 看状态
systemctl restart cloudflared-tunnel   # 重启（URL 会变）
systemctl stop cloudflared-tunnel      # 停服
systemctl disable cloudflared-tunnel   # 停开机自启
```

---

## 十、APK_R4 重 build 指南（含 backend URL）

如果需要 APK 走**在线后端模式**（而不是 hybrid local），要在重 build 前设 `VITE_API_BASE_URL`。

### 方案 A：临时 quick tunnel URL（机器不重启就不变）

```powershell
cd "F:\Gorsachius magnificus\species_monitoring_platform\frontend"
@"
VITE_API_BASE_URL=https://ethnic-legitimate-bride-limits.trycloudflare.com
"@ | Out-File -Encoding utf8 -NoNewline .env.production.local

npm run build
npx cap sync android
cd android
.\gradlew.bat assembleDebug
# APK 在：android/app/build/outputs/apk/debug/app-debug.apk
```

设了 `VITE_API_BASE_URL` 之后 `IS_HYBRID_LOCAL_MODE` 在 build time 被评为 `false`——
App 启动会调 axios、refreshHealth 走真 /api/health、sidebar/topbar 显示后端状态。

### 方案 B：使用 Cloudflare named tunnel + 自定义域名（URL 永久不变）

需要你提供：
1. 一个域名（如 `gm-api.example.com`）
2. 该域名的 Cloudflare 账号管理权限（API token）

流程：
1. 远程跑：`cloudflared tunnel login` → 浏览器授权→写入 cert.pem
2. `cloudflared tunnel create gm-backend` → 得到 tunnel UUID
3. `cloudflared tunnel route dns gm-backend gm-api.example.com`
4. 写 `~/.cloudflared/config.yml`：
   ```yaml
   tunnel: <UUID>
   credentials-file: /root/.cloudflared/<UUID>.json
   ingress:
     - hostname: gm-api.example.com
       service: http://127.0.0.1:8000
     - service: http_status:404
   ```
5. systemd unit ExecStart 改为：`cloudflared tunnel run gm-backend`
6. APK 用 `VITE_API_BASE_URL=https://gm-api.example.com`——从leader不变

需要该路径告诉我照该域名。

### 方案 C：APK 继续走 hybrid local（不动 R3 APK）

R3 APK (`bugABCD-fix.apk`) 的 `VITE_API_BASE_URL=''`，启动后 `IS_HYBRID_LOCAL_MODE=true`，
App 完全走本地 SQLite + Capacitor，不调 backend。
后端部署只是为了未来需要云同步 / 多人协作 / 多设备合并 时备用。
你仍然仅用 R3 APK 跑野外调查完全 OK。
