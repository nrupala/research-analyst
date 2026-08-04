# Research Analyst — Android APK build

The app ships as a **Capacitor / system-WebView** APK (F-Droid-friendly — no Chrome/TWA
dependency). One web codebase (`ui/`) is the source of truth. **Play Store is intentionally
skipped**; distribution is **F-Droid + direct APK on ra.devinfo.dev (+ the aimlds.org mirror)**.

## Build in CI (recommended — no local Android SDK, no box, no Docker)

The workflow is staged at `deploy/github-actions/android-apk.yml`.

**Activate it once:** copy that file to `.github/workflows/android-apk.yml` using the GitHub
web editor. (The connected API token can't create workflow files, so this single paste is
manual — after that it self-serves.)

**Run it:**
- Actions tab -> "Android APK (debug)" -> **Run workflow**, or
- push a tag: `git tag apk-v0.2.1 && git push origin apk-v0.2.1`

**Output:**
- every run: a downloadable artifact `research-analyst-debug-apk`
- on a tag: a **GitHub Release** with `research-analyst-debug.apk` attached — this is the URL
  the site's "Download APK" button points at.

Produces a **debug-signed** APK: fine for sideloading, not for F-Droid/Play.

## Build locally / on the box

Prereqs: Node >= 18, JDK 17, Android SDK (`ANDROID_HOME` set).
```
./scripts/build_apk.sh debug
adb install android/app/build/outputs/apk/debug/app-debug.apk
```

## Install on a phone (sideload)
1. Settings -> Apps -> Special access -> Install unknown apps -> allow your browser or Files app.
2. Open the APK link on the phone and tap Install (or `adb install research-analyst-debug.apk`).

## What this APK does
A thin Capacitor WebView that loads **https://ra.devinfo.dev** (set in `capacitor.config.ts`
`server.url`). The PWA service worker still caches the shell for offline use.

## F-Droid submission — follow-up (NOT done yet)
F-Droid requires a self-contained, reproducible build with fully-FOSS deps:
1. Drop `server.url` and **bundle** `ui/` into the APK; switch `app.js`'s API base to an absolute
   `https://ra.devinfo.dev/api` so bundled assets still reach the backend.
2. Generate a real upload keystore (template: `keystore.properties.template`) kept in GitHub
   **Secrets** (never committed); switch CI to `assembleRelease`.
3. Add `fdroiddata` metadata and submit an RFP (merge request) to F-Droid.

The PWA covers Android/iOS/macOS today; this APK adds the F-Droid + direct-download channel.
