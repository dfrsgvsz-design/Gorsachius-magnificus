# Alembic integration · survey_store · P0 W3

**Date**: 2026-06-11
**Ticket**: #A · P0 W3 · 产品级回滚演练打底
**Author**: 后端 & 架构负责人（工程师 A）
**Scope**: `shared/backend/stores/survey_store.py` only (per Option A拍板)

## 1. 为什么先做 survey_store

我们有 3 个 SQLite 数据库：

| 库 | 是否被 alembic 接管 | 理由 |
|---|---|---|
| `survey_store.db` (12 tables · audit + soft-delete + sync) | ✅ 是 | 运营数据 (PII / 调查记录)·不能丢·必须有 downgrade |
| `taxonomy_catalog.sqlite3` (9 tables) | ❌ 否 | 每次启动从 seed JSON 重生·schema 漂了重 bootstrap 即可 |
| `detections.db` (1 table) | ❌ 否 | 只 append·schema 几乎不变·下个改动再上 |

P0 W3 只做 survey_store。其他两库未来有 schema 分支再上。

## 2. 文件清单

```
shared/backend/stores/
├── migrations/                                   ← alembic 工作目录
│   ├── alembic.ini                              ← 配置 (ASCII only, gbk 安全)
│   ├── env.py                                   ← 多 DB-Aware env, batch ops 开
│   ├── script.py.mako                           ← 新版本模板
│   ├── __init__.py
│   └── versions/
│       ├── __init__.py
│       └── 0001_survey_store_baseline.py       ← 12 tables + 44 indexes
└── migrations_runtime.py                        ← lifespan-time helper
                                                    + stamp-pre-alembic 逻辑

scripts/db_migrate.py                            ← 操作员 CLI

species_monitoring_platform/backend/requirements.txt   ← + alembic==1.13.3 + SQLAlchemy==2.0.36
acoustic_platform/backend/requirements.txt             ← 同上
species_monitoring_platform/backend/tests/test_alembic_migrations.py
acoustic_platform/backend/tests/test_alembic_migrations.py
```

## 3. 三个启动场景的处理

`apply_survey_store_migrations(db_path)` 在 `SurveyStore.__init__` 里跑：

1. **Fresh empty DB**
   - `alembic_version` 不存在 · 12 baseline 表不存在
   - 跑 `alembic upgrade head` → 创建 alembic_version + 全部 baseline DDL
   - DB 现在 at `0001_survey_store_baseline`

2. **Pre-alembic existing DB**（部署在本 PR 之前）
   - `alembic_version` 不存在 · 但 `survey_projects` 存在
   - 先 `alembic stamp 0001_survey_store_baseline`（只插一行 alembic_version, 不跑 DDL）
   - 再 `alembic upgrade head`（已 at head, no-op）
   - **DB 数据完全保留** · 测试已断言这一点
   - 已有运营 sqlite 文件可以直接迁过 PR · 不需要导出再导入

3. **Up-to-date DB**
   - `alembic_version` 存在 · 值 = head
   - `alembic upgrade head` 是 no-op

## 4. 防御层

`SurveyStore.__init__` 调 `apply_survey_store_migrations(...)` 后**仍然**会跑
`self._conn.executescript(self._DDL)` + `self._migrate_schema()`。这是
defense-in-depth：

- 如果 alembic 没装上（旧 wheel · 旧镜像）·helper 返回 None + 写一行 WARNING
  · DDL fallback 跑，schema 仍创建
- 如果 alembic 本身报错（损坏 alembic_version row 等罕见情况）·exception
  被吞 + 写 logger.exception · DDL fallback 跑，启动不被破坏

代价：少量重复的 `CREATE IF NOT EXISTS` execute · 可忽略。

收益：alembic 引入不可能让生产 boot 失败。

## 5. 操作员 CLI

```bash
# 查当前 DB 在哪个 revision
python scripts/db_migrate.py current

# 查全部 revision 历史
python scripts/db_migrate.py history

# 升到 head（启动时已自动跑，手动用于离线/紧急情况）
python scripts/db_migrate.py upgrade head

# 升一档
python scripts/db_migrate.py upgrade +1

# 降一档
python scripts/db_migrate.py downgrade -1

# 全部回到空（仅 alembic_version 留）
python scripts/db_migrate.py downgrade base

# 把数据库标记为已经在 head（不跑 DDL）—— pre-alembic DB 第一次迁进时用
python scripts/db_migrate.py stamp head

# 创建新 revision 模板
python scripts/db_migrate.py revision -m "add survey_geofence column"

# 指定不同的 DB（默认从 SURVEY_DATA_DIR / BIRD_PLATFORM_DATA_DIR 推）
python scripts/db_migrate.py --db /backup/survey_store_pre_migrate.db current
```

## 6. 写新 migration 的范式

```bash
python scripts/db_migrate.py revision -m "add survey_geofence column"
# 生成 shared/backend/stores/migrations/versions/0002_xxxx.py
# 手工填 upgrade() 和 downgrade()
```

在 `upgrade()` / `downgrade()` 里：

```python
def upgrade() -> None:
    # SQLite 受限 ALTER · 用 batch_alter_table 包起来
    with op.batch_alter_table("survey_sites") as batch:
        batch.add_column(sa.Column("geofence_radius_m", sa.Integer(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table("survey_sites") as batch:
        batch.drop_column("geofence_radius_m")
```

对纯 SQL：`op.execute("CREATE INDEX ...")` 也行。

## 7. P0 W3 产品级回滚演练（运营拿走跑）

```bash
# 1) 备份当前数据库（必须先做）
sudo cp /app/data/survey_store/survey_store.db /var/backups/survey_store_$(date +%Y%m%d_%H%M%S).db

# 2) 看当前在哪个 revision
docker compose exec app python /app/scripts/db_migrate.py current
# 期望：0001_survey_store_baseline (head)

# 3) 模拟 schema 出问题后回滚（W3 演练）
docker compose exec app python /app/scripts/db_migrate.py downgrade -1
# 期望：alembic 一阶 downgrade·应用一定要先停（避免 active 写入丢）

# 4) 回升到 head
docker compose exec app python /app/scripts/db_migrate.py upgrade head

# 5) 用 smoke probe 确认 API 仍服务
scripts/smoke_production_health.sh
```

## 8. 验收

```
species 后端 · 82 passed (78 + 4 alembic)
acoustic 后端 · 72 passed (68 + 4 alembic)
合计 154/154

Alembic 集成 4 个测试：
  ✓ test_fresh_db_upgrade_head_creates_baseline_tables
  ✓ test_pre_alembic_db_is_stamped_without_ddl_replay
  ✓ test_upgrade_downgrade_roundtrip
  ✓ test_survey_store_init_invokes_migrations

CLI 烟测：
  ✓ upgrade head → 14 tables (12 baseline + alembic_version + sqlite_sequence)
  ✓ current → 0001_survey_store_baseline (head)
  ✓ downgrade base → 仅 alembic_version + sqlite_sequence 残留
  ✓ upgrade head 再次 → 14 tables 恢复
```

## 9. 下一个 PR 的 hook 点

- **survey_store 新 schema 改动**：必须同时写 alembic revision · 不要再扩展
  `_init_schema._DDL` · CI 应该加一条 lint 拦截
- **taxonomy_catalog 上 alembic**：等 schema 有产品级变动 (索引重建 / 列重命名)
  时再走一遍 Option A 流程
- **detection_store 上 alembic**：只 append, 没必要

## 10. 已知坑

- **alembic.ini 不能含非 ASCII**：Windows configparser 默认走 gbk · 命中
  em dash / 中文会 UnicodeDecodeError。这文件保持纯 ASCII
- **batch_alter_table 必须用**：SQLite 不支持 DROP COLUMN / MODIFY COLUMN·
  alembic 用临时表 + COPY 实现·开 `render_as_batch=True` (env.py 已设)
- **Let's Encrypt rate-limit 类似的坑**：不要在 CI 里反复 stamp/upgrade 不同
  数据库·会产生大量 alembic_version 行污染。test_alembic_migrations.py 用
  tempdir 隔离
