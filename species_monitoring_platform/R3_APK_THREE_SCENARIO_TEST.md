# R3 APK 三场景验证手册

**APK**: `F:\Gorsachius magnificus\species-monitoring-survey-debug-hybridlocal-bugABCD-fix.apk` (30.07 MB)
**修复内容**: Bug A (SQLite 连接残留) + Bug B (taxonomy gate 误报) + Bug C (axios interceptor 误拦) + Bug D (hybrid local 显"后端离线")
**测试日期**: 2026-04-26

---

## 适用场景

对应你们的三类实验：
1. **Simulation (本地仿真)** — 模拟器或测试环境，host 有外网
2. **Field (野外实验)** — 真机带去野外，可能有 4G 也可能完全断网
3. **No-Internet (无网)** — 真机彻底断网（飞行模式 / Wi-Fi 关 / 4G 关）

R3 APK 是 **hybrid local 架构**：所有 CRUD 都在设备本地 SQLite，**不依赖远程 backend**。三种场景下功能应等价，差别只在 sync/export 按钮（用户主动触发时才会去找后端）。

---

## 共通安装步骤

```powershell
# 装 APK
adb install -r "F:\Gorsachius magnificus\species-monitoring-survey-debug-hybridlocal-bugABCD-fix.apk"

# 授权（避免首次启动权限弹窗打断）
$pkg = "org.biodiversity.speciesmonitoring"
adb shell pm grant $pkg android.permission.ACCESS_FINE_LOCATION
adb shell pm grant $pkg android.permission.ACCESS_COARSE_LOCATION
adb shell pm grant $pkg android.permission.RECORD_AUDIO
adb shell pm grant $pkg android.permission.CAMERA
adb shell pm grant $pkg android.permission.POST_NOTIFICATIONS

# 启动
adb shell am force-stop $pkg
adb shell am start -n "$pkg/.MainActivity"
```

---

## 场景一：Simulation（本地仿真，host 联网）

### 操作
1. 模拟器或真机连 host Wi-Fi（host 有外网）
2. 装 R3 APK + 启动

### 期望行为（启动后 5 秒内观察）

| 检查项 | 期望 | 不符合即说明 |
|---|---|---|
| 顶部状态点颜色 | 🟢 绿色 (status-dot-online) | Bug D 未生效 |
| 顶部状态文字 | **"本地模式"** / **"Local mode"** | Bug D 未生效 |
| 红色 error banner | 不出现 | Bug A/C 未生效 |
| 黄色 warning banner | 不出现（默认在 setup step）| Bug B 未生效 |
| 默认 tab | 外业 (FieldOps) h1 | B2 退化 |
| 五个底部 tab 可见 | 总览 / 外业 / 物种 / 监测 / 更多 | 导航损坏 |
| Console (`adb logcat`) | 仅 `[api] Native build requires VITE_API_BASE_URL ...` 一条 warn | Bug C 未生效 |

### CRUD 测试
- 进入"外业" → 创建项目（"测试项目1"）→ 应秒入库
- `adb shell sqlite3 /data/data/org.biodiversity.speciesmonitoring/databases/bird_survey_localSQLite.db "SELECT * FROM survey_projects"` 验证已写入

---

## 场景二：Field（野外，可能 4G 可能断网）

### 操作
1. 真机带去野外或模拟（关 Wi-Fi 留 4G，或反之）
2. 启动 app

### 期望行为
**与场景一一致**（顶部 "本地模式"，无 banner），因为 hybrid local 不调后端。

### 额外验证
- GPS：进入"外业" → 创建测线 → 点"开始记录" → 应能拿到坐标（蓝色卫星 icon 跳数字）。野外 GPS lock 可能慢 30-60 秒。
- 录音：长按"录音"按钮 → 录 5 秒 → 松开 → 应入 mediaInbox 队列
- 离线后再连网：状态文字仍 **"本地模式"** —— 因为是 native + 无 VITE_API_BASE_URL，`IS_HYBRID_LOCAL_MODE=true` 是 build 时绑定，不会因网络变化而切换

---

## 场景三：No-Internet（彻底断网）

### 操作
```powershell
# 飞行模式 ON（断 Wi-Fi + 蜂窝 + GPS 网络辅助）
adb shell cmd connectivity airplane-mode enable

# 等 5s 让 networkInfo 更新
Start-Sleep -Seconds 5

# 启动 app
adb shell am force-stop org.biodiversity.speciesmonitoring
adb shell am start -n "org.biodiversity.speciesmonitoring/.MainActivity"
```

### 期望行为

| 检查项 | 期望 | 不符合即问题 |
|---|---|---|
| 顶部状态点颜色 | 🟢 绿色（仍 isOnline=true，因为 hybrid_local) | Bug D 未生效 |
| 顶部状态文字 | "本地模式" / "Local mode" | 同上 |
| 顶部蓝色 banner（移动端 sheet） | 不显示 | 离线 banner 文案 `appShell.offlineBanner` 应仅在 navigator.onLine=false 时出 |
| 红/黄 banner | 不出现 | 同场景一 |
| 项目 CRUD | **能创建/编辑/删除** | hybrid local 失败 → 排查 SQLite |
| GPS（如硬件 GPS 还开）| 仍能拿到坐标 | GPS 不依赖网络 |
| sync 按钮 | 灰显 / 提示离线 | 这是预期，因为 useSyncEngine 检测 navigator.onLine=false 后 disable |

### 飞行模式恢复
```powershell
adb shell cmd connectivity airplane-mode disable
```

---

## 故障排查速查表

如果实际表现不符合期望，对照下表：

| 症状 | 可能原因 | 排查命令 |
|---|---|---|
| 顶部仍显"后端离线"/"Backend offline" | 装的不是 R3 APK | `adb shell dumpsys package org.biodiversity.speciesmonitoring \| Select-String versionName` 比对时间戳 |
| 启动出红 banner "Connection ... already exists" | Bug A fix 不生效 | 重装：`adb uninstall org.biodiversity.speciesmonitoring && adb install -r <apk>` |
| 启动出红 banner "Native build requires VITE_API_BASE_URL" | Bug C fix 不生效（旧 build） | 同上 |
| Setup step 默认出黄 banner | Bug B fix 不生效（旧 build） | 同上 |
| 启动有 1-2 秒短暂"连接中..." | 这是预期 | 不是 bug，hybrid local 不显，瞬间过 |
| 创建项目后未入库 | SQLite 连接失败 | `adb logcat \| Select-String -Pattern "SQLite\|getDb\|ensureSchema"` 看错误 |

---

## 提交反馈格式

测完每个场景后，请按下面格式反馈：

```
场景一 Simulation:
  - 顶部状态: ✅/❌ 实际显示 _____
  - 红 banner: ✅/❌
  - 黄 banner: ✅/❌
  - CRUD: ✅/❌

场景二 Field:
  - 同上 + GPS lock 时间 _____

场景三 No-Internet:
  - 同上 + sync 按钮状态 _____
  - 飞行模式下创建项目能否保存 ✅/❌
```

发现任何一项 ❌，**立即贴 logcat 末尾 50 行**：
```powershell
adb logcat -d | Select-Object -Last 50
```

我会基于此精准定位修复。
