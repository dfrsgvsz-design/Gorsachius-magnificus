# Algo-D 决策记录：补足"8 大类群"——新增 `aquatic_vertebrates`（鱼类）与 `fungi`（菌菇）

- **工单：** Algo-D 后续工单（由 P0 W2 taxonomy 契约文档"缺口 3"派生）
- **决策日期：** 2026-06-10
- **决策人：** （待签字）sponsor / 算法 D
- **生效版本：** `taxonomy_release_id = taxonomy_seed_release_2026_06_10`，`survey_protocols registry_version = 2026-06-10`

---

## 1. 背景

`docs/taxonomy_api_contract.md` v1.0 §6 列出契约缺口 3：

> 工单 P1 W2 要求覆盖 8 大类群（鸟/哺乳/两栖/爬行/鱼类/昆虫/植物/菌菇），当前 `program` 枚举只有 3 个（terrestrial_vertebrates / plants / insects），覆盖 6 个类群。**鱼类、菌菇缺失**。

本工单把这两个 program 补齐，让 P1 W2 的"taxonomy_coverage_report.md"有可比较的基准。

---

## 2. 命名采决

| 维度 | 候选 | 选定 | 理由 |
|---|---|---|---|
| 鱼类 program key | `fish` / `aquatic_vertebrates` / `freshwater_fish` | **`aquatic_vertebrates`** | 与现有 `terrestrial_vertebrates` 对称；为后续把两栖鱼以外的水生类（如水生哺乳鲸豚）扩展留路 |
| 鱼类 submodules | `freshwater_fish`, `marine_fish` | **`freshwater_fish`, `estuarine_fish`, `marine_fish`** | 中国大陆华南 / 台湾沿海两类型生境都覆盖；分得太细 W3 再说 |
| 菌菇 program key | `fungi` / `mushrooms` / `macrofungi` | **`fungi`** | 与 iNat / GBIF 等价；macrofungi 在 fungi 下作 submodule |
| 菌菇 submodules | `macrofungi`, `microfungi`, `lichens` | **`macrofungi`, `lichens`** | microfungi 野外调查可识别性低，先不列；地衣（lichen）传统上视为复合生物但调查界归入 fungi |
| protocol 命名 | 见 §4 | （见下） | |

---

## 3. backbone 引用

| program | jurisdiction | backbone |
|---|---|---|
| aquatic_vertebrates | mainland_china | Fauna Sinica（中国动物志·鱼类）、MEE 内陆水域生物多样性调查规范、FishBase 中国子集 |
| aquatic_vertebrates | taiwan          | TaiCOL 鱼类、台湾鱼类资料库（Fish Database of Taiwan, ASRC）、TaiBIF 整合 |
| fungi               | mainland_china | 中国真菌志（Flora Fungorum Sinicorum）、Index Fungorum、MEE 大型真菌调查标准（draft） |
| fungi               | taiwan          | TaiCOL 真菌、TaiBIF、Index Fungorum |

> **诚实声明：** 上述 backbone 是已被学界引用的权威源；本工单交付的 seed JSON 仅为 importer + offline lookup 验证用（每包 2–3 条样本），**不是穷尽列表**，沿用既有 `seed_only=true, exhaustive_species_content=false` 标记。补全靠后续 W4+ 工单从权威库批量导入。

---

## 4. 新增 protocols（最小可用集）

| protocol_id | program | submodules | sampling_unit | track_policy | 备注 |
|---|---|---|---|---|---|
| `fish_electrofishing`   | aquatic_vertebrates | `[freshwater_fish, estuarine_fish]` | electrofishing_pass | required | 内陆水域电捕；需要持证 |
| `fish_visual_count`     | aquatic_vertebrates | `[freshwater_fish, estuarine_fish, marine_fish]` | snorkel_or_dive_swim | required | 浮潜/潜水视觉计数 |
| `fungi_transect`        | fungi               | `[macrofungi, lichens]` | fungi_transect_walk | required | 样线 |
| `fungi_quadrat`         | fungi               | `[macrofungi, lichens]` | fungi_plot_visit | optional | 样方 |

> 没有放 `fish_environmental_dna` / `fish_seine_net` / `fungi_substrate_survey` 等，避免一次开太大；后续 W3+ 按需补。

---

## 5. 4 个新 packages 概要

| package_id | jurisdiction | program | taxon_groups | expected_count（seed） |
|---|---|---|---|---|
| `cn_mainland_aquatic_vertebrates_seed` | mainland_china | aquatic_vertebrates | freshwater_fish, estuarine_fish, marine_fish | 3 |
| `cn_mainland_fungi_seed`               | mainland_china | fungi               | macrofungi, lichens                          | 3 |
| `tw_aquatic_vertebrates_seed`          | taiwan         | aquatic_vertebrates | freshwater_fish, estuarine_fish, marine_fish | 3 |
| `tw_fungi_seed`                        | taiwan         | fungi               | macrofungi, lichens                          | 3 |

每个包附带 `local_seed_assets` 指向新增的 seed JSON。

---

## 6. 数据变更影响面

| 文件 | 变更 |
|---|---|
| `species_monitoring_platform/backend/data/taxonomy_packages.json` | 顶层 `taxonomy_release_id` 改为 `taxonomy_seed_release_2026_06_10`，`manifest_version` 改为 `2026-06-10-fish-fungi-add`；`packages[]` 追加 4 项 |
| `species_monitoring_platform/backend/data/survey_protocols.json` | `registry_version` 改为 `2026-06-10`；`platform_scope.programs` 加 `aquatic_vertebrates`, `fungi`；`protocols[]` 追加 4 项 |
| `species_monitoring_platform/backend/data/mainland_fish_taxonomy_seed.json` | 新建 |
| `species_monitoring_platform/backend/data/mainland_fungi_taxonomy_seed.json` | 新建 |
| `species_monitoring_platform/backend/data/taiwan_fish_taxonomy_seed.json` | 新建 |
| `species_monitoring_platform/backend/data/taiwan_fungi_taxonomy_seed.json` | 新建 |
| `docs/taxonomy_api_contract.md` | bump 到 v1.1；§2.1 加 2 个 program；§2.3 加 4 个 protocol；§2.4 加新 submodules；§5 cheat sheet 扩到 20 行+；§6 缺口 3 标记为"已修复" |
| `scripts/algo_d/audit_taxonomy_contract.py` | `LEGAL_FIVE_TUPLES` 加新组合 |

不需要改动的：
- `shared/backend/stores/taxonomy_catalog.py` / `survey_store.py` —— 数据驱动的，无须改动
- `species_monitoring_platform/backend/routes/taxonomy.py` —— 路由也是数据驱动
- 现有 sqlite —— 后端首次启动会 rebuild release，旧的留作历史

---

## 7. 部署 & 回滚

### 部署
```powershell
# 1) 把改动 commit + push（你做）
git add species_monitoring_platform/backend/data/{taxonomy_packages.json,survey_protocols.json,mainland_fish_taxonomy_seed.json,mainland_fungi_taxonomy_seed.json,taiwan_fish_taxonomy_seed.json,taiwan_fungi_taxonomy_seed.json} docs/taxonomy_api_contract.md docs/algo_d/2026-06-10_add_fish_fungi_programs.md scripts/algo_d/audit_taxonomy_contract.py
git commit -m "Algo-D: add aquatic_vertebrates and fungi programs (8-group coverage)"

# 2) 启动后端，让它自动 rebuild taxonomy release（首次启动会跑）
cd "f:\Gorsachius magnificus\species_monitoring_platform\backend"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# 3) 验证新 release 已 active
curl http://127.0.0.1:8000/api/admin/taxonomy/releases/current
# -> {"taxonomy_release_id":"taxonomy_seed_release_2026_06_10", ...}

# 4) 跑契约审计，新 5-tuples 应全部 200
python "f:\Gorsachius magnificus\scripts\algo_d\audit_taxonomy_contract.py"
# -> 期望: 20+ tuple PASS（原 16 + 新 4 program×jurisdiction 组合下的 protocol 行）
```

### 回滚
1. `git revert <commit-hash>` 撤回数据文件改动
2. 后端启动后会重新激活旧 release（基于现存 sqlite 的 release table）
3. 或调 admin 接口 `POST /api/admin/taxonomy/releases/{old_release_id}/activate`

---

## 8. 风险

| # | 风险 | 缓解 |
|---|------|---|
| 1 | seed JSON 的样本物种名拼错（学名易错） | 每个学名都在文件里附上 GBIF/iNat/TaiCOL ID 做交叉校验链接，进 PR 时 reviewer 手动逐条比对 |
| 2 | `aquatic_vertebrates` 不只是鱼（鲸豚两栖也算），未来扩展模糊 | 在 §2 命名表已声明意图，doc 也写明；后续如新增鲸豚单独建 `program=marine_mammals` |
| 3 | 新 program 没有真的"测试覆盖物种 ≥30 条"，调用方可能误以为这是 ready-for-prod | seed 包统一 `seed_only=true`、`exhaustive_species_content=false`，前端要消费 metadata 时显式标灰 |
| 4 | 改 `taxonomy_release_id` 后旧 sqlite 不动，但运行时新 rebuild 可能失败 | 先在 dev 环境跑 `POST /api/admin/taxonomy/releases/rebuild?force=true&activate=false` 验证，再让 activate |

---

## 9. 签字

- [ ] 算法 D：__________  日期：__________
- [ ] 工程师 B（taxonomy API + survey_store 维护）：__________  日期：__________
- [ ] 项目主管 / sponsor：__________  日期：__________
