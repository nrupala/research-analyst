// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Research Analyst - Capacitor configuration (plain JS; no TypeScript required).
 *
 * Deliberately a .js config, not .ts, so the Capacitor CLI never needs a
 * TypeScript install to read it. (`npx cap add android` failed in CI with
 * "Could not find installation of TypeScript" when the config was .ts.)
 *
 * The web UI in /ui is the source of truth. Distribution: F-Droid + direct APK
 * on ra.devinfo.dev (and the aimlds.org mirror). Play Store is skipped.
 *
 * Build APK (see docs/ANDROID_BUILD.md):
 *   npx cap add android && npx cap sync android && (cd android && ./gradlew assembleDebug)
 */
const config = {
  appId: "com.research.analyst",
  appName: "Research Analyst",
  webDir: "ui",
  server: {
    // Production: the WebView loads the live site over HTTPS.
    // (Was http://127.0.0.1:8700 - a dev-only box-local origin that would
    // fail on a real device.)
    url: "https://ra.devinfo.dev",
    cleartext: false,
  },
  android: {
    // Minimum Android 8.0 (API 26) for modern web features.
    minSdkVersion: 26,
  },
  ios: {
    // iOS/macOS are PWA-only; this block is kept for parity, no IPA is built.
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

module.exports = config;
