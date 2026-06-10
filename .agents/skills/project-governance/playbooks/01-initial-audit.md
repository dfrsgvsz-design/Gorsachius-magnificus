# Playbook 01 · 接手项目的初始审计（24h 套路）

> PM 接到一个新项目（或被叫去救火），照下面 6 步走，4–6 小时出第一份审计报告。

## Step 1 · 扫仓库结构（30 min）

```bash
# Windows PowerShell
Get-ChildItem -Force | Select-Object Mode, Name, Length | Format-Table -AutoSize

# 或者跨平台
ls -la
```

只读 4 类文件，不读代码：
- `README.md` / `AGENTS.md` / 项目级 doc
- `submission/*` 或类似的"提审/上线"文件夹
- `scripts/*.ps1` `*.sh` —— 看 release_gate / quality_gate 是否存在
- 最近 7 天的 `*.log` 文件 —— 一手运行证据

## Step 2 · 读关键日志（30 min）

```bash
# 找最近 7 天日志
Get-ChildItem -Filter *.log -Recurse | Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-7) }
```

读法：**先读结尾 200 行**，再倒查 ERROR / WARNING / 503 / 404 / Traceback。

```bash
# 看错误
Select-String -Path "*.log" -Pattern "ERROR|WARNING|503|Traceback|Exception" -Context 0,2
```

把每个独立的错误整理成 **「错误类型 — 频率 — 影响面」** 三列表。

## Step 3 · 识别 P0/P1/P2（60 min）

按下表归类每个发现：

| 等级 | 定义 | 例子 |
|---|---|---|
| **P0** | 阻塞上线 / 阻塞测试 / 阻塞演示 | 后端 503、签名不全、API 契约破裂 |
| **P1** | 不阻塞但影响审核通过率 / 用户体验 | 商店素材缺、权限文案差、demo 模式警告 |
| **P2** | 技术债 / 体验抛光 / 长期演进 | 重复代码、未清理临时文件、磁盘冗余 |

输出表格：

```markdown
| ID | 等级 | 模块 | 现象 | 证据 | 推荐 DRI |
|---|---|---|---|---|---|
| #01 | P0 | backend | demo 模式启动 | log L15 | A |
| #02 | P0 | api | taxonomy/search 422 | log L43 | A |
| #03 | P1 | frontend | 三大核心 35% | refactor_progress | B |
| ... | ... | ... | ... | ... | ... |
```

## Step 4 · 摸清"上不了线的根因"（45 min）

不要只看错误，要分类成 3 桶：

1. **工程根因**（quality_gate fail / API 契约破裂 / 部署只能 demo）
2. **产品根因**（核心功能未完成 / UX 卡点）
3. **业务根因**（隐私 URL / 商店素材 / 审核账号 / 主体资质）

每桶最多 3 条，控制叙述层级，避免清单膨胀。

## Step 5 · 出审计报告（60 min）

固定 7 段结构：

```markdown
# <项目名> · 初始审计报告

## 一、平台全景（你要知道的事实）
- 仓库结构表
- 上线姿态：工程可部署度 / 用户功能交付度 / 业务合规度（三个 %）

## 二、为什么不能落地（按影响降序）
### P0 工程红线（X 条）
### P1 产品红线（X 条）
### P1 业务红线（X 条）
### 已具备、不要重复造（避免浪费）

## 三、落地路线图（4–8 周冲刺 + 条件性补充）
| 周次 | 里程碑 | 交付物 | 出口标准 |

## 四、团队配置（4±1）
| 工号 | 角色 | 技术栈 | 本项目焦点 |

## 五、四份正式工单（按 §9 七字段结构）
### 工单 #A
### 工单 #B
### 工单 #C
### 工单 #D
### 工单 #E

## 六、PM 自留事项
按周分解 PM 自己要做的事

## 七、最后一句话给团队
1–2 句话点出团队此刻的核心矛盾，激发使命感
```

## Step 6 · 启动会（120 min）

```
Hour 0-15: PM 全员宣读审计报告关键 3 张表
Hour 15-60: 每人复述自己工单（每人 5 min），PM 当场答疑
Hour 60-90: 协商 W1 末闸门标准，全员签字
Hour 90-105: PM 现场创建 governance 目录与 RAID Log 初稿
Hour 105-120: 拍板 1on1 时段、日报截止时刻、周会时段
```

## 第一天产物清单（PM 必交）

- [ ] `<项目名>_initial_audit_report.md`
- [ ] `submission/governance/01_reporting_protocol.md`
- [ ] `submission/governance/raid_log.md`（含 ≥10 条预热风险）
- [ ] `submission/governance/decision_log.md`（含 ≥3 条 Day 1 决策）
- [ ] `submission/governance/readiness_scorecard.md`（W1 基线值）
- [ ] 5 份工单（A/B/C/D/E）
- [ ] sponsor 一页纸（含 4 件需拍板事项）

## 红线

- **不读源码、不修代码** —— 不是你的工作
- **不许超 8 小时还没出审计报告** —— 信息饱和度足够，决断不能再拖
- **任何"等我再确认一下"超 30 分钟 = 决断 + 写入 D-NN**
- **审计不写"我感觉"** —— 全文必须可溯源到文件/日志/commit
