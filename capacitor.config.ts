/**
 * Research Analyst -- Capacitor Configuration
 *
 * Enables building native APK (Android) and IPA (iOS) from the same
 * web codebase. The web UI in /ui is the source of truth.
 *
 * Setup:
 *   npm init -y
 *   npm install @capacitor/core @capacitor/cli @capacitor/android @capacitor/ios
 *   npx cap sync
 *
 * Build APK:
 *   npx cap sync android
 *   cd android && ./gradlew assembleDebug
 *
 * Build iOS:
 *   npx cap sync ios
 *   npx cap open ios   // Opens Xcode
 */

import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
    appId: "com.research.analyst",
    appName: "Research Analyst",
    webDir: "ui",
    server: {
        url: "http://127.0.0.1:8700",
        cleartext: true,
    },
    android: {
        minSdkVersion: 26,
        buildOptions: {
            keystorePath: undefined,
            keystoreAlias: undefined,
        },
    },
    ios: {
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
