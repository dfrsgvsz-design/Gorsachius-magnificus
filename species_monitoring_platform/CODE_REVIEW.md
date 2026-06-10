# 生物多样性平台综合代码审查报告

**审查日期**: 2026-04-26
**审查范围**: `species_monitoring_platform` 全栈（前端 React + 后端 FastAPI + Capacitor 离线）
**Lint 状态**: 0 errors, 103 warnings（多为 unused imports/dead code）

---

## 1. 关键问题清单

### P0 — 影响核心功能

| ID | 问题 | 文件 | 影响 |
|---|---|---|---|
| **B1** | 离线地图三套缓存名称不通：`bird-tile-cache-v4`（SW）/ `biodiversity-survey-tiles-v1`（tileCache.js）/ `bird-platform-field-tiles-${key}`（surveyOffline.js） | `service-worker.js` / `tileCache.js` / `surveyOffline.js` | 用户预下载的离线瓦片**永远不会被服务工作者命中**，离线场景下地图空白 |
| **B2** | `DEFAULT_TAB_ID = "dashboard"`，但项目主线是野外调查 | `constants.js:47` | 野外用户首屏多走一步才能进调查界面 |
| **B3** | Service Worker 仅在 `PROD && VITE_ENABLE_SW === 'true'` 时注册 | `main.jsx:16-17` | README 宣称 offline-first，但默认生产构建无 SW |
| **B4** | `NAV_GROUPS` 与 `VISIBLE_NAV_GROUP_IDS` 完全不一致；`PRIMARY_NAV_TAB_IDS`/`DEFERRED_TAB_IDS`/`DEFERRED_NAV_GROUP_IDS` 全部死代码 | `constants.js:154-172` | 死代码堆积，维护负担；ID 集合不交叉表明曾有重构未完成 |

### P1 — 中等优先级

| ID | 问题 | 文件 | 影响 |
|---|---|---|---|
| **B5** | `FieldOpsTab` 第 270-292 行手写一次性 GPS 请求，但 `useGeolocation` hook 已存在并未使用 | `tabs/FieldOpsTab.jsx` / `hooks/useGeolocation.js` | 代码冗余，单一职责违反 |
| **B6** | `MapToolsPanel` 预加载按钮在无项目时禁用，无法使用 `study_region` 回退 | `tabs/FieldOpsTab.jsx:1326-1373` | 阻止首次使用前的离线准备 |
| **B7** | `useTrackRecording.js` 导入但未使用 `useCallback` | `hooks/useTrackRecording.js:1` | lint 警告 |
| **B8** | 27+ 个未使用的导入和函数（`useCurrentGps`、`submitProjectOnlineAware`、`saveSiteOnlineAware`、`PilotFlowPanel` 等）残留在 `FieldOpsTab.jsx` | `tabs/FieldOpsTab.jsx` | 死代码，bundle 体积膨胀 |

### P2 — 低优先级（不影响功能，但建议）

| ID | 问题 | 文件 | 影响 |
|---|---|---|---|
| **B9** | 后端 13+ 处使用 `import main as _m` 在函数体内部，避免循环依赖但耦合性高 | `routes/*.py` | 应改为 FastAPI Depends 注入 |
| **B10** | `_AUTH_EXEMPT_PATHS` 仅匹配 `/api/health` 完整路径，子路径如 `/api/health/readiness` 需 API key | `main.py:500` | 可能阻塞 health 子路径 |
| **B11** | `prefetchMapTiles` 用 `mode: "no-cors"` 抓取 OSM tiles，opaque response 无法验证状态 | `surveyOffline.js:952` | 失败 tile 也会被静默写入缓存 |
| **B12** | `FIELD_RELEASE_MODE = true` 硬编码，无法在开发时切换到外部 OSM | `constants.js:45` | 本地开发若 backend 不可用，地图全空 |

---

## 2. 架构性观察

### 优点
- 前端使用了清晰的关注点分离：`hooks/`、`lib/`、`components/{common,fieldops,tabs}/`
- 后端按功能切分到 22 个 router 文件，避免单 monolithic main.py
- iOS 风格设计已统一（rounded-2xl、SF 系统色板）
- 离线优先架构基础完备：本地存储（localStorage + IndexedDB + Filesystem）、同步队列、冲突合并都已实现
- 多语言（中/英）覆盖完整

### 风险
- `FieldOpsTab.jsx` 仍达 2225 行（重构进度记录显示曾从 4506 行精简至 2024 行，又回涨）
- `survey_store.py` 高达 225 KB（约 6000 行），超过单文件可维护阈值
- `taxonomy_catalog.py` 108 KB，应考虑拆分

---

## 3. 离线/轨迹/可用性专项

### 离线地图（B1 详细分析）

**当前数据流**：
1. 用户在 `MapToolsPanel` 点"预加载地图"
2. 调用 `preloadTilesOnlineAware()` → `prefetchMapTiles({ tileUrl, ..., cacheKey })`
3. `prefetchMapTiles` 把瓦片写入 `bird-platform-field-tiles-${cacheKey}` 缓存
4. **断网时**，Leaflet 通过 `<img>` 标签加载瓦片
5. Service Worker 拦截 fetch，在 `bird-tile-cache-v4` 缓存中查找 → **找不到** → 返回 503

**根因**: 写入和读取走两个完全不同的缓存桶。

**修复方案**：统一让 `prefetchMapTiles` 直接写入 SW 的 `bird-tile-cache-v4`。SW 的 `staleWhileRevalidateTile` 会自动复用预下载的瓦片。

### 轨迹记录

`useTrackRecording.js` 实现合理：
- GPS 精度过滤（默认 30m 阈值）
- 最小时间间隔 3000ms（防 GPS 漂移）
- Native（Capacitor Geolocation）/Web（`navigator.geolocation`）双端兼容
- 暂停/恢复支持
- IndexedDB 持久化 draft

**已发现问题**：FieldOpsTab.jsx 第 270-292 行的一次性 GPS 请求与 `useGeolocation` 重复（B5）。

### 可用性

| 痛点 | 当前 | 建议 |
|---|---|---|
| 首屏直奔调查 | Dashboard | fieldops（B2） |
| 离线首次部署 | 必须先建项目才能预加载瓦片 | 直接用 `study_region` 回退（B6） |
| 默认无 SW | 仅 `VITE_ENABLE_SW=true` 启用 | PROD 默认启用（B3） |
| 死代码混淆 | NAV 4 处死引用 | 删除（B4） |

---

## 4. 修复执行顺序

1. **B1** 离线地图缓存统一（核心）
2. **B2** 默认 Tab 改 fieldops
3. **B3** SW 默认 PROD 启用
4. **B4** 删除 NAV 死代码
5. **B5** FieldOpsTab 用 useGeolocation hook
6. **B6** MapToolsPanel 无项目回退到 study_region
7. **B7** useTrackRecording 清理 unused import
8. **B8** 选择性清理 FieldOpsTab unused（不破坏现有功能）

每步后运行 `npm run lint` 确保零回退。

---

## 5. 验证命令

```powershell
# Frontend
cd species_monitoring_platform/frontend
npm run lint
npm run build

# Backend
cd species_monitoring_platform
python -m unittest discover backend/tests -v
```
