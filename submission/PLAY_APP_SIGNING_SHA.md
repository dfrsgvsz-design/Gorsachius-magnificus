# Play App Signing · SHA 指纹登记表（species_monitoring_platform）

> **创建时间**：2026-06-10（工单 #C P0 W2，工程师 C Batch 3 留给工程师 A 的空模板）
> **责任人**：工程师 A（应用上架人）
> **填写时机**：Play App Signing **启用之后**（详见 `submission/06_packaging_signing_runbook.md` §2.1 第 3 步）
> **填写后用途**：所有依赖 SHA 签名校验的下游平台（Firebase、Google Maps、第三方登录、微信开放平台、地图 SDK …）需要从"旧 keystore SHA"切换到"Google 应用签名密钥 SHA"，本表是单一权威源。

## 0) 状态

- [ ] Play App Signing 已在 Play Console 启用
- [ ] 应用签名密钥 SHA 已记录（下方 §1）
- [ ] 上传密钥 SHA 已记录（下方 §2）
- [ ] 全部下游平台已切换至应用签名密钥 SHA（下方 §3 全部打勾）
- [ ] 切换后做一次端到端冒烟：登录、地图、推送、第三方分享逐项通过（下方 §4 全部打勾）
- [ ] 本文件 commit 到 main 并通知工程师 C 在 `submission/06_packaging_signing_runbook.md` §2.1 表格里标 ✅

## 1) 应用签名密钥（Google 托管 / production）

> 这一组 SHA 是**用户实际安装后**设备上验证用的；**所有第三方平台后台都应该填这一组**。

| 字段 | 值 |
|---|---|
| SHA-1 | `<待填写>` |
| SHA-256 | `<待填写>` |
| 算法 | RSA 2048（Google 默认） |
| 提取位置 | Play Console → 应用 → 设置 → 应用完整性 → 应用签名 → "应用签名密钥证书" |
| 截图归档路径 | `submission/_evidence/play_app_signing_production_key_<yyyy-mm-dd>.png`（截图后 commit） |

## 2) 上传密钥（本地 keystore / upload key）

> 这一组 SHA 是**本地 gradlew bundleRelease 出的 AAB 的签名指纹**；提交到 Play Console 时用它验证。
> 与 `submission/06_packaging_signing_runbook.md` §1 表中的 SHA-256 应**完全一致**（启用前 = 启用后，因为本地 keystore 没变，只是身份从"正式签名"降级为"上传凭证"）。

| 字段 | 值 |
|---|---|
| SHA-1 | `<待填写>` |
| SHA-256 | `<待填写>`（**预期等于** `CA:D0:C1:41:E2:75:21:6D:B2:84:18:58:FF:A0:FC:E6:1E:16:9C:E5:B3:FB:73:3B:0E:95:9B:7D:BF:A7:37:3E`） |
| 算法 | PKCS12 / RSA 2048 |
| 提取位置 | Play Console → 应用 → 设置 → 应用完整性 → 应用签名 → "上传密钥证书" |
| 截图归档路径 | `submission/_evidence/play_app_signing_upload_key_<yyyy-mm-dd>.png` |

如果 §2 SHA-256 与 `06_packaging_signing_runbook.md` §1 不一致，**立即停止上架**并通知工程师 C —— 说明本地 keystore 与上传到 Play 的 AAB 用的不是同一个，存在 keystore 替换风险。

## 3) 下游平台 SHA 切换 checklist

> 一律使用 §1 的"应用签名密钥 SHA"，**不要**用 §2 的上传密钥 SHA。

| 平台 | 后台路径 | 当前登记的旧 SHA（启用前） | 切换后填的新 SHA | 切换日期 | 操作人 | 验证 |
|---|---|---|---|---|---|---|
| Firebase Project (Android app `org.biodiversity.speciesmonitoring`) | console.firebase.google.com → 项目设置 → Android 应用 → SHA 证书指纹 | `<旧 SHA-1>` / `<旧 SHA-256>` | `<§1 SHA-1>` / `<§1 SHA-256>` | `<yyyy-mm-dd>` | `<姓名>` | [ ] 推送收到 / Auth 登录通过 |
| Google Maps Platform / Maps SDK for Android | console.cloud.google.com → API 和服务 → 凭据 → Android 应用限制 | `<旧 SHA-1>` | `<§1 SHA-1>` | `<yyyy-mm-dd>` | `<姓名>` | [ ] 地图正常加载，无水印 / 报错 |
| Google Sign-In / OAuth 2.0 客户端 | console.cloud.google.com → API 和服务 → 凭据 → OAuth 2.0 客户端 ID（Android 类型） | `<旧 SHA-1>` | `<§1 SHA-1>` | `<yyyy-mm-dd>` | `<姓名>` | [ ] 一键登录通过 |
| 微信开放平台（如使用） | open.weixin.qq.com → 移动应用 → 应用签名 | `<旧 MD5 / SHA>` | `<§1 SHA-1 / 转换为 MD5>` | `<yyyy-mm-dd>` | `<姓名>` | [ ] 分享 / 登录通过 |
| 高德 / 百度地图 SDK（如使用） | 各开放平台后台 → 应用管理 → SHA1 | `<旧 SHA-1>` | `<§1 SHA-1>` | `<yyyy-mm-dd>` | `<姓名>` | [ ] 地图加载通过 |
| AppsFlyer / Adjust / 友盟（如使用） | 各 SDK 后台 → Android 应用配置 | `<旧 SHA>` | `<§1 SHA>` | `<yyyy-mm-dd>` | `<姓名>` | [ ] 归因事件正常 |
| 推送服务（FCM 以外，如极光、个推） | 各推送后台 → Android 配置 | `<旧 SHA>` | `<§1 SHA>` | `<yyyy-mm-dd>` | `<姓名>` | [ ] 推送收到 |
| 其他：`<填写>` | | | | | | [ ] |

> 没列到的平台不代表不需要切换 —— 工程师 A 上架前盘点项目依赖（`frontend/package.json` + Android 原生 modules）整理出全集，写进本表。

## 4) 切换后冒烟测试

启用 Play App Signing + 切换全部下游 SHA 后，必须从 Play Store **重新下载**安装包（不要本地 sideload），在真机上跑：

- [ ] 冷启动进入首页，无 Google Play 服务报错
- [ ] 登录（账号 / Google / 微信任一通路）
- [ ] 地图加载（如有）
- [ ] 拍照 + 定位打点 + 离线同步全链路（参照 `submission/04_release_execution_runbook.md` 冒烟集）
- [ ] 推送通知（如有）发一条 test，前后台都收到
- [ ] 分享至微信 / 系统分享（如有）

任一项失败 → 回到 §3 找漏掉的平台。

## 5) 历史

- 2026-06-10 工程师 C 创建空模板（工单 #C Batch 3）
- `<yyyy-mm-dd>` 工程师 A 启用 Play App Signing 并填写 §1 / §2
- `<yyyy-mm-dd>` 工程师 A 完成 §3 切换并通过 §4 冒烟
