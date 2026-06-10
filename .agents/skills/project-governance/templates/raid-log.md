# RAID Log 模板（风险 / 假设 / 议题 / 依赖）

> 路径：`submission/governance/raid_log.md`（公共可读）
> PM 拥有写入权，每次周会逐条刷新。

## 四类条目

| 类别 | 缩写 | 定义 |
|---|---|---|
| Risk | R | 还没发生但可能发生的坏事 |
| Assumption | A | 现在判断的依据，若不成立项目方向就变 |
| Issue | I | 已发生、正在影响项目的事 |
| Dependency | D | 我们需要别人/别系统做的事 |

每条编号格式：`<类别>-NN`，例如 `R-01`、`I-03`。

## 主表格式

```markdown
| ID | 类别 | 标题 | 严重度 | 概率 | 触发指标 | DRI | 响应预案 | 状态 | 最后更新 |
|---|---|---|---|---|---|---|---|---|---|
| R-01 | Risk | Apple Developer 注册 D-U-N-S 延期 | High | Med | 注册超 14 天未通过 | E | 切换为个人开发者主体（限期 3 天决断） | OPEN | 2026-05-02 |
| R-02 | Risk | 后端 demo 模式上线被审核打回 | High | High | release_gate 不绿 | A | W2 末必须切生产模式 | OPEN | 2026-05-02 |
| A-01 | Assumption | 业务方决定上 iOS | Med | High | sponsor W1 末口头确认 | PM | 不上则释放 30% 人力 | OPEN | 2026-05-02 |
| I-01 | Issue | taxonomy/search 422 持续报错 | High | - | 已发生 | A | A 工号 W1 内修复 | OPEN | 2026-05-02 |
| D-01 | Dependency | 业务方提供测试账号 | High | - | E 工号每日跟进 | E | 超 72h 未给则 PM 直接 escalate sponsor | OPEN | 2026-05-02 |
```

## 严重度 × 概率 矩阵（PM 加权）

| 概率\严重 | Low | Med | High |
|---|---|---|---|
| **Low** | 监控 | 监控 | 周看一次 |
| **Med** | 监控 | 周看 | 周会必谈 + 写预案 |
| **High** | 周看 | 周会必谈 + 写预案 | **闸门必查 + 升级触发器** |

## 条目生命周期

```
NEW ─► OPEN ─► MITIGATING ─► RESOLVED ─► CLOSED
                  │
                  └─► ESCALATED （转 ESC-NNN）
```

每条状态变化必须在该行注释：
```
| R-01 | ... | OPEN→MITIGATING 2026-05-05: E 已发起 D-U-N-S 走加急通道 |
```

## 初始 15 条预热风险（接管项目第一天即填入）

```markdown
| R-01 | Risk | Apple Developer 注册延期 | High | Med | 注册超 14 天 | E | 切个人主体 | OPEN |
| R-02 | Risk | 后端 demo 模式被打回 | High | High | release_gate 不绿 | A | W2 末切生产 | OPEN |
| R-03 | Risk | 商店素材交付延期 | Med | High | W2 末未集齐 4 张截图 | E | PM 调线下设计资源 | OPEN |
| R-04 | Risk | Android 14 前台服务被打回 | High | Med | Play 政策更新 | B | 提交场景视频 | OPEN |
| R-05 | Risk | 物种 mapping ↔ checkpoint 不一致 | High | High | 已存在 | D | W1 内三选一收敛 | OPEN |
| R-06 | Risk | 隐私政策法务审核反复 | Med | Med | 草稿 2 轮未签 | E | 排"准 OK"版上线，后续微调 | OPEN |
| R-07 | Risk | 签名口令磁盘残留 | High | Low | KEYSTORE_INFO.txt 仍存盘 | C | W1 内 vault 化 | OPEN |
| R-08 | Risk | CI 额度不够 | Med | Med | Actions 分钟数月底见底 | C | 升级账户或买分钟 | OPEN |
| R-09 | Risk | 双 App 被审核员问"区别" | Med | High | 上架时 | PM | 一份"差异说明"提前准备 | OPEN |
| R-10 | Risk | 用户数据迁移失败 | High | Low | 升级后日志报错 | A | 准备回滚 DDL | OPEN |
| A-01 | Assumption | 上 iOS | Med | High | sponsor 决断 | PM | 不上则释人 | OPEN |
| A-02 | Assumption | 国内 Android 也上 | Med | High | sponsor 决断 | PM | 决定是否需 ICP | OPEN |
| D-01 | Dependency | 业务方测试账号 | High | - | E 每日跟进 | E | 超 72h escalate | OPEN |
| D-02 | Dependency | 隐私 URL 公网部署 | High | - | E 每周跟进 | E | PM 出 SOP | OPEN |
| D-03 | Dependency | 生产域名 + HTTPS | High | - | A 每周跟进 | A | W2 末必须可达 | OPEN |
```

## 红线

- **每条必须有 DRI**，"团队"不算
- **每条必须有触发指标**，"可能"、"或许"不算
- **每条必须有响应预案**，否则不算 OPEN
- **超 4 周未变化的 OPEN 条** PM 必须主动关闭或重排
