# Play App Signing — 4-step enrollment (B → PM dual-sign)

> **CRITICAL**: enrolling in Play App Signing is **irreversible** for a
> production app. Once Google holds the signing key, you cannot revoke or
> rotate it without filing a key-reset request that can take weeks. Two
> sign-offs are required before clicking "Save" in step 4:
>
> | Sign-off | Who | Date | Initials |
> |---|---|---|---|
> | Engineering Lead (DRI B) |   |   |   |
> | PM / Product Owner       |   |   |   |
>
> Print, sign, file under `submission/governance/` before proceeding.

This document is consumed by the PM. Engineering (DRI B) prepares the artifacts
in section "Pre-flight" and hands the AAB + this checklist to the PM.

---

## Pre-flight (DRI B does this BEFORE the PM session)

1. **Generate a fresh upload key** (used for uploading to Play Console — kept by
   the team, NOT given to Google):

   ```powershell
   keytool -genkey -v `
     -keystore species-monitoring-upload.jks `
     -alias upload `
     -keyalg RSA -keysize 2048 -validity 9125 `
     -storepass "<NEW_STRONG_PASSWORD>" `
     -keypass  "<NEW_STRONG_PASSWORD>" `
     -dname "CN=Species Monitoring, OU=Field Survey, O=<ORG>, L=<CITY>, S=<STATE>, C=CN"
   ```

   Validity is 25 years; matches Google's recommended upload key lifetime.
   Store the .jks file **outside the repo** (the repo .gitignore already blocks
   `*.jks`).

2. **Compute upload-key SHA-256 fingerprint** (PM enters this in step 3):

   ```powershell
   keytool -list -v `
     -keystore species-monitoring-upload.jks `
     -alias upload `
     -storepass "<NEW_STRONG_PASSWORD>" | Select-String "SHA256"
   ```

3. **Configure Gradle to sign release builds with the upload key**. Add to
   `species_monitoring_platform/frontend/android/app/build.gradle` (DO NOT
   commit the actual `keystore.properties` — it is .gitignored):

   ```groovy
   android {
       signingConfigs {
           release {
               storeFile file(System.getenv('UPLOAD_KEYSTORE_PATH') ?: '../keystore/species-monitoring-upload.jks')
               storePassword System.getenv('UPLOAD_KEYSTORE_PASSWORD')
               keyAlias System.getenv('UPLOAD_KEYSTORE_ALIAS') ?: 'upload'
               keyPassword System.getenv('UPLOAD_KEY_PASSWORD')
           }
       }
       buildTypes {
           release {
               signingConfig signingConfigs.release
               minifyEnabled true
               proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
           }
       }
   }
   ```

4. **Build the signed AAB** that will be uploaded in step 4:

   ```powershell
   cd species_monitoring_platform/frontend
   npm run build
   npx cap sync android
   cd android
   ./gradlew bundleRelease
   # Output: app/build/outputs/bundle/release/app-release.aab
   ```

5. **Archive the mapping file** (so future crash reports stay deobfuscatable
   — see `scripts/archive_mapping.ps1`):

   ```powershell
   ../../scripts/archive_mapping.ps1 -Version "1.0.0"
   ```

Hand the PM:
- `app-release.aab`
- This document with sections 1-2 filled in (fingerprint + cert details)
- `submission/playstore/mapping_1.0.0_<date>.txt`

---

## PM session — 4 steps in Play Console (irreversible from step 4 onwards)

### Step 1 — Create the app in Play Console

1. Sign in to <https://play.google.com/console>.
2. **All apps → Create app**.
3. Fill in:
   - App name: `Species Monitoring Survey`
   - Default language: `Chinese (Simplified) – zh-Hans-CN` (English added later)
   - App or game: `App`
   - Free or paid: `Free`
   - Declarations: tick both (developer programme + US export laws).
4. **Create app**.

### Step 2 — Enrol in Play App Signing (BEFORE first AAB upload)

1. **Setup → App signing**.
2. Choose **"Let Google generate and manage your app signing key"** (recommended).
   *Alternative: "Export and upload a key from Java Keystore" — only if you
   already have a production keystore you must keep. Default to Google-managed.*
3. The page will display:
   - **App signing key certificate** — copy SHA-1, SHA-256, MD5 into
     `submission/playstore/app-signing-fingerprints.txt` so reviewers can
     match crash reports.
   - **Upload key certificate** — initially blank; populated by step 3 below.

### Step 3 — Register the upload key fingerprint

1. Still on **Setup → App signing**.
2. Click **"Upload your upload key certificate"** in the *Upload key
   certificate* section.
3. Paste the SHA-256 fingerprint computed in the Pre-flight step 2.
4. Click **Save**. The fingerprint is now bound; future AAB uploads MUST be
   signed by the matching upload key.

### Step 4 — Upload the first AAB and create an internal-testing release

1. **Testing → Internal testing → Create new release**.
2. Click **Upload** and select `app-release.aab` from the Pre-flight.
3. Release name: `1.0.0 internal smoke (Batch B W3)`
4. Release notes (paste):

   ```text
   Initial internal release. Validates Play App Signing + AAB upload pipeline.
   Includes Batch 1+2+3+4+5 frontend deliverables:
     - 5m/3s track denoising
     - Production-grade map with clustering + user location
     - Media capture hooks (camera + audio)
     - Permission rationale infrastructure (4 sensitive perms)
     - Android 14+ background-location compliance scaffold
   See submission/playstore/release-notes-1.0.0.md for full details.
   ```
5. **Save → Review release → Start rollout**.

> **STOP** — Do NOT click "Start rollout" until BOTH sign-offs above are
> initialled. Rollback after this point requires deleting the release and
> uploading a fresh AAB; the signing key is permanently bound to Google.

---

## Post-launch checklist

- [ ] App signing certificate fingerprints filed in
      `submission/playstore/app-signing-fingerprints.txt`
- [ ] Upload key .jks backed up to encrypted cold storage (NOT the repo)
- [ ] `keystore.properties` template added to `submission/governance/` for
      future engineers (no real passwords, just placeholders)
- [ ] `mapping_1.0.0_<date>.txt` archived under `submission/playstore/`
- [ ] FOREGROUND_SERVICE_LOCATION declaration submitted (see
      `playstore_foreground_service_rationale.md`)
- [ ] 30 s screencast uploaded (see same doc)
- [ ] PM and Engineering Lead initialled the dual-sign table at the top

## Why this matters

If the upload key is ever lost, Play Console allows a **one-time key reset**
that takes 7-14 days of human review and blocks all releases during that
window. If the *signing* key were lost (i.e. you opted not to enroll in Play
App Signing), the situation is far worse: every user would have to uninstall
the old app and install a fresh one with a new key. This is the single
biggest reason to enroll, and the single biggest reason to back up the upload
key carefully.
