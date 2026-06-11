# `species_monitoring_platform/deploy/staging/` 限照报废决定

**Date**: 2026-06-10
**Ticket**: #A + #C 协同
**Author**: 后端 & 架构负责人（工程师 A）
**Reviewers**: 工程师 C（部署）+ PM
**Status**: 已执行（76 files / 44.7 MB on disk · 包含 best_model.pth 约 44 MB
checkpoint 副本）

## 背景

`species_monitoring_platform/deploy/staging/backend/` 是 v6 时代的代码快照，
用作"出问题就回滚到这份快照"的应急后路。Batch A → B → C 期间多次被点名：

- **Batch A**：扫 422/503 时这份快照与 main 接口已 drift（survey routes 多
  出 4 处 503 raise）
- **Batch B**：调用方迁移 `from shared.backend.*` 时只动 main，staging 限照保
  持旧 import 形式（已与 main 分叉）
- **Batch C**：survey_store / detection_store / taxonomy_catalog 三个真双胞胎
  迁 shared 后，staging 限照里仍然是 v6 的 SQLite schema 旧版

主干代码现在跟 shared/backend/* 强绑定（PYTHONPATH 包含 repo root + 平台 backend；
shared 模块负责持久化、taxonomy、模型加载），staging 限照里的 main.py 仍然按
"扁平 backend 单一目录" 假设组织 import 路径，**它已经不能 `python main.py`
启动**——既不能被 Dockerfile build 拿去做镜像（Dockerfile 现在用 repo root
context），也不能被 release_gate 拿去回归（release_gate.ps1 + release_gate.yml
都只引用 species/backend 与 acoustic/backend）。

继续保留它的唯一理由是"应急回滚"。但应急回滚的真正落点早就不在限照里：

| 应急路径 | 真正落点 | 限照是否能服务这条路径 |
|---|---|---|
| 数据恢复 | `<DATA_DIR>/survey_store/*.sqlite3` tar.gz 备份 + restore | ❌ 不参与，限照只是代码 |
| 代码回滚 | `git revert <bad-sha>` 或 `git checkout <good-tag>` | ❌ git 已足够，限照只增加 fork 不一致 |
| 容器回滚 | `docker compose up -d --build` 后回退到上一镜像 tag | ❌ 限照不构镜像 |
| 备份模型 | `<CHECKPOINTS_DIR>/best_model.pth` 直接拷一份 | ❌ 限照里的 best_model.pth 已是 v6 旧版 |

## 决定

**裁减**整个 `species_monitoring_platform/deploy/staging/` 目录，包括：

```
species_monitoring_platform/deploy/staging/
  ├── backend/                  # 76 个 py 文件，全部 dead code
  ├── README_DEPLOY.md         # 过期 runbook
  ├── start_windows.ps1        # 过期启动脚本（不调用 gunicorn）
  ├── start_linux.sh           # 过期启动脚本
  ├── env.production.template  # 早于 swdyx.eu.cc 决定的旧模板
  └── gm-backend.service       # systemd unit 文件，过期
```

**保留**的部分（已经不在这个目录下）：
- `species_monitoring_platform/deploy/pilot/` — 真正的字段试点配置
- `species_monitoring_platform/Dockerfile` + `docker-compose.yml` +
  `docker-compose.prod.yml` — 已替代 staging 限照里的所有部署文件

## 替代清单

| 限照里的文件 | 现在用什么替代 |
|---|---|
| `staging/backend/main.py` | `species_monitoring_platform/backend/main.py`（已 Batch A 现代化） |
| `staging/backend/runtime_paths.py` | `species_monitoring_platform/backend/runtime_paths.py` + `shared/backend/utils/runtime_paths.py` |
| `staging/backend/survey_store.py` | `shared/backend/stores/survey_store.py` + 平台 shim |
| `staging/backend/taxonomy_catalog.py` | `shared/backend/stores/taxonomy_catalog.py` + 平台 shim |
| `staging/start_windows.ps1` | `scripts/release_gate.ps1` + `docker compose up` |
| `staging/start_linux.sh` | `docker compose up`（compose 自带 healthcheck + restart policy） |
| `staging/env.production.template` | `species_monitoring_platform/.env.example`（已含 swdyx.eu.cc + LE 配置） |
| `staging/gm-backend.service` | docker compose 容器化已替代 systemd unit |
| `staging-report.txt`（限照体积报告） | 不再需要——本文记录最终结论 |

## 验证

```
$ tree species_monitoring_platform/deploy/staging
species_monitoring_platform/deploy/staging [error opening dir]

$ python -m pytest species_monitoring_platform/backend/tests/ -q --maxfail=3
... 73 passed ...

$ python -m pytest acoustic_platform/backend/tests/ -q --maxfail=3
... 63 passed ...
```

136/136 测试仍然全过，证明删除 staging 限照不影响主干。

## 回滚路径（如果决定后悔）

```bash
# 限照删除点在 git history 里：
git log --oneline --all -- species_monitoring_platform/deploy/staging/
git checkout <pre-deletion-sha> -- species_monitoring_platform/deploy/staging/
```

## 残留引用清理

以下 docs / reports 仍然提到 `deploy/staging` 路径，需要保留为"历史
记录"而不删除（说明当时 staging 限照存在），但**不要被新人误以为是
活的部署路径**：

- `QUALITY_GATE_REPORT.md` — 历史 quality gate 报告
- `species_monitoring_platform/HYBRID_LOCAL_MULTI_DEVICE_TEST_REPORT.md`
  — 历史多设备测试报告
- `docs/release_b/2026-06-10_422_503_inventory.md` — Batch A 交付文件，已在
  「2.3 Staging snapshot」一节标注限照状态

如果未来需要"应急回滚"能力，**走 git history + Docker image tag** 而非
重新拉一份限照——参考 `docs/release_b/2026-06-10_production_deploy_runbook.md`
§ 6 应急回滚那一节。
