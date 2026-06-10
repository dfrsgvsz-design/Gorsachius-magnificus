# Mapping Archive

Per-release R8/ProGuard `mapping.txt` archive for `scripts/deobfuscate.ps1`.

## Layout

```
submission/_mapping_archive/
├── README.md              ← this file
├── 10000/                 ← versionCode 10000 (= versionName 1.0.0)
│   └── mapping.txt
├── 10001/                 ← versionCode 10001 (= versionName 1.0.1)
│   └── mapping.txt
└── ...
```

## Workflow

After every successful `gradlew bundleRelease` (local or CI), do BOTH of
the following (or use the one wrapper script `scripts/archive_mapping.ps1`
contributed by B, which currently handles the B-side path — see "Path
reconciliation" below).

```powershell
$versionCode = 10000   # match frontend/android/app/build.gradle versionCode
$versionName = "1.0.0" # match versionName

# 1) C convention: keyed by versionCode (required by scripts/deobfuscate.ps1)
$dest = "f:\Gorsachius magnificus\submission\_mapping_archive\$versionCode"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Copy-Item `
  "f:\Gorsachius magnificus\species_monitoring_platform\frontend\android\app\build\outputs\mapping\release\mapping.txt" `
  "$dest\mapping.txt"

# 2) B convention: keyed by versionName + date (release-log friendly)
powershell -ExecutionPolicy Bypass -File `
  "f:\Gorsachius magnificus\scripts\archive_mapping.ps1" -Version $versionName

git add submission/_mapping_archive submission/playstore
git commit -m "chore(mapping): archive versionCode $versionCode (versionName $versionName)"
```

The `.github/workflows/android-release.yml` upload step also captures mapping
as a CI artifact, but **that artifact expires** (default 90 days for free
GitHub plans). The repo archive is the long-term record. **Both repo paths
must exist.**

## Path reconciliation (C × B, 2026-06)

Two scripts independently produced mapping archives at two different paths:

| Script | Path | Key | Author |
|---|---|---|---|
| `scripts/deobfuscate.ps1` | `submission/_mapping_archive/<versionCode>/mapping.txt` | versionCode (10000) | C |
| `scripts/archive_mapping.ps1` | `submission/playstore/mapping_<versionName>_<YYYY-MM-DD>.txt` | versionName (1.0.0) + date | B |

**The state today** (2026-06): both scripts are in the repo; `deobfuscate.ps1`
has been taught to **fall back** to B's path when called with `-VersionName`:

```powershell
# Primary lookup (versionCode):
.\scripts\deobfuscate.ps1 -VersionCode 10001 -StackFile crash.txt

# Fallback when only versionName is known:
.\scripts\deobfuscate.ps1 -VersionName "1.0.1" -StackFile crash.txt

# Direct mapping file (e.g. one pulled fresh from Play Console):
.\scripts\deobfuscate.ps1 -MappingFile "<path>" -StackFile crash.txt
```

**Long-term plan**: collapse to ONE path. Crash reports key on versionCode,
so `_mapping_archive/<versionCode>/mapping.txt` should be the canonical
location. B and C to converge by W4: extend `archive_mapping.ps1` to
also write the versionCode-keyed copy, or deprecate the playstore-flat
layout entirely. Until then, the fallback above prevents lost de-obfuscation.

## Why per-versionCode and not per-tag

versionCode is the immutable Play Console identifier. Tags can be re-cut /
re-tagged; versionCode is monotonic and uniquely identifies an APK / AAB
artifact. When a crash comes back from a real user, what we have is the
versionCode (in the crash report) — not the git tag — so the archive must
be keyed by versionCode for fast lookup.

## Sensitive?

`mapping.txt` is not a secret — it's an obfuscation reversal table. Anyone
with the APK and this file can de-obfuscate stack traces. But it does
contain your class/method names, which leak some internal structure. **Keep
this archive in the private repo; do NOT publish to a public mirror.**
