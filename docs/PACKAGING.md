<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Research Analyst — Packaging Plan (PWA → Android → iOS)

Phased plan. **Recommended sequence: PWA now (shipped) → Android TWA → iOS.** One web codebase
(`ui/`) is the source of truth for all three surfaces; do not fork the UI per platform.

---

## 0. Current scaffolding (already in repo)

- **PWA:** `ui/manifest.json`, `ui/sw.js`, full icon set (72→512, maskable, apple-touch). **Gap fixed
  in PR #8:** the service worker was never registered — now registered, so the app is genuinely
  installable/offline.
- **Capacitor (native wrapper):** `capacitor.config.ts`, `package.json` (Capacitor 6 deps + `cap:*`
  scripts), `scripts/build_apk.sh`, `keystore.properties.template`. This scaffolds a **WebView wrapper**
  for both Android and iOS.
- ⚠️ **Bug to fix before any native build:** `capacitor.config.ts` sets
  `server.url: "http://127.0.0.1:8700"` (dev-only; the box-local origin). A shipped app would try to
  load `127.0.0.1` on the user's phone and fail. For production, either bundle `ui/` and point API
  calls at `https://ra.devinfo.dev/api`, or set `server.url: "https://ra.devinfo.dev"`. Decide per
  surface (see below).

---

## 1. PWA — **done / cheapest** (box-free, ships via Pages)

Installable web app; no store, no review, instant updates.

- **State:** manifest ✅, SW registered ✅ (PR #8), icons ✅, HTTPS ✅ (Pages), 192+512 maskable ✅.
  Meets the install criteria on Chrome/Edge/Android; iOS Safari supports "Add to Home Screen".
- **Remaining polish (optional, small, box-free):**
  - Add a dedicated offline fallback page (`/offline.html`) instead of the generic "Offline" string in
    `sw.js` `cacheFirst`.
  - Add `display_override: ["standalone","minimal-ui"]` and a couple of `screenshots` in the manifest
    to improve the Android install prompt and unlock the richer install UI.
  - Consider `shortcuts` (e.g. "New comparison") in the manifest.
- **Effort:** ~0.5 day. **Cost:** $0. **Review friction:** none. **Native value:** home-screen install,
  offline cached shell + last-viewed reports (already in `sw.js` data cache).

**This is the primary distribution channel.** Everything below wraps this same PWA.

---

## 2. Android — **Trusted Web Activity (TWA) → Google Play** (recommended)

Prefer a **TWA (via Bubblewrap)** over the scaffolded Capacitor WebView wrapper. A TWA renders in the
user's Chrome engine (full PWA capabilities, no WebView drift, automatic updates when the PWA updates),
and Google Play treats installable PWAs favorably. Keep Capacitor for iOS only.

- **Steps:**
  1. `npx @bubblewrap/cli init --manifest https://ra.devinfo.dev/manifest.json`
  2. Host **Digital Asset Links** at `https://ra.devinfo.dev/.well-known/assetlinks.json` (maps the app
     signing-key SHA-256 to the domain, so the URL bar is hidden). This is a small static file — ships
     via Pages, box-free.
  3. Generate an upload keystore (`keytool`; template already at `keystore.properties.template` —
     **never commit the real keystore**). Enroll in **Play App Signing**.
  4. `bubblewrap build` → AAB; upload to Play Console.
- **Effort:** 1–2 days (mostly Play Console listing: description, screenshots, privacy policy, data-safety
  form, content rating). **Cost:** one-time **$25** Google Play developer fee. **Review friction:** low —
  TWAs of real PWAs pass routinely; main asks are a privacy policy + data-safety disclosure.
- **Native value required:** minimal (offline + home-screen already satisfy it). A finance disclaimer +
  privacy policy page are required for the listing.

> The existing `scripts/build_apk.sh` + `capacitor.config.ts` produce a **Capacitor WebView APK** — a
> valid fallback if TWA/Digital Asset Links prove fiddly, but it ships an older WebView and needs the
> `server.url` prod fix. Recommend TWA as primary, Capacitor-APK as backup.

---

## 3. iOS — **Capacitor / WKWebView → App Store** (last, highest friction)

No TWA equivalent on iOS. Use the scaffolded **Capacitor** wrapper (WKWebView) to produce an IPA.

- **Steps:** fix `capacitor.config.ts` for prod (bundle `ui/` or point at `https://ra.devinfo.dev`);
  `npx cap add ios`; `npx cap sync ios`; open in Xcode; set bundle id `com.research.analyst`, signing
  team, icons/splash; Archive → App Store Connect.
- ⚠️ **Apple review risk — Guideline 4.2 ("Minimum Functionality" / "just a repackaged website").** A
  thin WKWebView that only loads the site is a common **rejection**. To pass, add genuine native value:
  - Offline capability (cached reports) — partly there via SW; make it visibly work offline.
  - Native **share sheet** for exporting a report (PDF/HTML).
  - Home-screen presence + splash + native status bar (Capacitor plugins already listed).
  - Ideally **push notifications** for scheduled/emailed reports (ties to the monetization "scheduled
    reports" feature) — this is the strongest 4.2 defense.
- **Effort:** 3–5 days (Xcode setup + at least one real native feature + review iterations). **Cost:**
  **$99/yr** Apple Developer Program; a Mac + Xcode required. **Review friction:** **high** — budget for
  1–2 rejection/resubmit cycles.
- **Native value required:** **mandatory and non-trivial** — do not attempt iOS until at least one of
  {offline reports, native share, push} is real. Otherwise it will be rejected under 4.2.

---

## 4. Summary matrix

| Surface | Distribution | One-time cost | Recurring | Review friction | Native value needed | Effort |
| --- | --- | --- | --- | --- | --- | --- |
| **PWA** | ra.devinfo.dev (Pages) | $0 | $0 | none | install + offline (done) | ~0.5 d |
| **Android TWA** | Google Play | $25 | $0 | low | minimal (+ privacy/data-safety) | 1–2 d |
| **iOS Capacitor** | App Store | $99/yr | $99/yr | **high (Gl. 4.2)** | **real native feature required** | 3–5 d |

## 5. Recommendation

1. **Ship PWA now** (PR #8 merged → installable). Zero cost, immediate cross-platform reach — this is
   the default answer to "Android app + iOS app" for a solo build.
2. **Android TWA next** ($25, ~2 days) once there's a privacy policy + finance disclaimer page. Highest
   ROI store presence.
3. **iOS only after** at least one real native feature exists (push for scheduled reports is the best
   fit and doubles as a paid-tier feature). Don't spend the $99 + Mac + review cycles on a bare
   WKWebView shell.

Fix `capacitor.config.ts` `server.url` before any native build. Keep `ui/` as the single codebase.

---

## Decisions locked (2026-08-04)

- **Domains: both `devinfo.dev` and `aimlds.org`, as co-equal true mirrors.** RA ships on
  `ra.devinfo.dev` **and** `ra.aimlds.org` from the same Pages/Worker projects (`.dev` corporate
  flagging is the reason aimlds.org exists). See `MIRROR-aimlds.md`.
- **Android stores: Play + F-Droid + site install page + direct APK.**
  - **Two build flavors from the same `ui/`:** **Play = TWA** (Chrome engine, best UX);
    **F-Droid = Capacitor / system-WebView** build. Rationale: a TWA depends on Chrome, which F-Droid
    flags as a proprietary dependency (`NonFreeDep` anti-feature); the self-contained WebView build
    avoids that and passes F-Droid's inclusion policy. AGPL core is F-Droid-friendly.
  - **Direct APK** hosted on **GitHub Releases**, linked from the site install page — for
    corporate/sovereign users who can't use Play.
  - F-Droid needs a reproducible build + `fdroiddata` metadata + fully-FOSS deps.
- **iOS / macOS: PWA only** (no Apple Developer Program) — unchanged.
- **Entitlement / paid unlock: API key per email** (not full accounts) — see `MONETIZATION.md`
  (Entitlement model). The app/PWA merely accepts a key, so purchase stays on the web across every
  channel: **zero Apple/Google cut, no store-billing conflict.**
