# Android / iOS 提审材料清单（可勾选）

> 适用范围：`acoustic_platform/frontend` 与 `species_monitoring_platform/frontend`（当前两者移动端配置一致）。

## 1) 基础信息

- [ ] 应用中文名、英文名（商店展示名）
- [x] `applicationId / bundleId`：`org.biodiversity.speciesmonitoring`（Android/iOS 统一）
- [x] 版本号 / 构建号：`versionName 1.0.0` / `versionCode 10000`（规则：versionCode = major×10000 + minor×100 + patch，详见 `06_packaging_signing_runbook.md`）
- [ ] 上架地区、分级、分类、关键词
- [ ] 开发者/发行主体名称与联系邮箱

## 2) 隐私与数据合规

- [ ] 隐私政策 URL（公网可访问）
- [ ] 用户协议/服务条款 URL（公网可访问）
- [ ] 数据收集矩阵（收集项、用途、是否可选、保留时长、第三方共享）
- [ ] 数据主体权利机制（删除账号、导出数据、注销路径）
- [ ] 未成年人相关声明与处理流程（如适用）

## 3) 权限与敏感能力（需逐项说明“为什么用、何时触发、不授权是否可用”）

### Android（已从 `AndroidManifest.xml` 识别）

- [x] `android.permission.INTERNET`
- [x] `android.permission.ACCESS_NETWORK_STATE`
- [x] `android.permission.ACCESS_COARSE_LOCATION`
- [x] `android.permission.ACCESS_FINE_LOCATION`
- [x] `android.permission.CAMERA`
- [x] `android.permission.RECORD_AUDIO`
- [x] `android.permission.MODIFY_AUDIO_SETTINGS`
- [x] `android.permission.READ_MEDIA_IMAGES`
- [x] `android.permission.READ_MEDIA_AUDIO`
- [x] `android.permission.READ_EXTERNAL_STORAGE` (`maxSdkVersion=32`)

### iOS（工程已生成：`frontend/ios/App`）

- [x] `Info.plist` 权限文案已写入（中英双语）：`NSCameraUsageDescription`、`NSMicrophoneUsageDescription`、`NSLocationWhenInUseUsageDescription`、`NSPhotoLibraryUsageDescription`、`NSPhotoLibraryAddUsageDescription`
- [ ] 文案是否需法务/品牌复核（提审前确认一次）

## 4) 商店素材

### Android / Google Play

- [ ] 应用图标（512x512）
- [ ] Feature Graphic（1024x500）
- [ ] 手机截图（至少 2 张，建议 1080x1920 或同等比例）
- [ ] 平板截图（如支持平板）
- [ ] 宣传视频链接（可选）

### iOS / App Store Connect

- [ ] App Icon（1024x1024，无透明）
- [ ] iPhone 6.7" 截图（至少 1 组）
- [ ] iPhone 6.5" 或 6.1" 截图（按当前要求）
- [ ] iPad 截图（如声明支持 iPad）
- [ ] 预览视频（可选）

## 5) 测试账号与审核协助

- [ ] 审核测试账号（账号/密码/手机号/验证码获取方式）
- [ ] 测试环境可用性（24h 可访问）
- [ ] 审核路径说明（从启动到核心功能）
- [ ] 特殊白名单/地区限制说明
- [ ] 若需硬件设备，提供模拟方式或演示视频

## 6) 版本说明与发布信息

- [ ] 本次更新说明（面向用户）
- [ ] 详细变更记录（面向审核/内部）
- [ ] 已知问题与规避方案
- [ ] 回滚方案与紧急联系人

## 7) 预提审技术检查

- [ ] 生产 API 域名、证书、备案信息可访问
- [ ] 隐私弹窗与权限弹窗触发时机正确
- [ ] 首次拒绝权限后，应用可降级运行并给出引导
- [ ] 核心流程离线/弱网可预期失败并有提示
- [ ] 崩溃监控与日志脱敏已启用

