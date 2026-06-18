# 签名与打包 Runbook（species_monitoring_platform）

> 目标读者：负责出包/上架的工程师。覆盖 Android 签名出包（本地 + CI）、版本号规则、R8 混淆、iOS 工程与 TestFlight 计划。

## 1) 签名材料（红线）

| 项 | 值 |
|---|---|
| Keystore 文件 | `C:\Users\Administrator\.keystores\species-monitoring\species-monitoring-release.jks`（仓库外） |
| 类型 / 算法 | PKCS12 / RSA 2048 |
| 有效期 | 10000 天（2026-06-10 → 2053-10-26，≥ 25 年） |
| 别名 | `speciesmonitoring-release` |
| 证书 SHA256 | `CA:D0:C1:41:E2:75:21:6D:B2:84:18:58:FF:A0:FC:E6:1E:16:9C:E5:B3:FB:73:3B:0E:95:9B:7D:BF:A7:37:3E` |
| 口令 | **仅存于企业密码管理器（Vault），严禁落地磁盘。** 从 Vault 条目 `Species Monitoring / Android Release Keystore` 取出。条目结构与迁移流程见 §1.1。 |

红线规则：

- keystore、口令、`release-signing.env`、任何含明文口令的文件 **严禁提交进仓库**。根 + species `.gitignore` 已拦截 `*.jks/*.keystore/*.p12/keystore.properties/release-signing.env/KEYSTORE_INFO.txt`。
- **`KEYSTORE_INFO.txt` 已永久退役**（2026-06-10，工单 #C P0 W2）。该文件曾用于本地暂存口令，现已删除并禁止再生成；任何文档不得再引用它。
- keystore 丢失 = Play 上架主体丢失（除非启用 Play App Signing 托管）。**强烈建议首发即启用 Play App Signing**，本地 keystore 降级为 upload key，正式签名密钥由 Google 托管。详见 §2.1。
- 备份要求：Vault 1 份 + 离线介质 1 份；口令与文件分开存放；离线介质收存于物理保险柜并登记。
- 本地校验工具：`scripts/verify_signing_env.ps1`（从环境变量读取并校验 4 个 `ANDROID_KEYSTORE_*`，不打印口令本身）。

## 1.1) 保险库（Vault）存储结构与迁移流程

> **强制要求（工单 #C P0 W2）**：所有签名口令必须仅存于企业密码管理器（1Password、Bitwarden、HashiCorp Vault 或同等级 SOC2 认证产品）。磁盘上的 `KEYSTORE_INFO.txt`、`release-signing.env` 等明文口令文件已禁用。

### Vault 条目结构（固定）

| 字段 | 值 | 备注 |
|---|---|---|
| 条目名（Title） | `Species Monitoring / Android Release Keystore` | 全字符串严格固定，工具脚本据此查找 |
| 类别 | API Credential / Secure Note | 不要存为 Login 类型 |
| 字段 `ANDROID_KEYSTORE_FILE` | `C:\Users\Administrator\.keystores\species-monitoring\species-monitoring-release.jks` | 路径常量，跨机器复用时按 §3 注入时覆盖 |
| 字段 `ANDROID_KEYSTORE_PASSWORD` | `<明文口令>` | **必须 Concealed/Password 类型字段** |
| 字段 `ANDROID_KEY_ALIAS` | `speciesmonitoring-release` | |
| 字段 `ANDROID_KEY_PASSWORD` | `<明文口令>` | 与 keystore 口令相同（PKCS12 类型一致） |
| 字段 `KEYSTORE_SHA256` | `CA:D0:C1:41:E2:75:21:6D:B2:84:18:58:FF:A0:FC:E6:1E:16:9C:E5:B3:FB:73:3B:0E:95:9B:7D:BF:A7:37:3E` | 供 §2.1 Play App Signing 启用校对 |
| 附件 | `species-monitoring-release.jks` | 可选；同时本地保留一份并设置 NTFS ACL 仅本人可读 |
| 备注 | "10000 天有效期至 2053-10-26；丢失=Play 主体丢失（除非已启用 Play App Signing）；启用 Play App Signing 后此条目降级为 upload key 对应物" | |

### 一次性迁移 checklist（曾经持有 `KEYSTORE_INFO.txt` 的机器）

完成下列每一步后在本 PR 评论 / Linear 工单 #C 回执打勾：

- [ ] 已新建上表所示 Vault 条目，4 个 `ANDROID_KEYSTORE_*` 字段值与历史 `KEYSTORE_INFO.txt` 一致。
- [ ] 已在 Vault 条目"分享给"列表中加上：运维负责人 + 安全负责人 + 应用上架人（至少 3 人；防止单人离职导致密钥孤儿）。
- [ ] 已在物理保险柜中放置 1 份离线介质（U 盘）备份；介质上**仅**含 keystore 文件，**不**含口令；登记编号 + 入柜日期。
- [ ] 已彻底删除磁盘上所有历史 `KEYSTORE_INFO.txt`：
      ```powershell
      Get-ChildItem -Path "C:\","D:\","F:\" -Recurse -Force -Filter "KEYSTORE_INFO.txt" -ErrorAction SilentlyContinue | ForEach-Object { Remove-Item $_.FullName -Force; Write-Host "Removed: $($_.FullName)" }
      ```
- [ ] 已在所有出包工作机执行 `scripts/verify_signing_env.ps1`，确认能从环境变量正确读出 keystore 文件 + alias + 口令哈希校验通过。
- [ ] 已 grep 项目目录确认无任何**活跃引用** —— 命令：
      ```powershell
      rg -n "KEYSTORE_INFO" --glob '!node_modules' --glob '!.gitignore' --glob '!*.gitignore' "f:\Gorsachius magnificus"
      ```
      预期：**所有匹配仅来自本文档（`submission/06_packaging_signing_runbook.md` §1 红线规则和 §1.1 迁移指南）**，无其他文件引用。
      若 `quality_gate.ps1` / `release_gate.ps1` / `.github/workflows/*.yml` / `submission/04_release_execution_runbook.md` 等任何其他文件出现命中，按要求清除并把当前条目 unchecked。

### 日常取用流程（每次本地出包前）

```powershell
# 1. 从 Vault 取值（以 1Password CLI 为例；Bitwarden 用 `bw get item` 同理）
$item = "Species Monitoring / Android Release Keystore"
$env:ANDROID_KEYSTORE_FILE     = op read "op://Production/$item/ANDROID_KEYSTORE_FILE"
$env:ANDROID_KEYSTORE_PASSWORD = op read "op://Production/$item/ANDROID_KEYSTORE_PASSWORD"
$env:ANDROID_KEY_ALIAS         = op read "op://Production/$item/ANDROID_KEY_ALIAS"
$env:ANDROID_KEY_PASSWORD      = op read "op://Production/$item/ANDROID_KEY_PASSWORD"

# 2. 本地校验：环境变量齐全 + keystore 可读 + alias 与 SHA256 匹配
powershell -ExecutionPolicy Bypass -File "f:\Gorsachius magnificus\scripts\verify_signing_env.ps1"

# 3. 通过后进 §3 出包流程
```

口令在 shell 结束 / 屏锁后即失效；**严禁** `Set-Content` 写入文件或 `git add` 任何含口令的临时文件。

## 2) 包名与版本号（定版）

- `applicationId / bundleId`：`org.biodiversity.speciesmonitoring`（Android / iOS 已统一；历史文档中的 `org.biodiversity.fieldsurvey` 已废弃）。
- 当前版本：`versionName 1.0.0` / `versionCode 10000`；iOS `MARKETING_VERSION 1.0.0` / `CURRENT_PROJECT_VERSION 10000`。
- **递增规则**：`versionCode = major×10000 + minor×100 + patch`
  - `1.0.1` → 10001；`1.2.0` → 10200；`2.0.0` → 20000。
  - 每次提审 versionCode 必须严格递增；iOS build number 与 versionCode 同步取值。
- 修改位置：
  - Android：`frontend/android/app/build.gradle` → `versionCode` / `versionName`
  - iOS：`frontend/ios/App/App.xcodeproj/project.pbxproj` → `CURRENT_PROJECT_VERSION` / `MARKETING_VERSION`

## 2.1) Play App Signing 启用 SOP（强烈建议首发即启用）

### 为什么要启用

- Google 托管正式（production）签名密钥，本地 keystore 降级为 **upload key**。
- 后果：upload key 丢失/泄露可申请重置（48h SLA），主体不丢；本地 keystore 丢失也**不再等于上架主体丢失**。
- 一旦启用**不可关闭**（这是 Google 的策略），所以决策点在第 1 步。

### PM 版 4 步指底（双签模板）

面向 PM 的启用 checklist 独立一份：[`docs/release_b/play_app_signing_4_steps.md`](../docs/release_b/play_app_signing_4_steps.md)（B 起草，顶部有工程与 PM 双签表 + 不可逆警告 + DRI B 预备动作 + 4 步 PM 活动 + 发布后 checklist）。

本节下面的 4 步表是"工程侧技术接入"视角，与 B 的文档互补：B 里重点是"PM 拍谁、什么时候不能后悔"；本节重点是"engineering 供货什么 + 下游怎么接受 SHA 变更"。两者都看。

### 启用流程（4 步，每步附验收）

| # | 动作 | 在哪里做 | 验收信号 |
|---|---|---|---|
| 1 | 在 Play Console 进入 **应用 → 设置 → 应用完整性 → 应用签名**，点击"使用 Play 应用签名"，选择"导出并上传与 Play 不同的密钥" → 实际上选"使用 Play 生成的密钥"（推荐：让 Google 全权管） | Play Console | 页面状态变为"已启用 Play App Signing"；可看到"Google 生成的应用签名密钥"区块 |
| 2 | Play Console 下载 **upload certificate template**，用本地 keystore 出一次 AAB（按 §3）并上传到内部测试轨道；Google 接管签名 | Play Console + 本地 §3 | 内测轨道页面显示版本号已通过签名验证；"应用签名密钥"和"上传密钥"两个 SHA256 都已展示 |
| 3 | 在 **应用完整性 → 应用签名** 页面截图保存以下 4 个值：<br/>① 应用签名密钥（Google 托管）SHA-1<br/>② 应用签名密钥 SHA-256<br/>③ 上传密钥（本地 keystore）SHA-1<br/>④ 上传密钥 SHA-256 | Play Console | 4 个值复制保存 |
| 4 | 把步骤 3 的 4 个 SHA 填进 `submission/PLAY_APP_SIGNING_SHA.md`（C 已留空模板）的 §1 / §2，按该表 §3 把"应用签名密钥 SHA"切换到所有依赖 SHA 校验的下游平台（Firebase、Maps API、第三方登录、推送、统计 SDK 等）。**注意第三方平台原本登记的本地 keystore SHA 现在变成了"upload key SHA"，必须替换为 Google 签名 SHA，否则线上 OAuth / Maps / 推送 / 分享会全部失败。** 完成后按 `PLAY_APP_SIGNING_SHA.md` §4 做端到端冒烟。 | 本仓 + 第三方平台 | `PLAY_APP_SIGNING_SHA.md` §0 全部 ✅，§3 各平台均打勾 + 验证通过 |

### 启用后本仓出包流程的变化

**完全无变化**——本仓继续按 §3 / §6 用 upload key 出 AAB，Google 在分发时换签。但要点：

- 本地校验签名时（`jarsigner -verify`），看到的是 upload key 的签名；Play 上线后看到的是 Google 应用签名密钥 —— 两者 SHA 不同**是预期**。
- `frontend/android/app/build.gradle` 中的 `signingConfigs.release` **不要改动**——它继续指向 upload key（即原 keystore）。
- 用户首次安装 / 升级时，Android PackageManager 校验的是 Google 应用签名密钥，故旧版本（启用 Play App Signing 之前发布的）**用户必须从 Play 拉取的版本升级**，不能用本地 sideload APK 直接覆盖（签名不匹配）。

### 失败回退路径

- 步骤 2 上传失败（"密钥不匹配"）：通常是 base64 编码污染（CRLF/BOM 串入）；按 §6 的 `[Convert]::ToBase64String` 命令重新生成。
- 启用后想撤回：**不可能**。Play App Signing 是一次性单向操作。决策前请与上级 + 安全双签。
- 第三方 SHA 替换遗漏：用户报"登录后白屏"/"地图不显示" → 立即检查 Firebase / Google Cloud Console / 微信开放平台等是否还在用旧 SHA。

## 3) 本地出包（Windows）

```powershell
# 0. 一次性：注入签名环境变量（值取自保险库，勿写入文件）
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
$env:ANDROID_KEYSTORE_FILE     = 'C:\Users\Administrator\.keystores\species-monitoring\species-monitoring-release.jks'
$env:ANDROID_KEYSTORE_PASSWORD = '<保险库取出>'
$env:ANDROID_KEY_ALIAS         = 'speciesmonitoring-release'
$env:ANDROID_KEY_PASSWORD      = '<保险库取出>'

# 1. 生产环境变量（首次）：复制 .env.production.example → .env.production，填 VITE_API_BASE_URL

# 2. Web 构建 + 同步原生工程
cd species_monitoring_platform\frontend
npm run build:android

# 3. 出签名包（AAB 交商店，APK 用于真机回归）
cd android
.\gradlew.bat bundleRelease assembleRelease
```

产物：

- AAB：`frontend/android/app/build/outputs/bundle/release/app-release.aab`（Play 上传件）
- APK：`frontend/android/app/build/outputs/apk/release/app-release.apk`（`adb install -r` 回归）
- 混淆映射：`frontend/android/app/build/outputs/mapping/release/mapping.txt`（**每个发布版本必须归档**，崩溃堆栈反混淆用；Play Console 可同步上传）

构建保护：`app/build.gradle` 中有 taskGraph 守卫——4 个签名变量不齐时，任何 release 任务直接失败，不会产出未签名包。

## 4) R8/ProGuard（已开启）

- `minifyEnabled true` + `shrinkResources true`，规则文件 `frontend/android/app/proguard-rules.pro`。
- 已保留：Capacitor 桥与全部 `@CapacitorPlugin` 反射入口、Cordova 兼容层、`@JavascriptInterface`、`@capacitor-community/sqlite`（含 SQLCipher JNI）。
- 升级/新增 Capacitor 插件后必须复跑第 5) 节回归，确认插件反射未被裁剪。

## 5) 发布前回归（最小集）

1. `adb install -r app-release.apk`（注意：与旧调试包签名不同，需先卸载 debug 包）。
2. 冷启动进入首页无白屏（WebView 资产 + R8 验证）。
3. 各插件冒烟：拍照、录音、定位打点、SQLite 本地写读、离线提交队列。
4. `mapping.txt` 抽查：`com.getcapacitor` 类名未被重命名（保留规则生效）。

## 6) CI 一键出包（GitHub Actions）

工作流：`.github/workflows/android-release.yml`

- 触发：打 tag `v*`（如 `v1.0.0`）或手动 `workflow_dispatch`。
- 流程：npm ci → `npm run build:android` → secrets 还原 keystore → `gradlew bundleRelease assembleRelease` → `jarsigner -verify` → 上传 AAB/APK/mapping 工件。
- 需配置的 Repository Secrets：

| Secret | 值 |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | keystore 文件的 base64。生成命令（PowerShell，临时落地后**立即删除**）：<br/>`[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\Users\Administrator\.keystores\species-monitoring\species-monitoring-release.jks")) \| Out-File -Encoding ascii android-keystore.b64`<br/>把 `android-keystore.b64` 内容粘进 GitHub Secret，然后 `Remove-Item android-keystore.b64 -Force`。 |
| `ANDROID_KEYSTORE_PASSWORD` | 保险库口令 |
| `ANDROID_KEY_ALIAS` | `speciesmonitoring-release` |
| `ANDROID_KEY_PASSWORD` | 与 keystore 口令相同（PKCS12） |

## 7) iOS：现状与 TestFlight 计划

已完成（可在 Windows 侧维护）：

- `frontend/ios/` 工程骨架已生成（Capacitor 8，7 个插件已注册），bundleId `org.biodiversity.speciesmonitoring`。
- `Info.plist` 已含 5 条权限文案（相机/麦克风/定位/相册读取/相册写入，中英双语，按"为什么用+何时触发"撰写）。
- 版本号已对齐 Android（1.0.0 / 10000）。

仍需 macOS 环境才能推进（硬依赖）：

| 步骤 | 命令/动作 | 依赖 |
|---|---|---|
| 1. 拉工程装依赖 | `npm ci && npm run build && npx cap sync ios`，`cd ios/App && pod install` | Mac/云 Mac（Xcode 15+，CocoaPods） |
| 2. 签名配置 | Xcode → Signing & Capabilities → 选 Team，自动管理签名 | Apple Developer Program（个人/组织，99 USD/年） |
| 3. 真机冒烟 | 跑第 5) 节回归（换成 iOS 真机） | 一台 iPhone |
| 4. 出包上传 | Xcode Archive → Distribute → App Store Connect（或 fastlane `build_app + upload_to_testflight`） | 同上 |
| 5. TestFlight 内测 | App Store Connect 添加内部测试员（≤100，免审），立即可装 | Apple 账号配置 |
| 6. TestFlight 外测 | 添加外部测试员（≤10000，需一次 Beta 审核，1–2 天） | 隐私政策 URL 必填 |

云 Mac 选项（无实体 Mac 时）：GitHub Actions `macos-14` runner（私有仓计费）/ MacStadium / AWS EC2 Mac。CI 化 iOS 出包建议用 fastlane match 管理证书，等 Apple 账号到位后再落地。

## 8) 审核挑刺自检（提审前最后一遍）

- [ ] 权限弹窗前有场景化引导，拒绝后功能可降级（Android target 36 + iOS 双端）。
- [ ] Play Data Safety / App Privacy 表单与 Manifest、Info.plist 权限逐项一致（多报漏报都会被打回）。
- [ ] `FOREGROUND_SERVICE_LOCATION/MICROPHONE` 需在 Play Console 申报使用场景视频（Android 14+ 政策）。
- [ ] 隐私政策 URL 公网可达，且内容覆盖定位/录音/照片三类敏感数据。
- [ ] 审核测试账号可用、后端 24h 可达（见 `03_missing_required_business_inputs.md`）。
- [ ] AAB 用正式 keystore 签名、versionCode 递增、mapping.txt 已归档。
