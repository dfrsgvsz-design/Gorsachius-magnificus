# 回滚 SOP v1.0（species_monitoring_platform + acoustic_platform）

> **版本**：v1.0（2026-06-10，工单 #C P0 W3）
> **DRI**：工程师 C（QA & DevOps）
> **生效范围**：双 App 前端 + 后端 + 数据迁移
> **触发条件**：内测 / 灰度 / 生产任何环境的 P0 缺陷、严重崩溃率上升（> 1%）、数据完整性事件、合规问题（隐私 / 权限滥用）。

## 0) 决策与责任

| 角色 | 决策权 |
|---|---|
| 工程师 C | 触发回滚提案、组织演练、出具事后报告 |
| 项目 PM | **唯一回滚批准人**；批准前需在工程师 A（healthcheck）+ B（前端构件）签字确认数据可回滚 |
| 工程师 A | 后端 / API 回滚执行、healthcheck 监测、数据迁移逆向脚本 |
| 工程师 B | 前端 / Web build 回滚执行、Play Console / 内测分发回滚 |

## 1) 回滚单位与命名约定

| 资产 | 当前位置 | N-1 锚点 |
|---|---|---|
| 前端 web build | `species_monitoring_platform/frontend/dist/` 由 `npm run build` 产出 | git tag `v<major>.<minor>.<patch>-web` 标记的构建产物（CI 产物归档） |
| 后端 docker image | `biodiversity-field-survey:release` | image tag `biodiversity-field-survey:<git-sha>` 或 `:<version>` |
| 签名 AAB | `frontend/android/app/build/outputs/bundle/release/app-release.aab` | Play Console 上"已撤回"的最近版本（versionCode = current - 1） |
| 数据库 schema | `species_monitoring_platform/backend/data/*.sqlite` + Alembic migration（如启用） | 上一次 migration 的 down-revision；如未启用 Alembic 则需手动 SQL 逆向脚本 |
| 配置 | `.env.production` + Play Console 远端配置 | git 上的上一个稳定提交对应的 `.env.production.example` 差异 |

## 2) 回滚 SOP（六步法）

### Step 0 · 前置 30 分钟内必须完成

- [ ] PM 已签字批准（书面或 Linear 工单留痕）
- [ ] 用户告知文案已准备：内测群发 + Play Console 备注
- [ ] 录屏工具就位（OBS / 系统录屏），全程录像 SOP 执行过程
- [ ] 回滚目标版本（N-1）已确认：在以下表格里填值

| 项 | N（要回滚的）| N-1（目标）|
|---|---|---|
| 前端 git tag | `<填写>` | `<填写>` |
| 后端 git tag | `<填写>` | `<填写>` |
| AAB versionCode | `<填写>` | `<填写>` |
| 数据库 migration head | `<填写>` | `<填写>` |
| 触发原因 | `<填写>` | — |

### Step 1 · 通告

- [ ] 内测群发"15 分钟内回滚"预通告
- [ ] Play Console 内测轨道暂停接收新用户

### Step 2 · 前端回滚

```powershell
cd "f:\Gorsachius magnificus\species_monitoring_platform\frontend"
git checkout v<N-1>-web        # N-1 tag
npm ci                         # 锁定依赖
npm run build                  # 重建产物
npx cap sync android           # 同步原生工程
```

验收：`frontend/dist/index.html` 哈希 = git tag 记录的哈希。

### Step 3 · 后端回滚

```powershell
cd "f:\Gorsachius magnificus\species_monitoring_platform"
docker compose down            # 当前服务停止
git checkout v<N-1>            # N-1 tag
docker compose build           # 重建 image
docker compose up -d           # 启动
```

验收：`curl -fsS http://127.0.0.1:8000/api/health` 返回 200，runtime_state = "ready"。

### Step 4 · 数据迁移逆向（如适用）

如果 N→N+1 引入了不兼容 schema 变更：

```powershell
cd "f:\Gorsachius magnificus\species_monitoring_platform\backend"
# 如启用 Alembic：
python -m alembic downgrade <N-1-revision>
# 如未启用：手动执行已预备的逆向 SQL 脚本
python scripts/db_downgrade.py --to <N-1-revision>
```

验收：抽样 10 条最近观测记录，逐字段对照"回滚前快照"无字段丢失。

### Step 5 · 移动端回滚

- [ ] 在 Play Console **Internal testing → Release** → "Promote previous release" 选择 versionCode = N-1 的发布版本
- [ ] 等待 Google 处理（通常 5-15 分钟）
- [ ] 让一名测试人员从 Play 拉新装包，确认 AAB 已回到 N-1

### Step 6 · 验收

按 `submission/04_release_execution_runbook.md` 第 5 节冒烟集（5 项）逐项过：

- [ ] 冷启动进入首页无白屏
- [ ] 拍照功能正常
- [ ] 录音功能正常
- [ ] 定位打点正常
- [ ] SQLite 本地写读正常
- [ ] 离线提交 → 重连同步全链路通

任何一项 fail → 立即触发"回滚的回滚"（恢复到 N），并把本次 SOP 失败的细节写入 §4 的演练记录。

## 3) 验收成功后必须做的事

- [ ] 内测群发"回滚已完成 + 复盘 24h 内出"
- [ ] 在 PM Linear 工单评论里贴录屏链接 + 本 SOP 完成时间戳
- [ ] **24 小时内**在 `submission/governance/postmortem_<yyyy-mm-dd>.md` 写复盘报告（"为什么需要回滚"、"如果有 SOP 的薄弱环节、是什么"、"下一版要避免的事"）

## 4) 演练记录（每次演练 / 真实回滚都要追加一条）

| 日期 | 类型（演练 / 真实）| 触发原因 | N → N-1 版本 | SOP 总耗时 | 失败步骤（如有）| 录屏链接 | 操作人 |
|---|---|---|---|---|---|---|---|
| `<待填写>` | 演练 | 工单 #C P0 W3 必须演练 | `<填写>` | `<填写>` | 无 | `<待填写>` | C |
| | | | | | | | |
| | | | | | | | |

## 5) 已知的"不可回滚"操作（红线）

下列操作执行后**无法回滚**，必须在执行前与 PM 双签：

1. **Play App Signing 启用**（一次性单向；见 `submission/06_packaging_signing_runbook.md` §2.1）
2. **删除生产数据库主表 / DROP TABLE / TRUNCATE 不带备份**
3. **撤销已发布到 Play Store 正式轨道（非内测）的版本** —— 撤销不可恢复
4. **删除 Play Console 应用 / 注销 Google Play Console 主体账号**
5. **删除 keystore 主密钥（启用 Play App Signing 之前）** —— 上架主体即时丢失

红线操作的双签流程：PM + 工程师 C 在 PR 评论里各打一次 "approved-irreversible"，且 PR 标题必须含 `[irreversible]` 前缀。

## 6) 回滚事故的事后评级

| 等级 | 触发 | 应对 |
|---|---|---|
| **L1** | 6 个月内首次回滚 + SOP 一次过 | 例行复盘，无须升级 |
| **L2** | 6 个月内第 2 次回滚 / 或 SOP 任一步 fail | 工程师 C + PM 召集全组复盘，调整 quality_gate / release_gate 阈值 |
| **L3** | 6 个月内第 3 次回滚 / 或 SOP 总耗时 > 60 分钟 / 或 §5 红线被触碰 | **暂停一切发布**，先把 release pipeline 重新设计再继续 |

## 7) 测试 SOP 自身的方法

本 SOP 必须在每次 minor 版本（X.Y.0）发布前**演练一次**，验证以下 5 个不变量：

1. SOP 总耗时 ≤ 60 分钟（v1.0 baseline；下版可压缩）。
2. Step 2 / Step 3 / Step 5 任一独立执行 ≤ 15 分钟。
3. Step 6 的 5 项冒烟无任何 fail。
4. 录屏完整、可观看，无敏感口令出镜。
5. 复盘报告 24 h 内产出。

任何一项不满足都视为本 SOP 失败，触发"SOP 修订 PR" 由工程师 C 提交。

## 8) 关联文档

- `submission/04_release_execution_runbook.md` — 发布执行 runbook（正向流程，本 SOP 是逆向）
- `submission/06_packaging_signing_runbook.md` — 签名出包（涉及 §1.1 Vault + §2.1 Play App Signing）
- `submission/05_go_live_decision_report.md` — 发布决策报告（"是否值得回滚"的判断框架）
- `QUALITY_GATE_REPORT.md` — 当前质量门禁状态
- `.github/workflows/release_gate.yml` — CI 端的发布闸门
- `quality_gate.ps1` / `scripts/release_gate.ps1` — 本地闸门脚本

## 9) 修订历史

- 2026-06-10 v1.0 工程师 C 首版（工单 #C P0 W3）
