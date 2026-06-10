# 发布执行手册（D-Day）

## 1. 预检查

- 在仓库根目录执行：`powershell -ExecutionPolicy Bypass -File scripts/release_gate.ps1`
- 确认全部显示 `[PASS]` 且最后为 `ALL PASS`
- 确认 `submission/03_missing_required_business_inputs.md` 中必填项已补齐

## 2. 生产环境变量

### species_monitoring_platform

- 复制：`species_monitoring_platform/frontend/.env.production.example` -> `.env.production`
- 必填：`VITE_API_BASE_URL=https://<正式后端域名>`
- 可选：`VITE_PILOT_MODE=false`

### acoustic_platform

- 复制：`acoustic_platform/frontend/.env.production.example` -> `.env.production`
- 必填：`VITE_API_BASE_URL=https://<正式后端域名>`
- 可选：`VITE_PILOT_MODE=false`

## 3. 前端打包

### species_monitoring_platform

- `cd species_monitoring_platform/frontend`
- `npm run build`
- Android 同步：`npm run build:android`

### acoustic_platform

- `cd acoustic_platform/frontend`
- `npm run build`
- Android 同步：`npm run build:android`

## 4. Android 提测

> 签名材料、环境变量、版本号规则详见 `06_packaging_signing_runbook.md`。

- 注入 4 个 `ANDROID_KEYSTORE_*` 签名环境变量（值取自保险库）
- `cd frontend\android` 后执行：`.\gradlew.bat bundleRelease assembleRelease`
- 产物：`app-release.aab`（上传 Play Console 内测轨道）+ `app-release.apk`（真机回归）
- 归档同目录 `mapping.txt`（崩溃反混淆必需）
- CI 替代路径：打 tag `v*` 触发 `.github/workflows/android-release.yml` 一键出包

## 5. 回滚方案

- 前端回滚：回退到上一个通过闸门的构建产物与 Git 提交
- 后端回滚：回退部署镜像到上一个稳定 tag
- 回滚后立即执行 `scripts/release_gate.ps1` 验证恢复状态

## 6. 上线放行条件（硬门槛）

- P0 问题数 = 0
- 两个前端构建通过
- 两个后端 `tests.test_health_runtime` 通过
- 提审材料（`submission/01` 与 `submission/02`）完成填写
