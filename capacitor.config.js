// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.
//
// A separate commercial license is available for uses incompatible with
// the AGPL-3.0. See COMMERCIAL-LICENSE.md.

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
