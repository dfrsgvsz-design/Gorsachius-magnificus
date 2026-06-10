# 物种监测平台前端重构日志

> 本文件记录每一步重构操作，方便后续人员接续工作。

## 项目基本信息

| 项                  | 值                                                              |
|---------------------|----------------------------------------------------------------|
| 项目路径             | `f:\Gorsachius magnificus\species_monitoring_platform\`         |
| 前端框架             | React 18 + Vite + TailwindCSS                                  |
| 移动端               | Capacitor 8 (Android)                                          |
| 地图                 | Leaflet + react-leaflet                                        |
| 国际化               | i18next (en / zh)                                              |
| 状态管理             | 无全局状态库，全部 useState（重构目标之一）                        |
| 路由                 | 无 React Router，App.jsx 内 useState 切 tab（重构目标之一）       |

---

## 重构前现状诊断

### 1. 前端目录结构

```
src/
├── App.jsx                    (749 行) — 主入口、tab切换、header/footer/nav
├── constants.js               (251 行) — TAB/MODULE/NAV 配置、i18n 文案
├── main.jsx                   (930 bytes) — Vite 入口、SW 管理
├── index.css                  (8.8 KB) — TailwindCSS + 自定义样式
├── i18n/                      — i18next 配置
├── lib/
│   ├── api.js                 (38 KB) — 所有 HTTP 请求封装
│   ├── api.test.js            (14 KB) — API 测试
│   ├── attachmentContract.js  (7 KB) — 附件标准化
│   ├── fieldOpsDrafts.js      (3 KB) — 轨迹草稿工具
│   ├── mobileNative.js        (18 KB) — Capacitor 桥接
│   ├── PlatformConfigContext.jsx (1.4 KB) — 平台配置 Context
│   ├── surveyOffline.js       (49 KB) — 离线数据操作引擎
│   └── surveyOffline.test.js  (13 KB) — 离线引擎测试
└── components/
    ├── common/                — 6 个通用组件 + index.js
    │   ├── ConfidenceBadge.jsx
    │   ├── DiversityRow.jsx
    │   ├── LoadingState.jsx
    │   ├── PageChrome.jsx
    │   ├── StatCard.jsx
    │   └── StatusBanner.jsx
    └── tabs/                  — 16 个 Tab 页
        ├── FieldOpsTab.jsx    ★ (203 KB / 4506 行) — 核心巨文件
        ├── AnalyzeTab.jsx     (38 KB)
        ├── VerifyTab.jsx      (30 KB)
        ├── MonitorTab.jsx     (25 KB)
        ├── DashboardTab.jsx   (23 KB)
        ├── EmbeddingsTab.jsx  (18 KB)
        ├── mobileNative.js    (18 KB)
        ├── SpeciesTab.jsx     (17 KB)
        ├── DevicesTab.jsx     (16 KB)
        ├── SDMTab.jsx         (16 KB)
        ├── SettingsTab.jsx    (15 KB)
        ├── XenoCantoTab.jsx   (11 KB)
        ├── PhenologyTab.jsx   (10 KB)
        ├── SoundscapeTab.jsx  (8 KB)
        ├── OccupancyTab.jsx   (8 KB)
        ├── AboutTab.jsx       (9 KB)
        └── FewShotTab.jsx     (7 KB)
```

### 2. FieldOpsTab.jsx 内部结构 (4506 行)

| 区间         | 内容                                         |
|-------------|---------------------------------------------|
| 1-85        | imports (18 个模块)                           |
| 86-649      | 常量 + 协议定义 (PROTOCOL_OPTIONS, VERTEBRATE_SUBMODULES) + 工具函数 |
| 650-1005    | 更多工具函数 (buildProtocolCatalog, taxonomy匹配, mask preview) |
| 1006-1075   | **主组件 export default** 开始，30+ useState |
| 1076-1360   | 轨迹草稿管理函数 (sync/pause/handleTrackPoint) |
| 1186-1360   | 10+ useEffect (state persistence, GPS, network, audio cleanup) |
| 1362-1752   | useMemo 派生数据 (protocol/taxonomy/route filtering) |
| 1758-1970   | 更多 useEffect (bootstrap, route/event sync, protocol switching) |
| 1972-2145   | handlePullSync / handlePushSync / route/program/protocol选择 |
| 2147-3037   | 完整 CRUD handlers (project/site/route/observation/track/export) |
| 3039-3877   | **JSX 渲染** (~840 行)                        |
| 3880-4055   | RouteReportPanel 子组件                       |
| 4057-4300   | VertebrateReviewPanel 子组件                  |
| 4302-4506   | MetricCard / ProtocolExportPanel / FieldSurveyMap 子组件 |

### 3. 核心问题

1. **单文件 4506 行**：地图/轨迹/记录/同步/导出/协议管理全混在一起，不可维护
2. **30+ useState + 20+ useEffect**：状态耦合严重，任何改动都可能引起连锁问题
3. **无全局状态管理**：surveyState 通过 useState + localStorage 手动管理
4. **无路由系统**：App.jsx 用 `useState(activeTab)` 做 tab 切换
5. **重复逻辑**：`handleSaveObservation` 和 `saveObservationOnlineAware` 高度重复
6. **子组件未拆文件**：RouteReportPanel / VertebrateReviewPanel / MetricCard / FieldSurveyMap 都在同一文件

---

## 重构架构设计

### 目标架构

```
src/
├── App.jsx                       — 精简为路由 + layout shell
├── constants.js                  — 保持不变
├── main.jsx                      — 保持不变
├── hooks/                        — ★ 新增：自定义 hooks
│   ├── useSurveyStore.js         — surveyState 全局管理 (替代 useState)
│   ├── useTrackRecording.js      — GPS 轨迹录制逻辑
│   ├── useAudioCapture.js        — 音频录制逻辑
│   ├── useNetworkStatus.js       — 在线/离线状态
│   ├── useGeolocation.js         — 当前位置
│   └── useProtocolEngine.js      — 协议选择/切换/字段管理
├── store/                        — ★ 新增：轻量 Context store
│   └── SurveyContext.jsx         — surveyState + dispatch
├── components/
│   ├── common/                   — 保持不变 + 新增
│   │   ├── MetricCard.jsx        — 从 FieldOpsTab 提取
│   │   └── ... (existing)
│   ├── fieldops/                 — ★ 新增：FieldOps 子组件目录
│   │   ├── FieldOpsTab.jsx       — 精简为组合层 (~200 行)
│   │   ├── MapPanel.jsx          — 地图展示 + 瓦片管理
│   │   ├── TrackPanel.jsx        — 轨迹录制控制
│   │   ├── RecordPanel.jsx       — 观察记录表单
│   │   ├── ProjectSitePanel.jsx  — 项目/站点/路线管理
│   │   ├── ProtocolSelector.jsx  — 协议族选择器
│   │   ├── SyncPanel.jsx         — 同步队列 + 冲突
│   │   ├── ExportPanel.jsx       — 导出管理 (合并 ProtocolExportPanel + VertebrateReviewPanel)
│   │   ├── RouteReportPanel.jsx  — 路线报告
│   │   ├── FieldSurveyMap.jsx    — Leaflet 地图组件
│   │   └── EssentialWorkflow.jsx — "Essential field workflow" 快捷区
│   └── tabs/                     — 其他 tabs 保持不变
└── lib/                          — 保持不变（后续可拆）
```

### 拆分策略

**Phase 1: 基础设施** (hooks + context)
- [ ] 创建 `hooks/useNetworkStatus.js` — 从 FieldOpsTab 提取网络状态逻辑
- [ ] 创建 `hooks/useGeolocation.js` — 从 FieldOpsTab 提取 GPS 位置逻辑
- [ ] 创建 `store/SurveyContext.jsx` — 将 surveyState 升级为 Context + useReducer
- [ ] 创建 `hooks/useSurveyStore.js` — 封装 surveyState CRUD 操作

**Phase 2: 子组件提取** (从 FieldOpsTab 底部开始，风险最低)
- [ ] 提取 `MetricCard` → `components/common/MetricCard.jsx`
- [ ] 提取 `FieldSurveyMap` → `components/fieldops/FieldSurveyMap.jsx`
- [ ] 提取 `RouteReportPanel` → `components/fieldops/RouteReportPanel.jsx`
- [ ] 提取 `VertebrateReviewPanel` → `components/fieldops/ExportPanel.jsx`
- [ ] 提取 `ProtocolExportPanel` → 合并到 `ExportPanel.jsx`

**Phase 3: 业务逻辑拆分** (从 FieldOpsTab 主体提取)
- [ ] 创建 `hooks/useTrackRecording.js` — 轨迹 start/stop/pause + GPS watch
- [ ] 创建 `hooks/useAudioCapture.js` — 音频录制逻辑
- [ ] 创建 `hooks/useProtocolEngine.js` — 协议切换 + 字段管理
- [ ] 提取 `ProtocolSelector` → `components/fieldops/ProtocolSelector.jsx`
- [ ] 提取 `ProjectSitePanel` → `components/fieldops/ProjectSitePanel.jsx`
- [ ] 提取 `MapPanel` → `components/fieldops/MapPanel.jsx`
- [ ] 提取 `TrackPanel` → `components/fieldops/TrackPanel.jsx`
- [ ] 提取 `RecordPanel` → `components/fieldops/RecordPanel.jsx`
- [ ] 提取 `SyncPanel` → `components/fieldops/SyncPanel.jsx`

**Phase 4: 功能修复**
- [ ] 地图瓦片代理验证 (FIELD_RELEASE_MODE 下 tile URL 是否正确)
- [ ] 轨迹启动简化 (允许无 route 时也能录 GPS 轨迹)
- [ ] 记录表单简化 (最小必填字段 + 可展开高级选项)

**Phase 5: 验证 + 清理**
- [ ] dev server 启动验证
- [ ] 各面板渲染验证
- [ ] 移除 FieldOpsTab 中已提取的死代码
- [ ] 更新本文档

---

## 操作日志

### Step 0: 现状分析 (已完成)
- 读取并分析了 FieldOpsTab.jsx 全部 4506 行
- 读取并分析了 App.jsx (749 行)、constants.js (251 行)
- 读取并分析了 lib/ 目录所有文件的大小和职责
- 确认两个平台 FieldOpsTab 完全相同，api.js/main.jsx 有微小差异
- 创建了本重构日志

### Step 1: Phase 1 — 基础 hooks + Context (已完成)

创建文件：
- `src/hooks/useNetworkStatus.js` (26 行) — 浏览器 online/offline 状态监听
- `src/hooks/useGeolocation.js` (42 行) — GPS 定位 (Web + Capacitor)
- `src/hooks/useAudioCapture.js` (103 行) — MediaRecorder 音频录制封装
- `src/store/SurveyContext.jsx` (93 行) — React Context 管理 surveyState，支持 localStorage + native storage 持久化

### Step 2: Phase 2 — 子组件提取 (已完成)

创建文件：
- `src/components/fieldops/fieldOpsUtils.js` (137 行) — 共享工具函数 (toArray, formatPreviewKey, buildMaskPreview, EXPORT_JURISDICTIONS 等 15 个函数/常量)
- `src/components/fieldops/MetricCard.jsx` (17 行) — 指标卡片展示组件
- `src/components/fieldops/FieldSurveyMap.jsx` (97 行) — Leaflet 地图组件 (含 MapViewport)
- `src/components/fieldops/RouteReportPanel.jsx` (155 行) — 路线/站点报告面板
- `src/components/fieldops/ProtocolExportPanel.jsx` (157 行) — 协议导出面板
- `src/components/fieldops/VertebrateReviewPanel.jsx` (237 行) — 陆生脊椎动物审核面板
- `src/components/fieldops/index.js` (5 行) — barrel export

FieldOpsTab.jsx 变更：
- 添加 imports: `../fieldops` (组件) + `../fieldops/fieldOpsUtils` (工具函数)
- 删除 react-leaflet import (CircleMarker, MapContainer, Polyline, TileLayer, useMap)
- 删除内联 EXPORT_JURISDICTIONS 常量
- 删除内联工具函数 (toArray → sortByRecent，共 ~150 行)
- 删除底部内联组件定义 (RouteReportPanel → FieldSurveyMap，共 ~625 行)
- **行数变化: 4506 → 3747 行 (-759)**

构建验证: `vite build` ✅ (3.63s, 2375 modules)

### Step 3: Phase 3 — useTrackRecording hook (已完成)

创建文件：
- `src/hooks/useTrackRecording.js` (140 行) — 轨迹录制核心逻辑 (状态/refs/syncDraftIntoUi/setStoredTrackDraft/clearTrackWatch/pauseTrackDraft/handleTrackPoint)
- `src/hooks/index.js` (4 行) — hooks barrel export

FieldOpsTab.jsx 变更：
- 添加 `import useTrackRecording from '../../hooks/useTrackRecording'`
- 替换 6 个内联 state/ref 声明为 hook 解构调用
- 删除 5 个内联函数 (syncDraftIntoUi, setStoredTrackDraft, clearTrackWatch, pauseTrackDraft, handleTrackPoint)
- **行数变化: 3747 → 3662 行 (-85)**

构建验证: `vite build` ✅

### Step 4: Phase 4 — 功能修复 (部分完成)

#### 4a: 地图瓦片代理 ✅
- 分析确认 tileUrl 逻辑正确: `FIELD_RELEASE_MODE ? pilotTileProxyUrl : remoteTileUrl`
- `platformConfig?.map?.tile_proxy_url` 优先级合理，fallback 到 `/api/maps/tiles/{z}/{x}/{y}`

#### 4b: 轨迹启动简化 ✅
- 移除 `handleStartTrack` 中强制要求 selectedRoute 的前置检查
- 现在允许无 route 时直接启动 GPS 轨迹录制 (ad-hoc survey)
- `buildTrackDraftForStart` 已安全处理 `selectedRoute=null`

#### 4c: 记录表单简化 ⏸️ (暂缓)
- 观察表单与协议引擎深度耦合 (taxon_group ↔ protocol ↔ submodule 联动)
- 需要更完整的 useProtocolEngine 拆分后才能安全简化
- 建议在后续迭代中处理

构建验证: `vite build` ✅ (FieldOpsTab chunk 163.45 kB)

### Step 5: JSX 面板拆分 — 第二轮 (已完成)

创建文件：
- `src/components/fieldops/TrackPanel.jsx` (~75 行) — 轨迹录制控制面板 (状态/指标/启停按钮)
- `src/components/fieldops/SyncPanel.jsx` (~55 行) — 同步队列+冲突显示面板
- `src/components/fieldops/MediaInboxPanel.jsx` (~30 行) — 媒体收件箱列表
- `src/components/fieldops/ProjectPanel.jsx` (~55 行) — 项目选择+创建表单
- `src/components/fieldops/SitePanel.jsx` (~75 行) — 站点选择+创建表单 (含 GPS 自动填充)
- `src/components/fieldops/TransectPanel.jsx` (~105 行) — 样线/路线管理 (观察员/天气/事件字段/指标)
- `src/components/fieldops/MapToolsPanel.jsx` (~75 行) — 地图瓦片预加载/路线导入导出/离线地图包
- `src/components/fieldops/ObservationFormPanel.jsx` (~195 行) — 物种观察记录表单 (分类/证据/附件/音频)

FieldOpsTab.jsx 变更：
- 替换 8 段内联 JSX 为组件调用
- 清理 7 个不再使用的 lucide-react imports (AlertTriangle, Crosshair, Camera, CloudDownload, Download, Mic, Upload)
- 修复 essential workflow 中轨迹启动按钮残留的 `!selectedRoute` disabled 条件
- **行数变化: 3662 → 3291 行 (-371)**
- **累计变化: 4506 → 3291 行 (-26.9%)**

构建验证: `vite build` ✅ (3.65s)

### Step 6: JSX 面板拆分 — 第三轮 (已完成)

创建文件：
- `src/components/fieldops/ActiveModuleCard.jsx` (~40 行) — 活动模块信息卡 (图标/标签/描述/提示)
- `src/components/fieldops/ProtocolSelectorPanel.jsx` (~145 行) — 协议族选择器 (程序/子模块/协议/管辖区 + 指标卡 + 标签芯片)
- `src/components/fieldops/PilotFlowPanel.jsx` (~65 行) — 样线试点流程 (状态卡 + 工作流步骤)
- `src/components/fieldops/EssentialWorkflowPanel.jsx` (~105 行) — 核心野外工作流 (快捷按钮 + 地图 + 指标 + 最近记录)

FieldOpsTab.jsx 变更：
- 替换 4 段内联 JSX 为组件调用
- 清理 2 个不再使用的 lucide-react imports (Activity, Square)
- lucide imports 从 13 个精简为 4 个 (Loader2, MapPinned, RefreshCw, Save)
- **行数变化: 3291 → 3112 行 (-179)**
- **累计变化: 4506 → 3112 行 (-30.9%)**

构建验证: `vite build` ✅ (3.12s)

### Step 7: protocolEngine 模块提取 (已完成)

创建文件：
- `src/components/fieldops/protocolEngine.js` (788 行) — 协议引擎模块，包含：
  - 常量: `TAXA`, `DEFAULT_REMOTE_TILE_URL`, `DEFAULT_FIELD_TILE_PROXY_URL`, `PROGRAM_OPTIONS`, `TERRESTRIAL_VERTEBRATE_PROTOCOLS`, `VERTEBRATE_SUBMODULES`, `PROTOCOL_OPTIONS` (7 个协议定义)
  - i18n: `COPY` (en/zh 双语 UI 文案)
  - 纯函数 (37 个): `pickLocale`, `humanizeFieldKey`, `uniqueNormalizedStrings`, `inferProtocolDefaultTaxonGroup`, `inferProtocolDefaultEvidenceType`, `getVertebrateSubmoduleById`, `resolveVertebrateSubmodule`, `deriveVertebrateSubmoduleId`, `inferFieldType`, `getRemoteFieldKeys`, `buildProtocolFieldDefinitions`, `normalizeProtocolDefinition`, `buildProtocolCatalog`, `mergeTaxonomyCatalogEntries`, `findSpeciesMatch`, `createEmptyTransectSession`, `buildProtocolFieldState`, `getProtocolDefinition`, `createProtocolState`, `resolveProtocolSelection`, `normalizeProtocolFieldValues`, `matchesActiveSubmodule`, `matchesProtocolObservation`, `matchesProtocolTrack`, `getMatchingTaxonomyPackages`, `getTaxonomyGateIssueLabels`, `buildTaxonomyGateWarningMessage`, `buildTaxonomyMetricNote`, `buildTaxonomyGateBlockingMessage`

FieldOpsTab.jsx 变更：
- 删除 736 行内联常量和纯函数，改为从 protocolEngine 导入
- 清理 10 个未使用的 protocolEngine 导入（仅在 protocolEngine 内部使用）
- **行数变化: 3112 → 2376 行 (-736)**
- **累计变化: 4506 → 2376 行 (-47.3%)**

构建验证: `vite build` ✅ (3.19s)

### Step 8: useSyncEngine hook 提取 (已完成)

创建文件：
- `src/hooks/useSyncEngine.js` (208 行) — 同步引擎 hook，包含：
  - 状态: `networkOnline`, `loadingSync`, `bootstrapReady` (3 个 useState)
  - 副作用: 网络监听 useEffect, 远程协议拉取 useEffect, bootstrap hydration useEffect
  - 函数: `handlePullSync` (useCallback, 并行拉取 sync/protocols/taxonomy/designAssets)
  - 函数: `handlePushSync` (useCallback, 推送 syncQueue + 自动 pull)

FieldOpsTab.jsx 变更：
- 删除 3 个 useState (`loadingSync`, `networkOnline`, `bootstrapReady`)
- 删除 1 个 useRef (`hydratedRef`)
- 删除 3 个 useEffect (网络监听、协议拉取、bootstrap)
- 删除 2 个 async function (`handlePullSync`, `handlePushSync`)
- 清理 6 个不再需要的 imports (`pullSurveySync`, `pushSurveySync`, `getSurveyProtocols`, `getSurveyDesignAssets`, `applySyncResult`)
- 替换 `networkOnline` 引用为 hook 返回的 `isOnline`
- **行数变化: 2376 → 2248 行 (-128)**
- **累计变化: 4506 → 2248 行 (-50.1%)**

构建验证: `vite build` ✅ (3.42s)

### Step 9: useProtocolSelection hook 提取 (已完成)

创建文件：
- `src/hooks/useProtocolSelection.js` (301 行) — 协议选择 hook，包含：
  - 状态: `protocolState` (useState, 协议选择完整状态)
  - 派生值 (5 个 useMemo): `currentProgram`, `activeVertebrateSubmoduleId`, `activeVertebrateSubmodule`, `visibleProtocols`, `protocolDefinition`, `activeObservationTaxonGroups`, `activeTaxonomySearchGroup`
  - 同步副作用 (6 个 useEffect): 存储选择恢复、模块种子协议、协议状态持久化、分类群同步、脊椎动物子模块同步、可见协议回退
  - 选择 handlers (5 个): `handleSelectProgram`, `handleSelectProtocol`, `handleSelectVertebrateSubmodule`, `handleProtocolEventFieldChange`, `handleProtocolRecordFieldChange`

FieldOpsTab.jsx 变更：
- 删除 1 个 useState (`protocolState`)
- 删除 5 个 useMemo (协议派生值)
- 删除 6 个 useEffect (协议同步逻辑)
- 删除 5 个 handler function (协议选择/切换)
- 清理 6 个不再需要的 protocolEngine imports
- **行数变化: 2248 → 2024 行 (-224)**
- **累计变化: 4506 → 2024 行 (-55.1%)**

构建验证: `vite build` ✅ (3.21s)

---

## 当前文件结构 (重构后)

```
src/
├── hooks/                          ★ 新增
│   ├── index.js                    — barrel export
│   ├── useNetworkStatus.js         — 网络状态
│   ├── useGeolocation.js           — GPS 定位
│   ├── useAudioCapture.js          — 音频录制
│   ├── useTrackRecording.js        — 轨迹录制核心
│   ├── useSyncEngine.js            — 同步引擎 (~208 行)
│   └── useProtocolSelection.js     — 协议选择 (~301 行)
├── store/                          ★ 新增
│   └── SurveyContext.jsx           — surveyState Context
├── components/
│   ├── fieldops/                   ★ 新增 (20 文件)
│   │   ├── index.js                — barrel export
│   │   ├── fieldOpsUtils.js        — 共享工具函数 (~130 行)
│   │   ├── protocolEngine.js       — 协议引擎 (~788 行)
│   │   ├── MetricCard.jsx          — 指标卡片
│   │   ├── FieldSurveyMap.jsx      — Leaflet 地图
│   │   ├── RouteReportPanel.jsx    — 路线报告
│   │   ├── ProtocolExportPanel.jsx — 协议导出
│   │   ├── VertebrateReviewPanel.jsx — 脊椎动物审核
│   │   ├── TrackPanel.jsx          — 轨迹录制控制
│   │   ├── SyncPanel.jsx           — 同步队列+冲突
│   │   ├── MediaInboxPanel.jsx     — 媒体收件箱
│   │   ├── ProjectPanel.jsx        — 项目管理
│   │   ├── SitePanel.jsx           — 站点管理
│   │   ├── TransectPanel.jsx       — 样线管理
│   │   ├── MapToolsPanel.jsx       — 地图工具
│   │   ├── ObservationFormPanel.jsx — 观察记录表单
│   │   ├── ActiveModuleCard.jsx    — 活动模块信息卡
│   │   ├── ProtocolSelectorPanel.jsx — 协议族选择器
│   │   ├── PilotFlowPanel.jsx      — 试点流程面板
│   │   └── EssentialWorkflowPanel.jsx — 核心工作流面板
│   └── tabs/
│       └── FieldOpsTab.jsx         — 2024 行 (原 4506 行, -55.1%)
```

## 后续待办

1. **记录表单简化** — 简化 observationForm 相关逻辑
2. **SurveyContext 实际接入** — 替换 FieldOpsTab 中的 useState(surveyState)
3. **路由系统** — 可选：引入 React Router 替换 useState tab 切换

---

*最后更新: Step 9 (useProtocolSelection hook 提取完成, 2024 行, -55.1%), 构建验证通过*
