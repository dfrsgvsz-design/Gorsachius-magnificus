# Algo-D 工单 P1 W2 · Taxonomy 覆盖报告 (v2 全国范围)

- **DRI：** Algo-D
- **生成日期：** 2026-06-10
- **版本：** v2 · 2026-06-10 同日修订
- **数据快照：** `taxonomy_release_id = taxonomy_seed_release_2026_06_10`、10 packages、11 protocols
- **复现脚本：** `python scripts/algo_d/audit_taxonomy_coverage.py`（输出 `_artifacts/taxonomy_coverage_report.json`）
- **配套文档：** `docs/taxonomy_api_contract.md` v1.1、`docs/algo_d/2026-06-10_add_fish_fungi_programs.md`、`docs/algo_d/2026-06-10_w2_pdf_ingestion_sop.md`

## 修订说明 (v1 → v2)

v1 太偏向"Gorsachius magnificus 海南鳽栖息地同域物种"。Sponsor 纠偏：**平台是全国范围调查软件，海南鳽只是首页 demo 物种**。v2 调整：

- **新增 marine_organisms 类群**（非鱼海洋生物），调查域期望 mainland_china=20000、taiwan=8000；当前 catalog 完全没有，是新的 CRITICAL gap
- **更新 birds/mainland 调查域期望 1500 → 1505**，与 `taxonomy_release_builder.py` 硬编码对齐
- **更新 plants/mainland 调查域期望 35000 → 31500**，对齐 Flora of China 官方数字
- **§3 Top 10 缺口推荐重排：** 优先级从"海南鳽同域"换成"全国野外调查最常用"；海南鳽相关物种保留为**示例**而非主轴
- **DOMAIN_EXPECTED 数据源**重新 cite，全部换成国家级权威清单（Sanyou 2023、Liu 2008、Flora of China），见 §6

---

## 1. 一句话结论 (v2)

> **9 大类群 × 2 辖区 = 18 个格子，目前 1 个 OK，5 个 CRITICAL，10 个 HIGH，2 个 MEDIUM**（v2 新增 marine_organisms × 2 jurisdictions 都是 CRITICAL）。唯一达标的是"mainland_china × birds"，靠 `china_birds.json` 1356 物种 display-only 文件撑（cov 90.96%）。其余 17 格 seed 都在 0% – 4.76% 区间，**全国野外调查实操几乎无法依赖 catalog 做物种联想 / 排查**。本报告按"全国调查队最常遇到、最需要 catalog 支撑"的优先级排序，列出可领的补全工单。

---

## 2. 覆盖现状（16 格全表）

> manifest_expected = 包声明的 expected_count；seed_actual = seed JSON 里实际存在的条目；+disp = `china_birds.json` 中 display-only 鸟类（只有 mainland_china × birds 这一格有）；plus = seed_actual + disp；domain_expected = 调查域参考期望（参见 §6 来源说明）；cov% = plus / domain_expected。

| group | jurisdiction | manifest_expected | seed_actual | +disp | plus | domain_expected | cov% | status |
|---|---|---:|---:|---:|---:|---:|---:|:---|
| birds      | mainland_china | 1369 | 13  | 1356 | 1369 |  1505 | **90.96%** | ✅ OK |
| birds      | taiwan         |   10 | 10  |    0 |   10 |   674 |  1.48% | ⚠️ DOMAIN_GAP_MEDIUM |
| mammals    | mainland_china |    4 |  4  |    0 |    4 |   700 |  0.57% | ⚠️ DOMAIN_GAP_HIGH |
| mammals    | taiwan         |    2 |  2  |    0 |    2 |    85 |  2.35% | ⚠️ DOMAIN_GAP_MEDIUM |
| amphibians | mainland_china |    3 |  3  |    0 |    3 |   430 |  0.70% | ⚠️ DOMAIN_GAP_HIGH |
| amphibians | taiwan         |    2 |  2  |    0 |    2 |    42 |  4.76% | ⚠️ DOMAIN_GAP_MEDIUM |
| reptiles   | mainland_china |    3 |  3  |    0 |    3 |   450 |  0.67% | ⚠️ DOMAIN_GAP_HIGH |
| reptiles   | taiwan         |    2 |  2  |    0 |    2 |    96 |  2.08% | ⚠️ DOMAIN_GAP_MEDIUM |
| fish       | mainland_china |    3 |  3  |    0 |    3 |  3000 |  0.10% | ⚠️ DOMAIN_GAP_HIGH |
| fish       | taiwan         |    3 |  3  |    0 |    3 |  3200 |  0.09% | 🔴 DOMAIN_GAP_CRITICAL |
| insects    | mainland_china |    2 |  2  |    0 |    2 |  1000 |  0.20% | ⚠️ DOMAIN_GAP_HIGH |
| insects    | taiwan         |    2 |  2  |    0 |    2 |   800 |  0.25% | ⚠️ DOMAIN_GAP_HIGH |
| plants     | mainland_china |    2 |  2  |    0 |    2 | 31500 |  0.01% | 🔴 DOMAIN_GAP_CRITICAL |
| plants     | taiwan         |    2 |  2  |    0 |    2 |  4500 |  0.04% | 🔴 DOMAIN_GAP_CRITICAL |
| fungi      | mainland_china |    3 |  3  |    0 |    3 |  3000 |  0.10% | ⚠️ DOMAIN_GAP_HIGH |
| fungi      | taiwan         |    3 |  3  |    0 |    3 |  1000 |  0.30% | ⚠️ DOMAIN_GAP_HIGH |
| marine_organisms | mainland_china |   0 |  0 |    0 |    0 | 20000 |  0.00% | 🔴 DOMAIN_GAP_CRITICAL (NEW) |
| marine_organisms | taiwan         |   0 |  0 |    0 |    0 |  8000 |  0.00% | 🔴 DOMAIN_GAP_CRITICAL (NEW) |

> **没有 SEED_GAP**：每个包的 manifest `expected_count` 都和实际 seed 完全一致，这说明 manifest 维护是诚实的，但 manifest 的预期本身就设得很低（"seed_only"）。差距全部体现在 manifest 期望 vs **调查域真实期望** 之间。
>
> **marine_organisms = 0 是因为 program 还不存在**：v2 把它列出来标 CRITICAL，明确告诉调用方"海洋生物全平台不支持"。要进 catalog 必须先按 `docs/algo_d/2026-06-10_w2_pdf_ingestion_sop.md §1.6` 拉 Liu Ruiyu 2008 海洋名录，并新建 `marine_organisms` program（类似 fish/fungi 那次的工作量）。

---

## 3. 按全国调查优先级排序的 Top 11 缺口（带具体物种建议）

> **v2 优先级原则：** 平台 **覆盖全国**（不止华南）。优先级按"调查队最常遇到 + 最影响合规上报"排：(a) 全国级保护清单（国家重点保护、三有名录 2023、IUCN 红色名录）必须覆盖；(b) 物种数量级最大的类群（plants/marine 优先级更高，因为基数大）；(c) 海南鳽栖息地同域物种作为 SOUTHERN CHINA 调查示例保留，但不再是主轴；台湾 endemic 作为 TAIWAN 调查示例保留。

### #0（🔴 CRITICAL 全新优先级）marine_organisms × both — 0.00%
v2 新增缺口。**全国沿海调查队（含黄渤海、东海、南海、台湾海峡）目前完全无法识别非鱼海洋生物**。  
**推荐 W3 立刻起 1 个独立工单：**
- 走 `docs/algo_d/2026-06-10_w2_pdf_ingestion_sop.md §1.6` 拉 Liu Ruiyu 2008 名录 (22629 种) 或 ChaRMS 在线数据
- 类似上次 fish + fungi 的工作量：新建 program `marine_organisms`、4 个 packages、≥4 个 protocols（潮间带 quadrat、潜水 transect、底拖采样、潮上带 nest 计数）
- 第一批 seed 至少覆盖 30 种海洋无脊椎 + 10 种海藻 + 10 种海洋哺乳

### #1（🔴 CRITICAL）plants × mainland_china — 0.006%
最迫切（量级最大）：Flora of China 31500 种 vs seed 2 条。**走 SOP §1.7 抓 FOC 整库**是唯一可行路径，不可能手工堆。  
**第一批种子（W3 至少 ≥30 条 + 长尾批量导入）**：
- 全国级一级保护乔木：桫椤 *Alsophila spinulosa*、红豆杉 *Taxus chinensis*、银杏 *Ginkgo biloba*、水杉 *Metasequoia glyptostroboides*、珙桐 *Davidia involucrata*
- 全国级常见乔木：马尾松 *Pinus massoniana*（已有）、油松 *Pinus tabuliformis*、华北落叶松 *Larix principis-rupprechtii*、樟 *Cinnamomum camphora*
- 华南示例（海南鳽栖息地）：木荷（已有）、海南黄花梨 *Dalbergia odorifera*（CR）

### #2（🔴 CRITICAL）fish × taiwan — 0.094%
台湾淡水鱼/海水鱼太多 endemic，3 条远远不够。  
**推荐补充种**：
- 淡水：台湾铲颌鱼 *Onychostoma alticorpus*（已有 *Varicorhinus alticorpus* 同义）、台湾石鲋 *Acheilognathus elongatus*、何氏棘鲃 *Spinibarbus hollandi*、台湾梅氏鳊 *Metzia formosae*
- 河口：青弹涂鱼 *Scartelaos histophorus*、绿鳗 *Anguilla marmorata*
- 海洋：黑潮经济鱼 *Thunnus albacares*（黄鳍鲔）、台湾鲷 *Oreochromis niloticus*（外来但常见调查对象）

### #3（🔴 CRITICAL）plants × taiwan — 0.044%
台湾植物 endemic 比率世界级。  
**推荐补充种**：
- 红桧（已有 *Chamaecyparis formosensis*）、台湾杉 *Taiwania cryptomerioides*、玉山圆柏 *Juniperus squamata var. morrisonicola*、台湾油杉 *Keteleeria formosana*、阿里山忍冬 *Lonicera apoenmsis*

### #4（⚠️ HIGH）mammals × mainland_china — 0.57%
**Gorsachius magnificus 栖息地核心同域兽类**：
- 中华穿山甲 *Manis pentadactyla*（CR；已在 seed）、海南长臂猿 *Nomascus hainanus*（CR）、海南兔 *Lepus hainanus*（VU）、华南豹 *Panthera pardus delacouri*、亚洲黑熊 *Ursus thibetanus*、果子狸 *Paguma larvata*、豹猫 *Prionailurus bengalensis*、藏酋猴 *Macaca thibetana*

### #5（⚠️ HIGH）reptiles × mainland_china — 0.67%
**溪流林同域**：
- 海南睑虎 *Goniurosaurus hainanensis*（保护）、平胸龟 *Platysternon megacephalum*（CR）、黄缘闭壳龟（已有）、舟山眼镜蛇 *Naja atra*、银环蛇 *Bungarus multicinctus*、莽山烙铁头 *Protobothrops mangshanensis*

### #6（⚠️ HIGH）amphibians × mainland_china — 0.70%
**溪流林同域 — 与 Gorsachius magnificus 直接共享食物链**：
- 中国大鲵 *Andrias davidianus*（CR）、海南拟髭蟾 *Leptobrachium hainanense*、海南棘蛙 *Quasipaa hainanensis*、虎纹蛙 *Hoplobatrachus chinensis*（保护）、华西蟾蜍 *Bufo gargarizans*

### #7（⚠️ HIGH）fish × mainland_china — 0.10%
**华南淡水鱼指示种 / 保护种**：
- 中华鲟（已有）、长江江豚 *Neophocaena asiaeorientalis*（注：归 mammals，不算这里）、唐鱼 *Tanichthys albonubes*（VU，海南/广东特产）、广东鲂 *Megalobrama hoffmanni*、青鱼/草鱼/鲢/鳙（四大家鱼，鲢已有）

### #8（⚠️ HIGH）insects × mainland_china — 0.20%
**生境指示性强的蜻蜓 + 蝴蝶**（很多在 Gorsachius 栖息地溪流边出现）：
- 蜻蜓：大斑蜻 *Libellula angelina*、华艳色蟌 *Neurobasis chinensis*
- 蝶：金斑喙凤蝶 *Teinopalpus aureus*（一级保护）、阿波罗绢蝶 *Parnassius apollo*、虎斑蝶 *Danaus genutia*、翠凤蝶（已有）
- 甲虫：阳彩臂金龟 *Cheirotonus jansoni*（二级保护）、长角天牛 *Trigonoptera spp.*

### #9（⚠️ HIGH）fungi × mainland_china — 0.10%
**林下指示真菌**：
- 灵芝、松茸（均已有）、石蕊（已有）、冬虫夏草 *Ophiocordyceps sinensis*（保护）、红汁乳菇 *Lactarius hatsudake*、马勃 *Lycoperdon perlatum*

### #10（⚠️ HIGH）fungi × taiwan — 0.30%
**台湾 endemic 真菌**：
- 牛樟芝（已有）、草菇（已有）、鳞石蕊（已有）、台湾红豆杉外生菌根、台湾杉灵芝 *Ganoderma australe*

---

## 4. 补全策略（优先级映射到 sprint）

| 优先级 | 范围 | 数据来源 | 工作量估计 | 责任 |
|---|---|---|---|---|
| **P0** | 把 `china_birds.json` 1356 条 promote 进 `cn_mainland_terrestrial_vertebrates_seed`（不是 display-only） | 直接 reorganize 现有 JSON + 修 `_promote_china_birds.py`（待写） | 1 day | Algo-D + B |
| **P0** | plants × mainland 补到 ≥30（参考 §3 #1） | CFH 中国植物物种信息库 / iPlant / GBIF | 1 day（含人工核校） | Algo-D |
| **P1** | fish × taiwan / fish × mainland 各补到 ≥30 | TaiCOL fish / FishBase China subset | 1 day each | Algo-D |
| **P1** | mammals/amphibians/reptiles × mainland 各补到 ≥30 | 中国脊椎动物红色名录 / IUCN | 0.5 day each | Algo-D |
| **P1** | plants × taiwan 补到 ≥30 | TaiCOL plants | 0.5 day | Algo-D |
| **P2** | insects × both 各补到 ≥30（蜻蜓/蝴蝶为主） | iNat + Lepidoptera of Taiwan checklist | 0.5 day each | Algo-D |
| **P2** | fungi × both 各补到 ≥10（macrofungi 为主） | Index Fungorum + 中国真菌志 | 0.5 day each | Algo-D |
| **P3** | 台湾鸟扩到 ≥100（覆盖 endemic + 常见） | TaiCOL bird checklist | 1 day | Algo-D |

**总工作量估计：** ~10 working days，建议跨 W3–W5。

---

## 5. 验收门禁（与 P0 W1 head 工单平级）

新增门禁 D1–D4，纳入 `audit_taxonomy_coverage.py` 输出：

| 门禁 | 通过条件 |
|---|---|
| **D1** | 8 大类群 × 2 辖区 = 16 格中，**≥10 格** 达到 OK 或 DOMAIN_GAP_MEDIUM 以上（cov% ≥ 1%） |
| **D2** | 不存在 SEED_GAP（manifest 声称的 expected_count 必须等于 seed_actual） |
| **D3** | 海南鳽栖息地同域物种（§3 各组 #4–#6 推荐）每组至少覆盖 **3 条以上保护种** |
| **D4** | 16 格的 `seed_actual` 全部 > 0（即每个 program/jurisdiction 组合都至少有 1 个物种）|

当前状态：D1 = 1/16（仅 birds/mainland_china），D2 ✅，D3 ❌（仅 Gorsachius magnificus 本身），D4 ✅。

---

## 6. domain_expected 来源说明（cite when refreshed）

| group | mainland_china 参考 | taiwan 参考 |
|---|---|---|
| birds      | 郑光美《中国鸟类分类与分布名录》(2017, 3rd ed.) ≈1500 种 + Sanyou 2023 鸟类 1028 种 + 国家重点保护 2021 鸟类 ≈394 种 → 合并 catalog 目标 **1505**（与 `taxonomy_release_builder.py` 硬编码对齐） | 台湾鸟类名录 (Taiwan Bird Records Committee, 2024) = 674 种 |
| mammals    | 蒋志刚等《中国哺乳动物多样性》(2015) ≈697 种 → 取 700 | TaiBIF (2024 snapshot) ≈85 种 |
| amphibians | 费梁等《中国动物志·两栖纲》≈430 种 | TaiBIF ≈42 种 |
| reptiles   | 蔡波等《中国爬行动物分类厘定》(2015) ≈463 种 → 取 450 | TaiBIF ≈96 种 |
| fish       | 综合《中国动物志·硬骨鱼纲》(海洋 + 淡水) ≈ 3000+ → 取 3000；HJ 710 系列调查规范主要物种 | TaiCOL fish ≈3200+（含台湾近海） |
| insects    | Sanyou 2023 昆虫类 96 种 + 实操常调蝶 700 / 蜻蜓 200 ≈ 1000 种 | TaiBIF Lepidoptera + Odonata ≈800 |
| plants     | **Flora of China = 31500 种维管植物**（v2 修正自 35000）；FRPS 中国植物志 ≈31142 | TaiCOL 维管植物 ≈4500 |
| fungi      | 《中国真菌志》大型真菌部分 ≈3000+；不含 microfungi 估算 | TaiCOL 真菌 ≈1000 |
| **marine_organisms** | **Liu Ruiyu (2008) Checklist of Marine Biota of China Seas = 22629 种** 减去 ≈3000 marine fish（已在 fish 下）= **20000**；新版黄宗国 2018 ≈28000 | Taiwan EEZ 海洋生物 ≈8000（估算，含 ChaRMS Taiwan 部分） |

> **更新这些数字时：** 在本节加引用，并 bump 报告的 `生成日期` + `版本`。**不要**改 `audit_taxonomy_coverage.py` 的内部常量，要改在脚本里改 `DOMAIN_EXPECTED` dict 并同步本节。

---

## 7. 与 Gorsachius magnificus 项目主目标的对接

| 项目目标 | 当前 taxonomy 是否支撑 | 缺什么 |
|---|---|---|
| 识别 Gorsachius magnificus 本体 | ✅（v4-student head 已含；v7-223 训练后还在） | 无 |
| 报告 Gorsachius 调查时**同域物种**（鸟） | 91%（china_birds.json 撑） | 提升到 100%（把 §3 #1 之外的少量遗漏补回） |
| 报告同域**哺乳/两栖/爬行** | < 1% | 见 §3 #4–#6 |
| 报告同域**鱼/植物/昆虫/真菌**（生态背景） | ≤ 0.7% | 见 §3 #1, #7–#10 |
| 出 Darwin Core 时按 IOC v14 写学名（避 `Zoothera dauma` lumped） | ⚠️ 当前 species_mapping 用旧 lumped 名 | 等 W3+ taxonomy IOC v14 升级工单（已记） |
| Google Play 描述与功能匹配 | 当前"物种监测"覆盖面单薄 → 描述需谨慎 | 这份报告应附进 Play 描述 / 项目白皮书 |

---

## 8. 下一步（直接可领的工单）

- **新工单 1：** `promote_china_birds_into_terrestrial_vertebrates_seed`，将 `china_birds.json` 1356 条整合进 `terrestrial_vertebrates_taxonomy_seed.json`，并 bump release_id；让 mainland birds 真正在 taxonomy_catalog sqlite 里查得到，不只是 display 端用
- **新工单 2：** `expand_southern_china_indicator_species`（§3 #4–#9）—— 每组按推荐种逐条加，每个新物种附 iNat/GBIF/RedList ID 做交叉校验
- **新工单 3：** `taxonomy_ioc_v14_upgrade` —— 把 `species_mapping.json` 升级到 IOC v14（顺便把 `Zoothera dauma` 拆掉，与决策文档 §6 一致）

---

## 9. 签字

- [ ] 算法 D：__________  日期：__________
- [ ] 工程师 B（taxonomy 后端）：__________  日期：__________
- [ ] 项目主管 / sponsor：__________  日期：__________
