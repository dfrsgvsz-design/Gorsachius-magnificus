# L4 闸门决策报告模板

> 路径：`submission/reports/gates/gate_W<n>_decision.md`
> 当且仅当本报告通过双签（PM + sponsor）后，才允许进入下一阶段。

```markdown
# Gate W<n> Decision Report

- 评审时间: 2026-MM-DD HH:MM
- 评审范围: <里程碑名，例如：W2 生产就绪度闸门>
- 主持: <PM 名>
- 出席: <PM> + <sponsor> + A/B/C/D/E

## 9 项打分（任何一项为 🔴 即 no-go）

| # | 维度 | 检查项 | 状态 | 证据链接 |
|---|---|---|---|---|
| 1 | P0 缺陷数 | = 0 | 🟢/🟡/🔴 | <issue tracker 链接> |
| 2 | release_gate | ALL PASS | 🟢/🟡/🔴 | <CI run 链接> |
| 3 | E2E 核心路径 | 全绿 | 🟢/🟡/🔴 | <Playwright run 链接> |
| 4 | 生产健康 | 24h 99% 200 | 🟢/🟡/🔴 | <监控截图> |
| 5 | 签名材料 | vault 化、磁盘 0 残留 | 🟢/🟡/🔴 | <vault 路径> |
| 6 | 商店素材 | 100% 集齐 | 🟢/🟡/🔴 | `submission/store_assets/` |
| 7 | 审核账号 | 24h 可达 | 🟢/🟡/🔴 | <测试账号文档> |
| 8 | 回滚演练 | 完成 1 次 | 🟢/🟡/🔴 | <演练记录> |
| 9 | 崩溃监控 | mapping 归档 | 🟢/🟡/🔴 | <监控后台> |

## 决策

- [ ] GO（全部 🟢）
- [ ] CONDITIONAL GO（全部 🟢 + ≤2 项 🟡 + 有明确补救计划）
- [ ] NO-GO（任意 🔴）

## 决策依据

<3–5 句话，必须可量化、可追溯>

## 补救计划（CONDITIONAL GO / NO-GO 时必填）

| 项 | 补救动作 | DRI | 截止 |
|---|---|---|---|
| ... | ... | ... | ... |

## 下次复评时间

YYYY-MM-DD HH:MM

## 双签

- PM: <签名> · <日期>
- Sponsor: <签名> · <日期>
```

## 闸门触发时机（本项目专用）

| 闸门 | 时点 | 重点 |
|---|---|---|
| Gate W1 | W1 末（周五）| 工程红线归零：quality_gate / release_gate 全绿、API 契约稳定 |
| Gate W2 | W2 末 | 生产就绪：后端域名 24h 可达、三大核心 E2E 全绿 |
| Gate W3 | W3 末 | 商店就绪：素材包 100%、审核账号到位、内测包可装 |
| Gate W4 | W4 末 | 提审：AAB 签名、mapping、商店后台填写归零 |
| Gate iOS-T | iOS TestFlight 前 | Apple 账号 + Mac + Pod 链路全通 |
| Gate iOS-P | iOS 提审前 | TestFlight 外测 Beta 审核通过 |

## PM 在闸门会上的角色

- **绝不替队员回答** —— 让 DRI 自己解释证据
- **任何无证据的 🟢 当场降为 🟡**
- **CONDITIONAL GO 的补救计划必须在会上写完** —— 不许"会后补"
- **NO-GO 不算失败** —— 算"少坑了一次用户"，鼓励早报
