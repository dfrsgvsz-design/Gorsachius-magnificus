# 工单 #D-W2-001 · 权威名录拉取与双向对齐

> 发件人：PM
> 收件人：Worker D（算法 & 数据工程师）
> 下发时间：W1 末（计划生效：W2 周一 09:00）
> 适用范围：仅 species_monitoring_platform（acoustic_platform 已软降范）
> 工单状态：PUBLISHED · 待 DRI 24h 内书面接单

---

## 【思路定调】

你不是"把 PDF 转成 JSON 的工人"。你是**让这个 App 的物种数据库变得能上学术报告、能过审、能让科研单位拿走就用的人**。

`backend/data/biodiversity_references/` 里 PM 已经把 6 套权威源（国家级一二级、三有、海南省级、红色名录、调查方法、海洋、植物、海南鳽）的**结构、来源、schema** 写好了。但**数据本身没拉**——这是你的活。

不允许的事：
- 拿任何非官方源的"整理版"名录灌库（公众号 / 抖音 / AI 生成）
- 跳过 schema 检验直接 import
- 不写 diff 报告就 bump manifest_signature
- 让"数量对不上官方计数"的解析结果进库

你的产出 = species_monitoring_platform 上线后能否拿"科研合规"卖点。

---

## 【任务清单】

### 🔴 P0 W2 周一 → 周三 · 拉取 4 份主名录

按下表逐条完成。**每完成一条提交一个 commit + PR**，PM 当天评审：

| 序 | 名录 | 来源 | 拉取动作 |
|---|---|---|---|
| 1 | 国家重点保护野生动物名录 2021 | https://www.forestry.gov.cn/c/www/lczc/90131.jhtml | 下载附件 PDF → OCR/解析 → JSON |
| 2 | 国家重点保护野生植物名录 2021 | 同上公告 | 同 |
| 3 | 有重要生态、科学、社会价值的陆生野生动物名录 2023 | https://www.gov.cn/zhengce/zhengceku/202307/content_6889361.htm | 下载 PDF → 解析 → JSON |
| 4 | 中国生物多样性红色名录-脊椎动物卷 2020 | https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/202305/t20230522_1030745.html | 下载 PDF → 解析 → JSON |

**统一输出格式**：参考 `backend/data/biodiversity_references/0X_*.md` 各份"五、数据 schema"章节。

**统一存放位置**：`backend/data/parsed_lists/<list_name>_<version>.json`

**校验命令**（PM 会跑这个验你）：

```python
# tests/test_authoritative_lists.py
def test_national_protected_2021_count():
    data = json.load(open("backend/data/parsed_lists/national_protected_2021.json"))
    assert data["list_meta"]["total_species"] == 980
    assert data["list_meta"]["total_categories"] == 8
    # 一级 234 + 二级 746 = 980
    grade_1 = sum(1 for s in data["species"] if s["protection_level"] == "国家一级")
    grade_2 = sum(1 for s in data["species"] if s["protection_level"] == "国家二级")
    assert grade_1 == 234, f"国家一级应 234，实际 {grade_1}"
    assert grade_2 == 746, f"国家二级应 746，实际 {grade_2}"
```

类似的测试每份 1 个，全绿才能进下一步。

### 🔴 P0 W2 周三 → 周四 · 拉取 2 份海洋 + 海南省级

| 序 | 名录 | 来源 |
|---|---|---|
| 5 | 海南省省级重点保护陆生野生动物名录 2024 | 海南省政府官网 |
| 6 | 海南省省级重点保护野生植物名录 2024 | 海南省政府官网 |

输出位置：`backend/data/parsed_lists/hainan_*_2024.json`

> 海洋部分的名录已包含在第 1 条（国家重点保护 2021 名录的水生部分，带 `*` 标注），不单独拉。

**校验**：海南动物 212 种 / 海南植物 206 种 + 兰科规则单独 flag。

### 🔴 P0 W2 周四 → 周五 · 灌入 taxonomy_catalog.sqlite3

```python
# scripts/import_authoritative_lists.py
# 把上面 6 份 JSON 灌入 taxonomy_catalog.sqlite3
# 1. 新增 4 个表（如不存在）：
#    - national_protection (level int, name_la text, name_zh text, ...)
#    - three_have_list (name_la text, ...)
#    - china_red_list (name_la text, grade text, ...)
#    - provincial_protection (province text, name_la text, level text, ...)
# 2. UPSERT 模式，避免重复
# 3. 关联到 taxa 主表，通过 name_la 匹配
# 4. 更新 manifest_signature
# 5. 输出 import_report.json: {table: rows_added, rows_updated, rows_failed}
```

**验收命令**：

```bash
cd species_monitoring_platform/backend
python scripts/import_authoritative_lists.py --dry-run
python scripts/import_authoritative_lists.py --commit
python -m pytest tests/test_authoritative_lists.py -v
```

**验收标准**：
- dry-run 报告 0 错误
- commit 后 manifest_signature 更新
- 所有 pytest 绿

### 🔴 P0 W2 周五 · 物种头三选一收敛（你工单原 #1 的延续）

你上一份工单 #D-W1-001 里那个"物种头 217 vs 223 mapping mismatch"的三选一决策，**在拿到这 6 份权威名录后必须 W2 末闭环**：

- 选 a（升 head 到 223）：用上面新拉的国家级 + 三有名录做训练增量
- 选 b（锁 mapping 到 217）：在 taxonomy_catalog 中明示哪 6 个被弃用
- 选 c（重训）：用新拉的 1924 三有名录做候选物种集

PM 周五闸门会上要求你出书面决策草稿 + 实施动作。

### 🟡 P1 W3 · Diff 报告 + 业务方校对入口

```python
# scripts/generate_taxonomy_diff_report.py
# 对比 import 前后的 taxonomy_catalog 状态:
# - 新增物种数
# - 修订 protection_level 的物种
# - 新增的 三有 物种
# - 物种学名变更（FoC 修订后）
# 输出: submission/reports/taxonomy_diff_W2.md
```

业务方 W3 中会拿这份 diff 报告抽 30 个物种做学术校对（详见 `00_README.md` §六）。

### 🟢 P2 W3-W4 持续 · HJ 710 PDF 解析（仅摘要章节）

```python
# scripts/parse_hj710_methods.py
# 下载 HJ 710.1~710.11 共 11 份 PDF
# 仅解析"主要内容、技术要求和方法"章节
# 输出: backend/data/parsed_protocols/hj710_<n>_methods.json
# Schema:
# {
#   "standard_id": "HJ 710.4-2014",
#   "taxon_group": "鸟类",
#   "methods": [
#     {
#       "name": "样线法",
#       "applicability": "...",
#       "parameters": {...},
#       "season": "..."
#     }
#   ]
# }
```

这一步是为 W3 末 App 内"协议选择"页面的协议参数自动填充打底。

### 🟢 P2 W4 持续 · iNat / GBIF / eBird API 接入

不是为了**名录**（不接受任何 API 作为权威名录），而是为了**occurrence data**：

```python
# scripts/sync_occurrence_data.py
# 拉取每个保护物种的最近 5 年观察记录
# 用途：
#   - App 内"近期发现"地图图层
#   - 调查项目推荐"该区域可能见到的物种"
#   - 不进 taxonomy_catalog，进单独的 occurrences 表
```

---

## 【验收标准】

| 项 | 量化标准 |
|---|---|
| 4 份主名录 JSON 解析准确性 | 物种数与官方计数 100% 一致（980/455/1924/4767）|
| 2 份海南省级 JSON 解析准确性 | 212 / 206 与官方一致 |
| taxonomy_catalog 灌入成功率 | rows_failed = 0 |
| pytest 覆盖率 | 6 份名录每份至少 3 个测试，全绿 |
| diff 报告完整性 | 含新增、修订、弃用、未匹配 4 个分类 |
| 物种头三选一决策 | 入 Decision Log D-NN，双签 PM + Sponsor |
| 双签 | PM + B 工号（B 工号要消费这份数据，必须确认 schema 可用）|

---

## 【DRI】
**Worker D**

## 【截止】
- P0：W2 周五 18:00（hard）
- P1：W3 周三 18:00
- P2：W4 末

## 【依赖谁】
- **Sponsor**：物种头三选一决策的最终拍板（W1 周三前给 D 决策范围）
- **PM**：6 份 schema 已在 `biodiversity_references/0X_*.md` 各份"五"章节定义，已就绪
- **A 工号**：`taxonomy_catalog.sqlite3` 的 lifespan 加载要在 A 修完 503 后才稳定（W1 末）
- **网络**：4 个国家级 PDF 来自 forestry.gov.cn / gov.cn / mee.gov.cn，国内访问稳定；海南来自 hainan.gov.cn，同样稳定。无翻墙需求。

## 【谁依赖你】
- **A 工号**：`taxonomy/search` API 的返回需要这份数据，否则 W2 末协议契约锁不了
- **B 工号**：前端物种联想控件 + 物种详情页（三层徽章 + 红色名录评级）需要你
- **PM**：W2 末闸门第 4 项"算法/数据"维度评分依赖这份数据
- **业务方**：W3 中抽 30 个物种做学术校对的 diff 报告依赖你

---

## 【接单要求】

- W1 周五 18:00 前书面回复 PM：是否接单（默认接），如有异议指出哪条 P0 无法在期内完成
- 接单后在工单顶部追加状态变更日志：
  ```
  - 2026-MM-DD HH:MM  DRAFT → PUBLISHED （PM）
  - 2026-MM-DD HH:MM  PUBLISHED → IN-PROGRESS  （D）
  ```
- 状态变更必须当日同步到 PM standup 群

---

## 【与其他工单的对接】

| 关联工单 | 关系 |
|---|---|
| D-W1-001（物种头三选一）| 本工单的 P0 第 5 条收尾延续 |
| A-W1-001（修 taxonomy/search 422）| A 修完后才能验证你的 schema 字段对得上 |
| B-W2-001（物种联想 + 详情页）| B 在你周五完成后才能开始 W3 任务 |

---

## 【红线】

- ⛔ 不允许跳过 dry-run 直接 commit
- ⛔ 不允许在物种数与官方计数不符时强行通过
- ⛔ 不允许把"未匹配学名"的物种悄悄丢弃 —— 必须出现在 diff 报告未匹配区
- ⛔ 不允许引入任何非本目录登记的数据源
- ⛔ 不允许私下修改 PM 写好的 schema —— 如需调整走 RFC（开个 D-W2-001-rfc.md）

---

## 【附录：本工单需要消费的 PM 资产】

| 路径 | 用途 |
|---|---|
| `species_monitoring_platform/backend/data/biodiversity_references/00_README.md` | 总索引、引用规则 |
| `.../01_national_protected_wildlife_list_2021.md` | 国家级动物 schema |
| `.../02_hainan_protected_wildlife_list_2024.md` | 海南省级 schema（参考其他省同模式）|
| `.../03_china_red_list_vertebrate_2020.md` | 红色名录 schema |
| `.../06_authoritative_sources_registry.md` | 所有 URL + 拉取 SOP |
| `.../07_marine_biodiversity.md` | 海洋部分要点 |
| `.../08_flora_of_china.md` | 植物数据库 schema |
| `.../09_three_have_list_2023.md` | 三有名录 schema |

---

## 【签名】

- PM 下发签字: ✅ 2026-MM-DD HH:MM（待发版填）
- DRI 接单签字: __ ✏️ 待 W1 周五 18:00 前
- Sponsor 知会签字: __ ✏️ 待 W1 周末
