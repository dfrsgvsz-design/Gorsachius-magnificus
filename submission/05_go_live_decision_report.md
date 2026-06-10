# 上线决策报告（当前轮）

## 结论

- 决策：**条件上线（可提测）**
- 当前技术状态：主链路构建与运行闸门已通过
- 生效前提：补齐业务与合规必填信息后再提审

## 技术验收结果

- 发布闸门：`scripts/release_gate.ps1` 通过
- Python 语法：通过（仓库主范围无错误）
- 后端运行测试：
  - `species_monitoring_platform/backend` 通过
  - `acoustic_platform/backend` 通过
- 前端构建：
  - `species_monitoring_platform/frontend` 通过
  - `acoustic_platform/frontend` 通过

## 已具备的上线资产

- 提审清单：`submission/01_android_ios_submission_checklist.md`
- 材料模板：`submission/02_submission_material_template.md`
- 缺失信息清单：`submission/03_missing_required_business_inputs.md`
- 发布执行手册：`submission/04_release_execution_runbook.md`
- 一键闸门脚本：`scripts/release_gate.ps1`
- 生产环境模板：
  - `species_monitoring_platform/frontend/.env.production.example`
  - `acoustic_platform/frontend/.env.production.example`

## 剩余动作（上线前必须完成）

1. 业务提供审核测试账号与可访问环境
2. 补齐隐私政策 / 用户协议公网地址
3. 补齐商店素材（图标、截图、介绍文案）
4. 配置生产 `VITE_API_BASE_URL` 并完成 Android Release AAB 打包
5. 若上 iOS，补齐 iOS 工程与 `Info.plist` 权限说明

## 负责人建议

- 技术负责人：执行 `release_gate.ps1` 并锁定候选版本
- 产品/运营：补齐商店与审核材料
- 法务/合规：确认隐私与数据处理文本
- 发布工程：完成签名、提审、灰度放量与回滚预案
