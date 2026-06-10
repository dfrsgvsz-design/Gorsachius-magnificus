/**
 * Localized copy for the 4 sensitive runtime permissions the field workflow
 * needs. Each entry has:
 *
 *   - `rationale.zh|en`   — shown BEFORE the OS prompt to explain why
 *   - `denied.zh|en`      — shown AFTER the user denies, with degraded mode
 *   - `recoverHint.zh|en` — short hint shown next to a "Settings" deep link
 *                            when the permission was denied with "Don't ask"
 *   - `icon`              — lucide-react icon name used by the modal/fallback
 *   - `degradedMode`      — short label for what the app still allows
 *
 * The `id` is the canonical permission key used by `usePermissionGate`. It is
 * NOT the Capacitor permission string (those vary per plugin). The hook maps
 * between this id and the appropriate Capacitor request shape.
 */

export const PERMISSIONS = {
  location: {
    id: 'location',
    icon: 'MapPin',
    rationale: {
      zh: {
        title: '需要使用你的位置',
        scene: '在野外样线/样点定位、记录观察点坐标、生成轨迹时使用',
        when: '仅在你点击"开始调查""保存观察"或地图页面时',
        benefit: '让观察点自动吸附到样线、轨迹可导出 GPX / GeoJSON',
        action: '允许使用位置',
        skip: '暂不使用',
      },
      en: {
        title: 'Location is required',
        scene: 'Used for locating field transects/plots, recording observation coordinates, and generating tracks',
        when: 'Only when you tap "Start survey", "Save observation", or open the map',
        benefit: 'Observations auto-snap to transects, and tracks export as GPX / GeoJSON',
        action: 'Allow location',
        skip: 'Not now',
      },
    },
    denied: {
      zh: {
        headline: '已拒绝定位',
        body: '你可以继续录入观察记录,但坐标需要手动填写。需要时在系统设置中开启即可恢复自动定位。',
        degradedMode: '手动输入坐标',
      },
      en: {
        headline: 'Location denied',
        body: 'You can keep entering observations but coordinates have to be filled in manually. Enable location in system settings any time to restore auto-positioning.',
        degradedMode: 'Manual coordinate entry',
      },
    },
    recoverHint: {
      zh: '设置 → 应用 → 权限 → 位置 → 始终允许',
      en: 'Settings → Apps → Permissions → Location → Allow all the time',
    },
  },

  camera: {
    id: 'camera',
    icon: 'Camera',
    rationale: {
      zh: {
        title: '需要使用相机',
        scene: '拍摄物种照片作为观察证据,自动嵌入 GPS 时间戳便于后续核实',
        when: '仅在你点击"拍照"或"+"按钮时',
        benefit: '审核员可以直接看到原始图像,减少误判',
        action: '允许使用相机',
        skip: '改用上传',
      },
      en: {
        title: 'Camera is required',
        scene: 'Take photos of species as observation evidence, with GPS and timestamp embedded for later verification',
        when: 'Only when you tap "Take photo" or the "+" button',
        benefit: 'Reviewers can see the original image directly, reducing misidentification',
        action: 'Allow camera',
        skip: 'Upload instead',
      },
    },
    denied: {
      zh: {
        headline: '已拒绝相机',
        body: '你仍可以从相册或文件中上传照片作为证据。如需现场拍照,请在系统设置中开启相机。',
        degradedMode: '从相册/文件上传',
      },
      en: {
        headline: 'Camera denied',
        body: 'You can still upload photos from your gallery or files as evidence. To capture on-site, enable the camera in system settings.',
        degradedMode: 'Upload from gallery/files',
      },
    },
    recoverHint: {
      zh: '设置 → 应用 → 权限 → 相机',
      en: 'Settings → Apps → Permissions → Camera',
    },
  },

  microphone: {
    id: 'microphone',
    icon: 'Mic',
    rationale: {
      zh: {
        title: '需要使用麦克风',
        scene: '录制鸟类/蛙类等动物叫声作为听觉证据,音频留存便于声纹比对',
        when: '仅在你点击"录音"按钮时',
        benefit: '声纹是动物身份的关键证据,尤其在难以目击时',
        action: '允许使用麦克风',
        skip: '改用文字备注',
      },
      en: {
        title: 'Microphone is required',
        scene: 'Record bird/frog/insect calls as audible evidence; audio is kept for later acoustic comparison',
        when: 'Only when you tap the "Record" button',
        benefit: 'Audio fingerprints are key evidence for animal identity, especially when sightings are difficult',
        action: 'Allow microphone',
        skip: 'Use text notes instead',
      },
    },
    denied: {
      zh: {
        headline: '已拒绝麦克风',
        body: '你可以用文字备注代替录音。若之后需要录音,请在系统设置中开启麦克风。',
        degradedMode: '文字备注代替音频',
      },
      en: {
        headline: 'Microphone denied',
        body: 'You can describe the call as a text note instead. Re-enable the microphone in system settings whenever you need audio.',
        degradedMode: 'Text notes instead of audio',
      },
    },
    recoverHint: {
      zh: '设置 → 应用 → 权限 → 麦克风',
      en: 'Settings → Apps → Permissions → Microphone',
    },
  },

  backgroundLocation: {
    id: 'backgroundLocation',
    icon: 'Activity',
    rationale: {
      zh: {
        title: '需要后台定位(长时间轨迹)',
        scene: '调查时往往步行 4-8 小时,屏幕熄灭后仍需持续记录轨迹点',
        when: '仅在你启动"开始调查"后,在前台通知栏中始终可见',
        benefit: '不会因为锁屏丢失轨迹数据,样线长度统计更准确',
        action: '始终允许',
        skip: '只录前台轨迹',
      },
      en: {
        title: 'Background location is required (long tracks)',
        scene: 'Field surveys often walk 4-8 hours; we need to keep recording track points while the screen is off',
        when: 'Only after you tap "Start survey", with a persistent foreground notification',
        benefit: 'No track data lost to screen-off events; transect length statistics stay accurate',
        action: 'Allow all the time',
        skip: 'Foreground-only track',
      },
    },
    denied: {
      zh: {
        headline: '后台定位已拒绝',
        body: '已切换到"仅前台录轨"模式 — 屏幕熄灭/应用切后台超过约 1 分钟会暂停轨迹,你回到应用时会自动续接。需要长时间轨迹时请在系统设置中改为"始终允许"。',
        degradedMode: '仅前台录轨',
      },
      en: {
        headline: 'Background location denied',
        body: 'Switched to "foreground-only track" mode — the track pauses when the screen sleeps or the app backgrounds for about a minute; it resumes automatically when you reopen the app. Change location permission to "Allow all the time" in system settings for long tracks.',
        degradedMode: 'Foreground-only track',
      },
    },
    recoverHint: {
      zh: '设置 → 应用 → 权限 → 位置 → 始终允许',
      en: 'Settings → Apps → Permissions → Location → Allow all the time',
    },
  },
}

/**
 * Look up the localized copy for a given permission and locale.
 * Falls back to English if the locale or permission is unknown.
 *
 * @param {keyof typeof PERMISSIONS | string} permissionId
 * @param {'zh' | 'en'} [locale]
 */
export function getPermissionCopy(permissionId, locale = 'zh') {
  const entry = PERMISSIONS[permissionId]
  if (!entry) return null
  const lang = entry.rationale[locale] ? locale : 'en'
  return {
    id: entry.id,
    icon: entry.icon,
    rationale: entry.rationale[lang],
    denied: entry.denied[lang],
    recoverHint: entry.recoverHint[lang],
  }
}

export function listPermissionIds() {
  return Object.keys(PERMISSIONS)
}
