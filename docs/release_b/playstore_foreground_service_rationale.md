# Play Console — FOREGROUND_SERVICE_LOCATION declaration

Use this document to fill in the **"Sensitive app permissions and APIs"** section
on Google Play Console when submitting the Species Monitoring Survey app
(`org.biodiversity.speciesmonitoring`). The same body is reusable for AAB and
APK release tracks (internal, closed, open, production).

## Permission declaration form

When prompted "Your app declares the FOREGROUND_SERVICE_LOCATION permission",
answer **Yes** and provide the following.

### 1. Core feature description (max 500 chars)

> 野外生物多样性调查员在 4–8 小时的样线/样点调查中持续记录 GPS 轨迹。屏幕熄灭或应用切换到后台时,前台位置服务保证轨迹点不丢失,以便准确统计样线长度、配速,并将观察点回贴到样线上。停止调查时立即关闭服务。
>
> Field biodiversity surveyors record continuous GPS tracks during 4-8 hour
> line-transect / plot surveys. The foreground location service guarantees no
> track points are dropped when the screen sleeps or the app backgrounds, so
> transect length, pace, and on-route observation snapping stay accurate. The
> service is stopped immediately when the surveyor ends the survey.

### 2. Which app features use the permission

- 字段 / Field: **野外调查 → 调查 → 开始调查 (Field Ops → Survey → Start
  survey)**
- 调用插件 / Plugin call: `@capacitor-community/background-geolocation`
  (`BackgroundGeolocation.addWatcher`)
- 关联实体 / Persisted entity: `track` (geometry: LineString, fields: lat,
  lon, alt, hdop, t)

### 3. When does the location data leave the device?

> 仅当调查员点击"结束 → 同步"且设备在线时,轨迹整体作为单个 GeoJSON 上传到我们
> 自托管的 FastAPI 后端(`POST https://swdyx.eu.cc/api/surveys/tracks`)。从未
> 与第三方共享。声学调查使用同一栈但子域名分离:`acoustic.swdyx.eu.cc`。
>
> Track data only leaves the device when the surveyor taps "End → Sync" while
> online. The full track is uploaded as a single GeoJSON to our self-hosted
> FastAPI backend at `POST https://swdyx.eu.cc/api/surveys/tracks`. Never
> shared with third parties. The companion acoustic survey uses the same
> stack under the `acoustic.swdyx.eu.cc` subdomain.

### 4. Why a foreground service is required (not the standard location API)

> 1. 调查时长 4–8 小时,标准 `getCurrentPosition` 在屏幕熄灭后会被 Android Doze
>    暂停,造成轨迹间断;
> 2. 数据完整性是核心交付物 — 缺失的轨迹点直接影响样线长度统计,触发数据复核;
> 3. 现行 Android 14+ 要求长时间后台位置必须用 `foregroundServiceType="location"`
>    的服务声明,本插件正是按此规范实现。
>
> 1. Surveys last 4-8 hours; standard `getCurrentPosition` is throttled by
>    Android Doze when the screen sleeps, leading to track gaps.
> 2. Data completeness is a core deliverable — missing track points directly
>    affect transect length statistics and trigger re-survey requests.
> 3. Android 14+ mandates that long-running background location work be wrapped
>    in a foreground service of type "location"; this plugin implements that
>    contract exactly.

### 5. Why we can't use a less-sensitive alternative

| Alternative | Why it doesn't work |
|---|---|
| `WorkManager` periodic location | Minimum 15-minute interval misses fine-grained track detail; not survey-grade |
| Fused Location passive listener | Stops when no other app requests location; cannot guarantee continuous capture |
| `requestLocationUpdates` w/o FGS | Throttled to 1 update/min by Doze + App Standby on Android 14+ |
| Manual point logging only | Defeats the purpose of an automated transect track |

### 6. Privacy policy URL

`https://swdyx.eu.cc/privacy`

The privacy policy MUST explicitly describe foreground location collection,
the 4-8 hour duration, and the on-device retention until the user syncs. PM
to confirm the page is live before clicking "Save" in Play Console step 4
(see `play_app_signing_4_steps.md`). The acoustic variant points at
`https://acoustic.swdyx.eu.cc/privacy` — they MUST be two physically
separate pages because Play Console reviews each app independently.

---

## Screencast script (30 s reference video)

The Play Console requires a short screencast demonstrating the foreground
service in real use. Record from a real Android 14 device with screen
recording at 1080×1920, max 30 s, mp4/H.264.

### Scene plan

| Time | Frame | Voice-over / Caption (Chinese + English) |
|---|---|---|
| 0:00–0:03 | App icon → app launches to Field Ops Setup step | "野外调查 App — 启动" / "Field survey app — launch" |
| 0:03–0:08 | Tap **开始调查** (Start survey); rationale modal appears | "出现场景化引导卡 — 说明为什么需要后台位置" / "Scenario card explains why background location is needed" |
| 0:08–0:13 | Tap **始终允许** in the system permission dialog | "用户同意后台位置" / "User grants background location" |
| 0:13–0:18 | Track recording starts; foreground notification appears in drawer | "前台通知栏可见,记录中" / "Foreground notification visible, recording" |
| 0:18–0:22 | Press home button; drag drawer down to show persistent notification | "锁屏/切后台后通知保留" / "Notification persists when backgrounded" |
| 0:22–0:27 | Return to app; tap **结束** (End); notification dismissed | "结束调查 → 通知自动消失" / "End survey → notification dismisses" |
| 0:27–0:30 | Show synced track on map (line) | "轨迹完整记录" / "Complete track recorded" |

### Recording commands

```powershell
# Connect device, enable USB debugging
adb shell screenrecord --time-limit 30 --bit-rate 12000000 --size 1080x1920 /sdcard/fgs_demo.mp4
# Pull to laptop
adb pull /sdcard/fgs_demo.mp4 ./submission/playstore/
# Convert to Play-compatible if needed (Android < 11 produces unsupported codec)
ffmpeg -i fgs_demo.mp4 -c:v libx264 -preset slow -crf 23 -movflags +faststart fgs_demo_play.mp4
```

---

## Pre-submission checklist

- [ ] Backend production domain filled in (sections 3, 6 above)
- [ ] Privacy policy URL live and explicitly covers foreground location
- [ ] 30 s screencast uploaded as `submission/playstore/fgs_demo_play.mp4`
- [ ] `AndroidManifest.xml` declares `FOREGROUND_SERVICE_LOCATION` (✅ already
      present after Batch 5) and `POST_NOTIFICATIONS` (✅ added in Batch 5)
- [ ] `capacitor.config.json` notification copy is in Chinese (✅ Batch 5)
- [ ] App actually requests background location AT THE MOMENT the user taps
      Start survey, NOT at app startup (relies on `usePermissionGate` from
      Batch 4)
- [ ] Permission rejection scenarios verified: foreground-only fallback works
      (8 scenarios from acceptance criteria)
