# Privacy Policy

**App name**: Species Monitoring Survey (hereinafter "the App")
**Package / Bundle ID**: `org.biodiversity.speciesmonitoring`
**Developer / Operator**: 【TODO: legal entity name】
**Contact email**: 【TODO: contact email】
**Support phone**: 【TODO: support phone (optional)】
**Effective date**: 2026-06-10
**Last updated**: 2026-06-10

---

## 1. Introduction

The App is an **offline-first biodiversity field-survey tool** for research institutions, protected areas, universities, and professional survey teams. We take the security of personal information and field-survey data seriously. This Privacy Policy explains what we collect, how we use, store, share, and protect it, and the rights you have.

Please read this policy carefully before using the App. **By using the App, you acknowledge that you have read and agree to this policy.** If you do not agree, please discontinue use.

> **Important (data storage model)**: The App's core survey features run in a **local, offline (hybrid-local) mode**. Observations, transect tracks, photos, and audio you record are **stored only on your device by default** (the on-device database and file system) and are **not** automatically uploaded to our servers. Data is transmitted to your organization's designated server only when you explicitly configure a backend endpoint and run "Sync".

## 2. Scope and Intended Users

- The App is **intended for adult professionals** (researchers, protected-area staff, trained surveyors, etc.).
- The App is **not directed to children** and does not knowingly collect personal information from minors. If we learn we have collected such data, we will delete it promptly.

## 3. Information We Collect

We follow the principle of **data minimization**. The following table lists the categories the App may process:

| Data type | Collected | How | Purpose | Required | Storage | Shared w/ 3rd party |
| --- | --- | --- | --- | --- | --- | --- |
| Location (GPS lat/lon, accuracy) | Yes | When you start recording a transect / mark an observation | Record coordinates, draw tracks, map positioning | Core feature | Device-local; sent to your org server on sync | No |
| Audio (field recordings) | Yes (user-initiated) | When you tap record | Bioacoustic evidence attachment | Optional evidence | Device-local; sent on sync | No |
| Images (camera / gallery) | Yes (user-initiated) | When you take a photo / pick an image as evidence | Visual evidence attachment | Optional evidence | Device-local; sent on sync | No |
| Survey business data (species, count, habitat, weather, notes) | Yes | Manually entered by you | Build survey records | Core feature | Device-local; sent on sync | No |
| Device & network status | Yes | System API | Detect offline/online, gate sync | Required | Device-local, not uploaded | No |
| Admin PIN verifier | Yes | When you set an admin PIN | Protect sensitive ops (e.g. project/site deletion) | Required (local only) | Device-local (hashed, no plaintext) | No |
| Crash / diagnostic logs | 【TODO: enabled?】 | Automatic | Debug crashes/errors | No | 【TODO】 | 【TODO: 3rd-party crash SDK?】 |

We do **not** collect: contacts, SMS, call logs, advertising identifiers (IMEI/MAC for ad tracking), or biometrics. The App contains **no third-party advertising SDKs**.

## 4. Third-Party Services & Outbound Data

| Third party | Trigger | Data sent | Notes |
| --- | --- | --- | --- |
| Map tile service (OpenStreetMap tiles, or your org's tile proxy) | When the map is displayed | Tile requests for the current viewport (approx. coordinates), IP address | Used only to load map tiles; the tile provider has its own privacy policy |
| Your organization's backend server | When you configure an `API endpoint` and run Sync | Your survey business data and attachments | The server is controlled by your organization; we, as the software provider, do not host that data |

Apart from the above, we do **not** sell, rent, or share your personal information with any third party.

## 5. How We Use Information

We use collected information to:
1. provide core features such as survey records, transect tracks, and evidence attachments;
2. position and display observations on the map;
3. synchronize local data to your organization's server when you initiate it;
4. keep the App secure and stable (e.g. local PIN protection for sensitive operations).

We do **not** use this information for user profiling, targeted marketing, or advertising.

## 6. Storage & Security

- **Location**: Stored locally on your device (within the app sandbox's database and file directories) by default. Business data is transmitted to your organization's server only when you initiate sync.
- **Retention**: Local data is under your control — uninstalling the App or deleting in-app clears it; the retention period for data synced to an organization server is governed by that organization's policy.
- **Transport security**: Network communication with backend servers requires HTTPS (production enforces `https://`).
- **Access control**: Sensitive deletion operations (projects/sites) are protected by a device-local admin PIN; the PIN is stored only as a hash, never in plaintext, and is never uploaded.

## 7. Your Rights

- **Access & export**: View the survey data you entered and export it in-app.
- **Correction**: Edit and correct your entered data in-app.
- **Delete a record**: Delete individual observations, transects, or attachments in-app.
- **Delete all / account closure**: See "Account Closure & Data Deletion" below.

### Account Closure & Data Deletion

- **Local data deletion**: Go to **Settings → Privacy & Data → Clear local data** to wipe all survey data on this device, or simply uninstall the App.
- **Organization-server data deletion**: If you previously synced data to an organization server, submit a request via **Settings → Privacy & Data → Request data deletion**, or email **【TODO: contact email】**.
- **Service level (SLA)**: We will respond and complete deletion within **15 business days** of receiving the request (except where retention is legally mandated).
- **Accounts**: The App currently **does not require account registration**; core features run under a device-local identity. If your organization enabled accounts, contact that organization's administrator to close them.

## 8. Permissions

The system permissions the App requests and their purposes are detailed in the accompanying "Per-Permission Justification" document. All sensitive permissions are requested when you **first trigger the related feature**, with a pre-prompt explanation beforehand. **Denying a permission does not prevent the App from launching** — only the related feature becomes unavailable while everything else degrades gracefully.

## 9. Children's Privacy

The App targets adult professionals, is not directed at minors, and does not knowingly collect minors' personal information. Guardians who believe a minor has provided us personal information should contact us for deletion.

## 10. Updates

We may update this policy from time to time. Material changes will be announced via in-app notice or by updating this page. The updated policy takes effect upon publication.

## 11. Contact Us

For questions, complaints, or requests regarding this policy or your personal information:
- Email: **【TODO: contact email】**
- Entity: **【TODO: legal entity name】**
- Address: **【TODO: office address (optional)】**
