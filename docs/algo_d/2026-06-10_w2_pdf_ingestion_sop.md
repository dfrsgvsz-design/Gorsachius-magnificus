# Algo-D W2 · 4 份官方源 PDF → JSON → sqlite 灌入 SOP

- **DRI：** Algo-D（Worker D）
- **起草日期：** 2026-06-10
- **生效目标：** taxonomy_release_id = `taxonomy_full_release_2026_W2`（暂用，定稿前可改）
- **关键依赖：** `shared/backend/stores/taxonomy_release_builder.py`、`taxonomy_catalog.py:ensure_bootstrapped`
- **关联文档：** `docs/taxonomy_api_contract.md` v1.1、`docs/algo_d/taxonomy_coverage_report.md`、`docs/algo_d/2026-06-10_add_fish_fungi_programs.md`

---

## 0. 重要发现（必须先看再动）

### 0.0 平台是全国范围调查软件，不是 Hainan-specific
- `platform_config.json` 当前把 `target_species = Gorsachius magnificus`、`study_region = Southern China` 写成首页 demo，但平台**架构上覆盖全国**，物种监测要支持任何中国行政区的野外队
- v1.1 SOP 之前的版本把"海南鳽栖息地同域物种"当成补全主轴，这是**对 demo 的过拟合**，必须纠回到国家级
- 实际操作：本 SOP 起 4 份官方 PDF 之外，**再加 3 份国家级源**（见 §1.5–1.7）；taxonomy_coverage_report 的 priority 排序换成"国家级生态调查"视角

### 0.1 1505 vs 1369 硬编码冲突
`taxonomy_release_builder.py:230-234` 写死：

```python
if expected_jurisdiction == "mainland_china":
    birds_count = submodule_counts.get("birds")
    if birds_count != 1505:
        errors.append(
            f"mainland_china terrestrial vertebrates birds count must be 1505, got {birds_count}"
        )
```

但当前 `taxonomy_packages.json#cn_mainland_terrestrial_vertebrates_seed.submodule_expected_counts.birds = 1369`。

**含义：** 现在的 sqlite 已经被 seed manifest（1369）灌过；如果走 release_builder full path（要求 1505），会校验失败。两条路线（seed-only vs full backbone）在 birds 数量上不对齐。

**解决路径：**
1. ✅ 推荐：W2 ingestion 落到 `taxonomy_full_release_2026_W2` 这个 release_id 下，**与 seed release 平行存在**（catalog 表 `taxonomy_releases` 支持多 release），activate 时切到 full
2. ❌ 不要：直接把 seed 的 birds count 改成 1505 —— seed manifest 描述的是 seed 包，不该和 full backbone 数字对齐

### 0.2 4 份 PDF 与 06 登记册我都拿不到
- 4 份官方 PDF 在政府站点（典型 .gov.cn），需要浏览器人工下载，**我没有工具下**
- 06 登记册 § 8 SOP 不在仓库里
- 因此 **Steps 1–4 由你执行**；Steps 5–7 我现在就把脚本写好

### 0.3 manifest_signature 是自动算的
`taxonomy_catalog.py:1342 _manifest_signature(manifest)` 在 `ensure_bootstrapped` / `_rebuild_catalog` 内自动算并写入 `taxonomy_releases.manifest_signature`。**Step 6 "更新 manifest_signature" 不需要独立动作**，跑完 Step 5 就有。

---

## 1. 4 份 PDF 来源 & 下载位置

### 1.1 国家重点保护野生动植物名录 2021
- **数据：** 980 物种（动物）+ 8 物种（植物特别名录）= 988 条
- **官方源：**
  - 动物：[国家林草局/农业农村部公告第 3 号·2021-02-05](https://www.gov.cn/zhengce/zhengceku/2021-02/09/content_5586227.htm)
  - 植物：[国家林草局/农业农村部公告第 15 号·2021-09-08](https://www.forestry.gov.cn/lyj/1/lyzc/20210908/418377.html)
- **下到本地放：** `species_monitoring_platform/backend/data/taxonomy_releases/taxonomy_full_release_2026_W2/national_protection_2021_动物.pdf` 和 `..._植物.pdf`

### 1.2 海南省级重点保护野生动植物名录 2024
- **数据：** 212 动物 + 206 植物 = 418 条
- **官方源：** [海南省政府公告·2024](https://www.hainan.gov.cn/) — 关键词搜索 "海南省重点保护野生动植物名录"
- **下到本地放：** `..._releases/taxonomy_full_release_2026_W2/hainan_protection_2024_动物.pdf` 和 `..._植物.pdf`

### 1.3 中国脊椎动物红色名录（IUCN 评级映射卷）
- **数据：** IUCN 评级（CR/EN/VU/NT/LC/DD）→ 中国脊椎动物
- **官方源：** [蒋志刚等 (2016) 中国生物多样性·25(5)](http://www.biodiversity-science.net/) — 可下 PDF
- **下到本地放：** `..._releases/taxonomy_full_release_2026_W2/china_red_list_vertebrates_2016.pdf`

### 1.4 11 份 HJ 710 系列环境保护行业标准
- **数据：** 调查 protocol 技术要求与方法
- **官方源：** [中国生态环境部·标准查询](https://www.mee.gov.cn/) 搜 "HJ 710"
- **11 份具体编号（按现有目录推测，请你确认）：**
  - HJ 710.1-2014 生物多样性观测技术导则 总则
  - HJ 710.2-2014 — HJ 710.12-2017（陆生维管植物、陆生贝类、蝴蝶、地衣、苔藓、淡水底栖大型无脊椎、内陆水域鱼类、鸟类、两栖动物、爬行动物、哺乳动物）
- **下到本地放：** `..._releases/taxonomy_full_release_2026_W2/hj710/HJ710.1.pdf` … `hj710/HJ710.14.pdf`

### 1.5 三有名录 2023（与国家重点保护并行）
- **数据：** 1924 种陆生野生动物（兽 91 + 鸟 1028 + 爬 450 + 两栖 253 + 昆虫 96 + 蛛形 2 + 寡毛 4）
- **官方源：** [国家林业和草原局公告 2023年第17号·2023-06-26](http://www.forestry.gov.cn/c/www/lcdt/510063.jhtml)（《有重要生态、科学、社会价值的陆生野生动物名录》）
- **与 1.1 的关系：** "国家重点保护" (Class I/II) 是高级保护；"三有名录" 是中级保护。**两个清单互不重叠**——三有名录中已列入国家重点的物种会被踢出。
- **下到本地放：** `..._releases/taxonomy_full_release_2026_W2/sanyou_protection_2023/sanyou_2023.pdf`
- **JSON schema：** 同 §3.1 + 加 `"protection_tier": "sanyou_2023"` 标签
- **校验：** `len(rows) == 1924`，且各 taxon_group 分组数与官方公告严格一致（兽 91 / 鸟 1028 …）

### 1.6 中国海洋生物名录（刘瑞玉 2008）
- **数据：** 22629 种现生生物（46 门）；含原核、海藻、海洋动物。是 ChaRMS (Chinese Register of Marine Species) 基础
- **官方源：** 中国科学院海洋研究所主编、科学出版社 2008，1267 页。**没有官方公开 PDF**——纸质 + 电子版（图书馆订阅）；可通过 [ChaRMS 在线](https://www.marinespecies.org/aphia.php?p=stats&country=zhCN) 抓部分元数据
- **替代源：** 黄宗国 2008《中国海洋生物种类与分布》(增订版) 22561 种；或 2018《中国海洋物种和图集》28000+ 种
- **本平台采决：** **新增一个 program = `marine_organisms`**（不是塞进 aquatic_vertebrates，那个只是鱼类）。submodules 至少包括：`marine_invertebrates`、`marine_algae`、`marine_mammals`（含鲸豚）、`marine_fish`（与现有 aquatic_vertebrates.marine_fish 同步而非重复）
- **下到本地放：** `..._releases/taxonomy_full_release_2026_W2/marine_biota_china/parsed.json`（用 ChaRMS 抓 + 刘瑞玉名录 OCR 拼）
- **校验：** 因为是非政府公开 PDF，行数门槛 ≥ 20000 即接受（不强 22629），但要把 source_version_date 和具体源说清楚

### 1.7 Flora of China (FOC，《中国植物志》英文修订版)
- **数据：** 31500 种维管植物（22 卷文本 + 22 卷图集，1988–2013 完成）
- **官方源：**
  - [iPlant.cn/foc 中文官方镜像](http://www.iplant.cn/foc/AboutFoc)
  - [eFlora @ Harvard University Herbaria](http://flora.huh.harvard.edu)
  - [Missouri Botanical Garden eFloras](https://www.efloras.org/flora_page.aspx?flora_id=2)
- **解析路径：** eFloras 提供物种页 HTML/XML 可批量抓取；不需要 OCR PDF。也可以直接拿 Tropicos 数据库
- **下到本地放：** `..._releases/taxonomy_full_release_2026_W2/flora_of_china/parsed.json`
- **校验：** `len(rows) ≥ 31000`（FOC 实际入库可能 31500，允许 ±500 容差因为分类校订）

---

## 2. 数据流总览

```
Step 1-4:  你下载 4 份 PDF → 放进
           backend/data/taxonomy_releases/taxonomy_full_release_2026_W2/

Step 5(a): 跑 parsers（4 个 stub 已就位，需要你确认 PDF 后我落实）
           PDFs → backend/data/taxonomy_releases/taxonomy_full_release_2026_W2/<source>/parsed.json

Step 5(b): 写 source_manifest.json（每个 jurisdiction × program 一个）
           backend/data/taxonomy_sources/taxonomy_full_release_2026_W2/
             mainland_china/terrestrial_vertebrates/source_manifest.json
             mainland_china/plants/source_manifest.json
             mainland_china/insects/source_manifest.json
             taiwan/...  (本工单暂不动 taiwan，留 seed 数据)

Step 5(c): 跑 scripts/algo_d/rebuild_taxonomy_from_sources.py
           - 调 build_full_release_manifest()
           - 写到 taxonomy_packages.full.json（与 seed 版并存）
           - 触发 catalog.rebuild_release(force=True, activate=False)
           - 候选 release 入库

Step 6:    自动（manifest_signature 在 rebuild_catalog 内算）

Step 7:    跑 scripts/algo_d/validate_pdf_to_json_row_counts.py
           - PDF 表行数 vs parsed.json 条目数 vs sqlite 表 count 严格相等
           - 启动 App + grep 启动日志：0 "does not match checkpoint head"
           - 启动日志 catalog packages: N, taxa: M, ...
```

---

## 3. 7 个动作的细则

### Step 1 国家重点保护 2021 PDF → JSON
- 行数门槛：988 条（980 动物 + 8 植物）
- JSON schema：
  ```json
  {
    "source": "national_protection_2021",
    "source_version_date": "2021-02-09",
    "release_id": "taxonomy_full_release_2026_W2",
    "rows": [
      { "scientific_name": "...", "simplified_chinese_name": "...", "protection_level": "I" | "II", "kingdom": "Animalia" | "Plantae", "taxon_group": "..." }
    ]
  }
  ```
- 落盘到：`backend/data/taxonomy_releases/taxonomy_full_release_2026_W2/national_protection_2021/parsed.json`
- **校验：** `len(rows) == 988`，不等于直接拒收。

### Step 2 海南省级 2024 PDF → JSON
- 行数门槛：418 条（212 动物 + 206 植物）
- JSON schema 同 Step 1，加 `"province_protection": "hainan_provincial"` 字段
- 落盘到：`..._releases/.../hainan_protection_2024/parsed.json`
- **校验：** `len(rows) == 418`

### Step 3 中国脊椎动物红色名录 → JSON
- 这一份不是新物种，是给已有物种**打 IUCN 标签**。
- JSON schema：
  ```json
  {
    "source": "china_red_list_vertebrates_2016",
    "source_version_date": "2016-08-01",
    "rows": [
      { "scientific_name": "...", "red_list_status": "CR" | "EN" | "VU" | "NT" | "LC" | "DD" | "NE" }
    ]
  }
  ```
- 用途：ingestion 时 merge 进 status 字段
- 落盘到：`..._releases/.../china_red_list_vertebrates_2016/parsed.json`

### Step 4 11 份 HJ 710 → 协议方法文档
- 不进 taxonomy_catalog（这是 protocol 不是 species）
- 解析"技术要求和方法"章节为 markdown / json，作为 `survey_protocols.json` 的 `standards_refs` 锚点 + 单独的方法描述文档
- 落盘到：`docs/standards/hj710_methods.md` + `docs/standards/hj710_methods.json`

### Step 5 走 taxonomy_release_builder.py 灌进 sqlite
```powershell
# Step 5(c) 自动运行，参数固定
python "f:\Gorsachius magnificus\scripts\algo_d\rebuild_taxonomy_from_sources.py" `
  --release-id "taxonomy_full_release_2026_W2" `
  --activate false
# 期望：candidate release 入库；现役 release 不变（seed_release_2026_06_10 继续 active）

# 验证候选 release
curl http://127.0.0.1:8000/api/admin/taxonomy/releases
# 期望：list 里有 "taxonomy_full_release_2026_W2"、is_current=False

# 等 PM 评审通过再激活
curl -X POST http://127.0.0.1:8000/api/admin/taxonomy/releases/taxonomy_full_release_2026_W2/activate
```

### Step 6 manifest_signature 更新
自动。`_rebuild_catalog` 内部已经算 hash 并写 `taxonomy_releases.manifest_signature` 列 + meta 表的 `manifest_signature` 键。**不需要单独脚本。** 验证：

```powershell
# sqlite 直接查
python -c "
import sqlite3
c = sqlite3.connect(r'f:\Gorsachius magnificus\species_monitoring_platform\backend\data\survey_store\taxonomy_catalog.sqlite3')
for row in c.execute('SELECT release_id, substr(manifest_signature, 1, 16), imported_at, activated_at FROM taxonomy_releases ORDER BY imported_at DESC'):
    print(row)
"
```

### Step 7 启动 App + 双重校验
```powershell
# (a) PDF 行数 vs JSON 行数 vs sqlite 计数严格一致
python "f:\Gorsachius magnificus\scripts\algo_d\validate_pdf_to_json_row_counts.py" `
  --release-id "taxonomy_full_release_2026_W2"
# 期望：所有 4 个 source 表格 行数严格一致；不严格直接 FAIL 不进 release

# (b) 启动后端，0 trim 警告
cd "f:\Gorsachius magnificus\species_monitoring_platform\backend"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 2>&1 | Select-String -Pattern "does not match"
# 期望：无任何匹配
```

---

## 4. 现已就位的脚本（不需要 PDF 就能跑）

| 脚本 | 用途 | 何时跑 |
|---|---|---|
| `scripts/algo_d/rebuild_taxonomy_from_sources.py` | Step 5(c) ingestion runner | 你把 PDF / parsed.json / source_manifest.json 都摆好之后 |
| `scripts/algo_d/validate_pdf_to_json_row_counts.py` | Step 7 行数严格校验 | 跑完 ingestion 之后 |
| `scripts/algo_d/_templates/source_manifest_template.json` | 4 份 source_manifest 起草模板 | Step 5(b) 你按此填 |

---

## 5. 还没就位的（等你 PDF 拿来后我落）

| 脚本 | 用途 | 阻塞点 |
|---|---|---|
| `scripts/algo_d/parsers/parse_national_protection_2021.py` | Step 1 PDF→JSON | 需要 1 份样本 PDF 看表格结构 |
| `scripts/algo_d/parsers/parse_hainan_protection_2024.py` | Step 2 PDF→JSON | 同上 |
| `scripts/algo_d/parsers/parse_china_red_list_2016.py` | Step 3 PDF→JSON | 同上 |
| `scripts/algo_d/parsers/parse_hj710_methods.py` | Step 4 PDF→章节 | 需要 1 份 HJ 710 样本（如 710.5 鸟类）看章节结构 |

写 parser 不在猜表格结构是因为：中国官方 PDF 表格变体很多（有的是文字流、有的是真表格、有的是图片型），猜错了等于白写。**只要你把 1 份样本 PDF 放进 `taxonomy_releases/taxonomy_full_release_2026_W2/_samples/` 我就能针对性写。**

---

## 6. 1505 vs 1369 问题的处置

| 选项 | 怎么做 | 影响 |
|---|---|---|
| **A（推荐）** | 把 W2 ingestion 落到 `taxonomy_full_release_2026_W2` 新 release，与 seed release 并存。catalog 表 `taxonomy_releases` 支持多 release，activate 切换。完成后 mainland_china birds 计数自然变成 1505 | 不动 seed manifest，不动 release_builder 硬编码，零回归 |
| B | 改 seed manifest 的 birds count 为 1505 | 误导 seed 包变成 full 包，长期负债 |
| C | 改 release_builder 硬编码 1505 → 1369 | 把 full backbone 阈值降到 seed 水位，违背"full = exhaustive"语义 |

走 A。

---

## 7. 验收门禁

| 门禁 | 通过条件 |
|---|---|
| **G1** Steps 1–4 落地 | 4 份 PDF 在 `taxonomy_releases/taxonomy_full_release_2026_W2/` 下，4 份 parsed.json 行数与官方数字严格一致 |
| **G2** Step 5 ingestion 成功 | `taxonomy_releases` 表里有 `taxonomy_full_release_2026_W2` 行、status=imported、is_current=False（候选） |
| **G3** Step 6 signature 完整 | manifest_signature 不为空，长度 = sha256 64 字符 |
| **G4** Step 7 行数验证 | `validate_pdf_to_json_row_counts.py` 退出码 0 |
| **G5** Step 7 启动日志 0 trim | uvicorn 启动日志 grep `"does not match"` 0 行 |
| **G6** 1505 校验通过 | release_builder validate 不抛 birds count 错误 |

---

## 8. 签字

- [ ] 算法 D：__________  日期：__________
- [ ] 工程师 B（taxonomy/catalog 维护）：__________  日期：__________
- [ ] 项目主管 / sponsor：__________  日期：__________
