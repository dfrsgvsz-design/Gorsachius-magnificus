# Production deploy runbook · swdyx.eu.cc

**Date**: 2026-06-10
**Ticket**: #A P0 W2 · 生产部署走通
**Author**: 后端 & 架构负责人（工程师 A）
**Audience**: 工程师 C（部署 / DevOps）+ 运维

PM 已经把生产域名拍下：`swdyx.eu.cc`. 本文是从一台新 VM 把两个平台跑成
HTTPS 的最小步骤。所有镜像、compose、nginx-proxy、acme-companion 都已
就绪，操作员只需要填几个变量。

## 1. 域名分配

| 平台 | 域名 | 用途 |
|---|---|---|
| species_monitoring_platform | `swdyx.eu.cc` | 主平台（生物多样性野外调查） |
| acoustic_platform | `acoustic.swdyx.eu.cc` | 次平台（声景生态指数） |

需要在 DNS 服务商加 A 记录：

```
A    swdyx.eu.cc           → <主机公网 IPv4>
A    acoustic.swdyx.eu.cc  → <主机公网 IPv4>
```

或者用 wildcard 覆盖：

```
A    swdyx.eu.cc           → <主机公网 IPv4>
A    *.swdyx.eu.cc         → <主机公网 IPv4>
```

> wildcard 方案以后加新子域名（staging / api / docs 等）零成本。

## 2. 防火墙

主机入站需要开放：

| 端口 | 协议 | 用途 |
|---|---|---|
| 80 | TCP | Let's Encrypt HTTP-01 挑战 + 自动 HTTP→HTTPS 跳转 |
| 443 | TCP | 生产 HTTPS |
| 22 | TCP | 运维 SSH |

## 3. 一次性部署（每个平台一遍）

### species_monitoring_platform

```bash
cd species_monitoring_platform

# 第一次：从模板拉 .env
cp .env.example .env

# 编辑 .env，至少填这三个
#   BIRD_API_KEY=<生成一个 40+ 字符的随机密钥>
#   ACME_LETSENCRYPT_EMAIL=ops@example.org
#   APP_DOMAIN=swdyx.eu.cc            # 已是默认值
nano .env

# 起服务（base + prod overlay）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 看 nginx-proxy 是否自动发现 vhost
docker logs nginx-proxy --tail 50

# 看 acme-companion 是否在签证书
docker logs nginx-proxy-acme --tail 50

# 等 60-90 秒，证书签好后直接打：
curl -I https://swdyx.eu.cc/api/health/liveness
# 应该返回 200 OK，证书链由 Let's Encrypt 签发
```

### acoustic_platform

```bash
cd ../acoustic_platform
cp .env.example .env
# 填同样的三个 + APP_PORT=8001（避免与 species 冲突）
nano .env

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

curl -I https://acoustic.swdyx.eu.cc/api/health/liveness
```

> **注意**：两个平台共享同一台 nginx-proxy（一台主机只能有一份）。所以
> 第二次 `up -d` 时 docker 会复用 species 平台的 nginx-proxy 容器，acme-
> companion 会自动为 `acoustic.swdyx.eu.cc` 申请第二个证书。

## 4. 验证

### 4.1 健康 endpoint

```bash
# 永远 200，rate-limit 免除
curl -fsS https://swdyx.eu.cc/api/health/liveness
curl -fsS https://acoustic.swdyx.eu.cc/api/health/liveness

# 紧凑就绪检查
curl -fsS https://swdyx.eu.cc/api/health/readiness | jq .
# {
#   "status": "ready",
#   "ready": true,
#   "deployment_ready": true,
#   "runtime_state": "ready",
#   ...
# }

# 完整健康负载（生产端必须 deployment_ready=true、readiness.mode="production"）
curl -fsS https://swdyx.eu.cc/api/health | jq '.readiness, .runtime_paths'
```

### 4.2 反 demo 模式断言

```bash
# 取 /api/health 然后用 jq 检查 4 个 externalization 旗标
curl -fsS https://swdyx.eu.cc/api/health \
  | jq -e '
      .deployment_ready == true and
      .readiness.mode == "production" and
      .readiness.blocking_codes == [] and
      .runtime_paths.mutable_runtime_externalized == true
    ' && echo "PRODUCTION READY" || echo "DEMO MODE — fix env"
```

### 4.3 24h 99% 200 SLO 验收

放一个 cron 跑：

```bash
# 每分钟拉一次 /api/health，写入 nginx access log + 应用 stdout
# 24h 后看：
docker logs --since 24h app | grep "GET /api/health" | awk '{print $9}' | sort | uniq -c
# 应该看到 ≥ 1425/1440 次返回 200（99% SLO）
```

如果 SLO 没达到，看 `/api/health` 的 `warnings` 和 `survey_readiness.go_live_blockers`。

## 5. 滚动

```bash
# 拉新代码
git pull

# 重建并平滑替换（用 stop_grace_period 给 gunicorn 30s 优雅退出）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# nginx-proxy + acme-companion 容器不重启，证书状态不变
```

## 6. 应急回滚（数据层）

> 区分两个轴：**数据回滚**（本节，恢复 survey_store.db 到某个快照）和
> **schema 回滚**（`python scripts/db_migrate.py downgrade -1`，见
> `docs/release_b/2026-06-11_alembic_integration.md`）。出事先判断是哪一类。

### 6.1 首选 · 脚本化快照/恢复（commit a0da1fa 起可用）

`scripts/snapshot_survey_store.ps1` + `scripts/restore_survey_store.ps1`，
在装有 PowerShell（Windows 或 Linux `pwsh`）+ Python 3 的机器上运行，
数据目录用 `-DataDir` 或 `SURVEY_DATA_DIR` 指定。

```powershell
# 例行 / 发版前：打快照（应用不用停 — 走 sqlite3 backup API，WAL 安全；
# 严禁直接 cp/copy 一个正在写的 WAL 库，会拷出坏文件）
.\scripts\snapshot_survey_store.ps1 -Tag before_v0_9 -Keep 10

# 出事时：停应用 → 恢复最新快照 → 起应用 → 烟测
docker compose stop app
.\scripts\restore_survey_store.ps1 -Latest    # 交互确认；自动化加 -Force
docker compose start app
curl https://swdyx.eu.cc/api/health/readiness
```

restore 自带五道安全闸：坏备份拒绝恢复 / EXCLUSIVE 锁证明应用已停 /
自动留 `pre_restore_<ts>.db` 副本（恢复本身可反悔）/ 清理残留
`-wal`/`-shm` / 恢复后 integrity_check + 打印 alembic 版本。快照落在
`<DataDir>/backups/`，恢复后若快照早于当前 schema，按提示跑
`python scripts/db_migrate.py upgrade head`。

### 6.2 兜底 · 纯 Linux 手工路径（主机无 pwsh 时）

```bash
# 备份（必须先停应用 — tar 直拷不具备 WAL 一致性保障）
docker compose stop app
tar -czf "/var/backups/survey_store_$(date +%Y%m%d_%H%M%S).tar.gz" \
  deploy/pilot/volumes/backend-data/survey_store/
docker compose start app

# 回滚到前一次备份
docker compose stop app
rm -rf deploy/pilot/volumes/backend-data/survey_store/
tar -xzf /var/backups/survey_store_<timestamp>.tar.gz -C ./
docker compose start app

# 验证
curl https://swdyx.eu.cc/api/health/readiness
```

## 7. Let's Encrypt 速率限制提醒

- LE 对同一个 hostname **每周** 最多签 50 个证书；调试时如果反复重建容器
  导致重复申请，会被锁 7 天。
- 调试期间务必先用 staging endpoint：
  ```bash
  # .env
  ACME_CA_URI=https://acme-staging-v02.api.letsencrypt.org/directory
  ```
  staging 证书不被浏览器信任但能验证流程；调通后改回 prod URI 并删除
  `certs` volume 让 acme-companion 重新申请正式证书。

## 8. Sentry / GlitchTip（可选）

`sentry-sdk==2.18.0` 已经在 requirements 里，sentry init 在两个平台的
main.py 都加好了。只需要在 .env 里塞 DSN：

```
SENTRY_DSN=https://<key>@<host>/<project_id>
DEPLOY_ENV=production
```

重启容器后 `/api/health` 日志会出现 `Sentry error monitoring enabled`。
如果团队选 GlitchTip，把 DSN 换成 self-hosted GlitchTip 实例的 URL
即可，sentry-sdk 兼容。

## 9. 已知阻塞

| 项 | 状态 | DRI |
|---|---|---|
| DNS A 记录上手 | 等运维 / 域名注册商 | C + PM |
| Let's Encrypt 邮箱 | 等填 ACME_LETSENCRYPT_EMAIL | PM |
| 防火墙 80/443 开 | 等运维 | C |
| Sentry / GlitchTip DSN | 等 PM 选 SaaS or 自托管 | PM |
| ICP 备案 | swdyx.eu.cc 在 `.eu.cc` 域不需要 ICP | — |

## 10. 验收清单（C 跑完后回字段）

- [ ] `dig swdyx.eu.cc` 返回主机 IP
- [ ] `dig acoustic.swdyx.eu.cc` 返回主机 IP
- [ ] `curl -I https://swdyx.eu.cc/api/health/liveness` 返回 200，cert 验证通过
- [ ] `curl -I https://acoustic.swdyx.eu.cc/api/health/liveness` 同上
- [ ] `curl -s https://swdyx.eu.cc/api/health | jq '.deployment_ready'` 为 `true`
- [ ] `curl -s https://swdyx.eu.cc/api/health | jq '.readiness.mode'` 为 `"production"`
- [ ] `curl -s https://acoustic.swdyx.eu.cc/api/health | jq '.deployment_ready'` 为 `true`
- [ ] 起 cron 跑 24h，统计 200 占比 ≥ 99%
- [ ] `release_gate.ps1` 整套 PASS（在 CI 上跑，不是这台主机）
