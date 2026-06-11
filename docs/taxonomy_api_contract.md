# Taxonomy API Contract — `/api/surveys/taxonomy/*`

- **责任人（DRI）：** Algo-D（算法 & 数据工程师）
- **首次起草：** 2026-06-10
- **当前版本：** v1.1 · 待 A / B 签字（v1.1 在 v1.0 当天补足"8 大类群"，新增 `aquatic_vertebrates`、`fungi` 两个 program 及配套 protocols / packages，详见 §11 修订记录）
- **配套审计脚本：** `scripts/algo_d/audit_taxonomy_contract.py`
- **配套数据源：** `species_monitoring_platform/backend/data/{survey_protocols.json, taxonomy_packages.json}`
- **背景：** `backend_run.log` 反复出现
  `GET /api/surveys/taxonomy/search?...&limit=250&...` → **422 Unprocessable Entity**。
  这份文档是 **A / B / D 跨角色对齐契约**，目的让 422 永久消失、并把"五元组的合法值矩阵"冻结成版本化资产，下次拓展时改这份文件 + bump 版本号即可。

---

## 1. 五元组词汇表

| 维度 | 类型 | 来源（source of truth） | 用途 |
|---|---|---|---|
| `program`        | string，枚举 | `survey_protocols.json#platform_scope.programs` 和 `taxonomy_packages.json#packages[].program` | 顶层分类。决定调查范畴。 |
| `jurisdiction`   | string，枚举 | 同上 `platform_scope.jurisdictions` | 行政区。决定走哪个本地化包。 |
| `protocol`       | string，枚举 | `survey_protocols.json#protocols[].protocol_id` | 调查方法（点样、线样、相机阵、捕笼……）。 |
| `submodule`      | string，枚举 | `survey_protocols.json#protocols[].submodules[]` *和* `taxonomy_packages.json#packages[].taxon_groups[]` | 物种类群细分。**注意两边定义有出入，见 §6 已知契约缺口 1**。 |
| `taxon_group`    | string，**别名** | 历史前端字段，与 `submodule` 同义 | **见 §6 已知契约缺口 2**。后端 `/api/surveys/taxonomy/search` 当前**不读**这个参数。 |

`q`、`limit` 是非五元组参数，但与契约同等重要，见 §3。

---

## 2. 合法值（authoritative enums）

### 2.1 `program`（5）

| 值 | 中文 | 覆盖类群 |
|---|---|---|
| `terrestrial_vertebrates` | 陆生脊椎动物 | birds, mammals, reptiles, amphibians |
| `plants` | 植物 | vascular_plants, shrubs, trees, herbs（包级别） / plants（协议级别） |
| `insects` | 昆虫 | butterflies, moths, beetles, odonates, other_insects（包级别） / insects（协议级别） |
| `aquatic_vertebrates` | 水生脊椎动物（鱼类） | freshwater_fish, estuarine_fish, marine_fish |
| `fungi` | 真菌（含地衣） | macrofungi, lichens |

> 8 大类群覆盖度：v1.1 已覆盖 8/8 中的 6+2 = 全部（鸟/哺乳/两栖/爬行/鱼/昆虫/植物/菌菇 + 地衣）。详见 `docs/algo_d/2026-06-10_add_fish_fungi_programs.md`。

### 2.2 `jurisdiction`（2）

| 值 | 中文 |
|---|---|
| `mainland_china` | 中国大陆 |
| `taiwan`         | 台湾 |

### 2.3 `protocol`（11）

| protocol_id | program | submodules (canonical) | sampling_unit | track_policy |
|---|---|---|---|---|
| `bird_line_transect`     | terrestrial_vertebrates | `[birds]`                                            | transect_walk                       | required |
| `bird_point_count`       | terrestrial_vertebrates | `[birds]`                                            | point_count_station_visit           | optional |
| `mammal_trap_net`        | terrestrial_vertebrates | `[mammals]`                                          | trap_station_night_or_check         | optional |
| `herp_infrared_camera`   | terrestrial_vertebrates | `[reptiles, amphibians]`                             | camera_station_deployment_or_check  | optional |
| `plant_quadrat`          | plants                  | `[plants]`                                           | plot_visit                          | optional |
| `plant_transect`         | plants                  | `[plants]`                                           | vegetation_transect_visit           | optional |
| `insect_transect`        | insects                 | `[insects]`                                          | insect_transect_walk                | required |
| `fish_electrofishing`    | aquatic_vertebrates     | `[freshwater_fish, estuarine_fish]`                  | electrofishing_pass                 | required |
| `fish_visual_count`      | aquatic_vertebrates     | `[freshwater_fish, estuarine_fish, marine_fish]`     | snorkel_or_dive_swim                | required |
| `fungi_transect`         | fungi                   | `[macrofungi, lichens]`                              | fungi_transect_walk                 | required |
| `fungi_quadrat`          | fungi                   | `[macrofungi, lichens]`                              | fungi_plot_visit                    | optional |

每个协议在 `mainland_china` 和 `taiwan` 都可用（十一协议 × 二辖区 = 22 个合法 `(protocol, jurisdiction)` 组合）。

### 2.4 `submodule`（按 program 分组）

**严格遵循 `survey_protocols.json#protocols[].submodules[]`**（这是 API `/api/surveys/taxonomy/search` 实际接受的取值）：

| program | 合法 submodule |
|---|---|
| `terrestrial_vertebrates` | `birds`, `mammals`, `reptiles`, `amphibians` |
| `plants` | `plants` |
| `insects` | `insects` |
| `aquatic_vertebrates` | `freshwater_fish`, `estuarine_fish`, `marine_fish` |
| `fungi` | `macrofungi`, `lichens` |

`taxonomy_packages.json` 里植物/昆虫 program 的 `taxon_groups` 字段更细（butterflies / vascular_plants / 等），但**那是包内部的物种归类，不是 API submodule 的合法取值**。混淆这两个会导致 0 结果或 422。详见 §6。

### 2.5 `q`、`limit`、`taxon_group`、`package_ids`

| 参数 | 类型 | 合法范围 | 行为 |
|---|---|---|---|
| `q`           | string | 任意 unicode，最长 200 字符 | 全文匹配 `scientific_name + chinese + english + synonyms` |
| `limit`       | int    | **`1 ≤ limit ≤ 200`** | **超出 200 返回 422**（这就是当前 bug）。默认 25。 |
| `taxon_group` | string | **当前 API 不接受**（写了不报错但被忽略）| 见 §6 缺口 2 |
| `package_ids` | list[string] | 见 §2.6 | 客户端不要直接传；由后端 `_resolve_taxonomy_search_package_ids` 从 (program, protocol, jurisdiction) 推导 |

### 2.6 `package_id`（10，全自动推导，不需要前端传）

| package_id | jurisdiction | program | taxon_groups |
|---|---|---|---|
| `cn_mainland_terrestrial_vertebrates_seed` | mainland_china | terrestrial_vertebrates | birds, mammals, amphibians, reptiles |
| `cn_mainland_plants_seed`                  | mainland_china | plants                  | vascular_plants, shrubs, trees, herbs |
| `cn_mainland_insects_seed`                 | mainland_china | insects                 | butterflies, moths, beetles, odonates, other_insects |
| `cn_mainland_aquatic_vertebrates_seed`     | mainland_china | aquatic_vertebrates     | freshwater_fish, estuarine_fish, marine_fish |
| `cn_mainland_fungi_seed`                   | mainland_china | fungi                   | macrofungi, lichens |
| `tw_terrestrial_vertebrates_seed`          | taiwan         | terrestrial_vertebrates | birds, mammals, amphibians, reptiles |
| `tw_plants_seed`                           | taiwan         | plants                  | vascular_plants, shrubs, trees, herbs |
| `tw_insects_seed`                          | taiwan         | insects                 | butterflies, moths, beetles, odonates, other_insects |
| `tw_aquatic_vertebrates_seed`              | taiwan         | aquatic_vertebrates     | freshwater_fish, estuarine_fish, marine_fish |
| `tw_fungi_seed`                            | taiwan         | fungi                   | macrofungi, lichens |

---

## 3. 端点契约速查

### 3.1 `GET /api/surveys/taxonomy/search`

```http
GET /api/surveys/taxonomy/search
  ?program={program}            # optional, see §2.1
  &jurisdiction={jurisdiction}  # optional, see §2.2
  &protocol={protocol}          # optional, see §2.3
  &submodule={submodule}        # optional, see §2.4
  &q={query string}             # optional, full-text match
  &limit={1..200}               # default 25, hard cap 200
```

**返回：**

```json
{
  "total": <int>,
  "results": [ { "scientific_name": ..., "taxon_id": ..., "matched_name": ..., ... } ],
  "filters": { "program": ..., "submodule": ..., "protocol": ..., "jurisdiction": ..., "q": ..., "limit": ..., "package_ids": [...] }
}
```

**状态码：**
- `200` 正常（结果可能为空，参考 `total`）
- `422` 参数验证失败（**目前主要原因是 `limit > 200`**）
- `503` `taxonomy_catalog` 未就绪（部署初始化中 / strict mode 失败）

### 3.2 `GET /api/surveys/taxonomy/packages`

```http
GET /api/surveys/taxonomy/packages
  ?jurisdiction={jurisdiction}
  &program={program}
  &protocol={protocol}
  &region={region}              # 当前实现不强制
```

### 3.3 `GET /api/surveys/protocols`

```http
GET /api/surveys/protocols
  ?program={program}
  &protocol={protocol}
```

---

## 4. 复现 / 修复 422 的最短路径

### 4.1 复现

```bash
curl -i "http://127.0.0.1:8000/api/surveys/taxonomy/search?jurisdiction=mainland_china&program=terrestrial_vertebrates&protocol=bird_line_transect&taxon_group=birds&limit=250&submodule=birds"
# -> HTTP/1.1 422 Unprocessable Entity
# -> {"detail":[{"type":"less_than_equal","loc":["query","limit"],"msg":"Input should be less than or equal to 200","input":"250","ctx":{"le":200}}]}
```

### 4.2 修复（任选其一）

| 方案 | 修改面 | 推荐度 |
|---|---|---|
| **A.** 前端把 `limit` 改成 `≤ 200` | `frontend/src/lib/api.js` 或调用方 | ★★★（最贴契约） |
| B. 后端把 `le=200` 抬到 `le=500`（必要时仅对管理面） | `backend/routes/taxonomy.py` 第 55 行 | ★（短期止血、需 PM 同意） |
| C. 引入分页（page+per_page），上限按页生效 | 改契约，A/B 双方都要动 | 长期方案，进 W4+ |

> 🚫 不要"接受 `taxon_group=birds` 这个未声明参数"：FastAPI 当前已经默默丢弃，不影响结果；正确做法是前端用 `submodule=birds` 替代（语义一致），删掉冗余 `taxon_group`。详见 §6 缺口 2。

---

## 5. 合法"五元组"组合 cheat sheet（34 行）

下表每行是一个 `(program, jurisdiction, protocol, submodule, taxon_group)` 的有效组合，A/B 实现时按这张表测试。v1.1 在 v1.0 的 16 行基础上加了 18 行（aquatic_vertebrates 10 行 + fungi 8 行）。

| program | jurisdiction | protocol | submodule | taxon_group (alias of submodule) |
|---|---|---|---|---|
| terrestrial_vertebrates | mainland_china | bird_line_transect      | birds            | birds |
| terrestrial_vertebrates | mainland_china | bird_point_count        | birds            | birds |
| terrestrial_vertebrates | mainland_china | mammal_trap_net         | mammals          | mammals |
| terrestrial_vertebrates | mainland_china | herp_infrared_camera    | reptiles         | reptiles |
| terrestrial_vertebrates | mainland_china | herp_infrared_camera    | amphibians       | amphibians |
| terrestrial_vertebrates | taiwan         | bird_line_transect      | birds            | birds |
| terrestrial_vertebrates | taiwan         | bird_point_count        | birds            | birds |
| terrestrial_vertebrates | taiwan         | mammal_trap_net         | mammals          | mammals |
| terrestrial_vertebrates | taiwan         | herp_infrared_camera    | reptiles         | reptiles |
| terrestrial_vertebrates | taiwan         | herp_infrared_camera    | amphibians       | amphibians |
| plants                  | mainland_china | plant_quadrat           | plants           | plants |
| plants                  | mainland_china | plant_transect          | plants           | plants |
| plants                  | taiwan         | plant_quadrat           | plants           | plants |
| plants                  | taiwan         | plant_transect          | plants           | plants |
| insects                 | mainland_china | insect_transect         | insects          | insects |
| insects                 | taiwan         | insect_transect         | insects          | insects |
| aquatic_vertebrates     | mainland_china | fish_electrofishing     | freshwater_fish  | freshwater_fish |
| aquatic_vertebrates     | mainland_china | fish_electrofishing     | estuarine_fish   | estuarine_fish |
| aquatic_vertebrates     | mainland_china | fish_visual_count       | freshwater_fish  | freshwater_fish |
| aquatic_vertebrates     | mainland_china | fish_visual_count       | estuarine_fish   | estuarine_fish |
| aquatic_vertebrates     | mainland_china | fish_visual_count       | marine_fish      | marine_fish |
| aquatic_vertebrates     | taiwan         | fish_electrofishing     | freshwater_fish  | freshwater_fish |
| aquatic_vertebrates     | taiwan         | fish_electrofishing     | estuarine_fish   | estuarine_fish |
| aquatic_vertebrates     | taiwan         | fish_visual_count       | freshwater_fish  | freshwater_fish |
| aquatic_vertebrates     | taiwan         | fish_visual_count       | estuarine_fish   | estuarine_fish |
| aquatic_vertebrates     | taiwan         | fish_visual_count       | marine_fish      | marine_fish |
| fungi                   | mainland_china | fungi_transect          | macrofungi       | macrofungi |
| fungi                   | mainland_china | fungi_transect          | lichens          | lichens |
| fungi                   | mainland_china | fungi_quadrat           | macrofungi       | macrofungi |
| fungi                   | mainland_china | fungi_quadrat           | lichens          | lichens |
| fungi                   | taiwan         | fungi_transect          | macrofungi       | macrofungi |
| fungi                   | taiwan         | fungi_transect          | lichens          | lichens |
| fungi                   | taiwan         | fungi_quadrat           | macrofungi       | macrofungi |
| fungi                   | taiwan         | fungi_quadrat           | lichens          | lichens |

---

## 6. 已知契约缺口（必须在 A/B 签字前对齐）

### 缺口 1：植物 / 昆虫的 `submodule` 粒度不一致
- `survey_protocols.json` 里这两个 program 的 `submodules` 折叠成 `["plants"]` / `["insects"]`
- `taxonomy_packages.json` 里同维度展开成 `vascular_plants/shrubs/trees/herbs` 和 `butterflies/moths/beetles/odonates/other_insects`
- **影响：** 前端要做植物细分（如只查"树木"）当前 API 没有路径
- **建议：** 把协议 `submodules` 同步成包级粒度（在 `survey_protocols.json#protocols[plant_*]#submodules` 里展开）。本变更归 **B 工程师** 后端契约维护。

### 缺口 2：`taxon_group` 是 `submodule` 的历史别名
- 前端代码继续传 `taxon_group=birds`
- 后端 `search_survey_taxonomy` 完全不读，但 FastAPI 不报错（静默忽略未声明 query 参数）
- **影响：** 前端开发者以为参数生效，碰到边界 case 调试困难
- **建议：** 前端在 1 个 PR 内把 `taxon_group` 全部替换成 `submodule`，并删除该字段在 `lib/api.js` 的痕迹。本变更归 **A 工程师** 前端契约维护。

### 缺口 3：8 大类群中 `鱼类` / `菌菇` 缺失 — ✅ 已修复（v1.1）
- v1.1 新增 `aquatic_vertebrates`（含 freshwater_fish/estuarine_fish/marine_fish）、`fungi`（含 macrofungi/lichens）
- 决策文档：`docs/algo_d/2026-06-10_add_fish_fungi_programs.md`
- 涉及数据文件：`taxonomy_packages.json`、`survey_protocols.json` 已 bump 版本；新增 4 个 seed JSON
- **遗留：** 这些 program 当前都是 `seed_only=true, exhaustive_species_content=false`，需要后续 W4+ 从权威库（Fauna Sinica / TaiCOL / Index Fungorum）批量导入

### 缺口 4：`limit` 单页上限 200 太小
- 见 §4。是当前 422 的直接原因。
- **决策建议：** §4.A（前端裁到 ≤ 200）。**A 工程师**这条修了再删 §4 复现里那条 `limit=250`。

---

## 7. 实现侧锚点（开发跳转）

| 位置 | 文件:行 | 职责 |
|---|---|---|
| 路由声明 | `species_monitoring_platform/backend/routes/taxonomy.py:48` | 五元组 Query 参数声明、`limit` 上限 200 |
| package_id 解析 | `species_monitoring_platform/backend/main.py` `_resolve_taxonomy_search_package_ids` | 把 `(program, protocol, jurisdiction)` 映射到 `package_ids` |
| 实际搜索 | `shared/backend/stores/taxonomy_catalog.py:1021 def search` | sqlite 查询 + 评分 + 限流 |
| 数据 source of truth | `species_monitoring_platform/backend/data/taxonomy_packages.json` + `survey_protocols.json` | 启动时加载到内存；改后端要同时 bump `taxonomy_release_id` |
| 触发 422 的实际请求 | `backend_run.log` 行号搜 `taxonomy/search` `422` | 复现样本 |
| 集成测试参考 | `species_monitoring_platform/backend/tests/test_taxonomy_api.py` | 已有的"成功"五元组示例 |

---

## 8. 验收门禁（与 P0 W1 head 工单平级）

| 门禁 | 工具 | 通过条件 |
|---|---|---|
| C1 完整 16 行五元组组合调起来 0 个 4xx | `scripts/algo_d/audit_taxonomy_contract.py --base http://127.0.0.1:8000` | 16/16 返回 200 |
| C2 `limit=200` 不报 422、`limit=201` 返回 422 | 同上 | 边界值符合契约 |
| C3 `taxon_group` 与 `submodule` 同值时返回结果一致 | 同上 | 别名兼容直到 A 修完为止 |
| C4 文档被 A、B、D 三方签字 | 本文件末尾签字行 | 三签齐 |

---

## 9. 变更流程

1. 改 `taxonomy_packages.json` / `survey_protocols.json` 必须同时 bump `taxonomy_release_id`（年-月-日-标识）
2. 改本文件必须 bump §头 "当前版本"，并在末尾"修订记录"加一行
3. 任何 Schema 变更：先动文档 → 再动代码 → 再发 PR（不接受"先写代码后补文档"）

---

## 10. 签字行

- [ ] 算法 D：__________  日期：__________
- [ ] 工程师 A（前端）：__________  日期：__________
- [ ] 工程师 B（后端）：__________  日期：__________
- [ ] 项目主管 / sponsor：__________  日期：__________

## 11. 修订记录

| 版本 | 日期 | 作者 | 变更 |
|---|---|---|---|
| v1.0 | 2026-06-10 | Algo-D | 首版。固化五元组合法值矩阵，定位 422 根因 (`limit > 200`)，列出 4 个已知缺口。 |
| v1.1 | 2026-06-10 | Algo-D | 当天补足"8 大类群"。新增 `aquatic_vertebrates` (freshwater_fish/estuarine_fish/marine_fish) 与 `fungi` (macrofungi/lichens) 两个 program；新增 4 个 protocol (`fish_electrofishing`, `fish_visual_count`, `fungi_transect`, `fungi_quadrat`)；新增 4 个 package；cheat sheet 从 16 行扩到 30 行；缺口 3 标记为已修复。`taxonomy_release_id` bump 到 `taxonomy_seed_release_2026_06_10`。 |
