/**
 * Research Analyst — Capacitor Configuration
 *
 * Builds a native APK (Android) from the same web codebase. The web UI in /ui
 * is the source of truth. Distribution: F-Droid + direct APK on ra.devinfo.dev
 * (and the aimlds.org mirror). Play Store is intentionally skipped.
 *
 * Build APK (see docs/ANDROID_BUILD.md):
 *   npx cap add android
 *   npx cap sync android
 *   cd android && ./gradlew assembleDebug
 */

import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
    appId: "com.research.analyst",
    appName: "Research Analyst",
    webDir: "ui",
    server: {
        // PRODUCTION: the WebView loads the live site over HTTPS.
        // (Was http://127.0.0.1:8700 — a dev-only box-local origin that would
        // fail on a real device. Fixed for shippable builds.)
        url: "https://ra.devinfo.dev",
        cleartext: false,
        // F-Droid follow-up: for a self-contained, reproducible build, drop
        // `server.url` entirely, bundle /ui into the APK, and point app.js's
        // API base at https://ra.devinfo.dev/api. See docs/ANDROID_BUILD.md.
    },
    android: {
        // Minimum Android 8.0 (API 26) for modern web features
        minSdkVersion: 26,
        buildOptions: {
            keystorePath: undefined,
            keystoreAlias: undefined,
        },
    },
    ios: {
        // iOS/macOS are PWA-only (no Apple Developer Program) — this block is
        // kept for parity but no IPA is built.
        minVersion: "15.0",
        scheme: "Research Analyst",
    },
    plugins: {
        SplashScreen: {
            launchShowDuration: 2000,
            backgroundColor: "#0f172a",
            showSpinner: false,
        },
        StatusBar: {
            style: "DARK",
            backgroundColor: "#0f172a",
        },
    },
};

export default config;
