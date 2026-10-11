# Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#\!/usr/bin/env bash
# Research Analyst — APK Build Script
# Module: scripts/build_apk.sh | Version: 0.1.0 | Updated: 2026-05-15
#
# Prerequisites:
#   - Node.js >= 18
#   - Android Studio with SDK (or standalone SDK tools)
#   - Java 17+ (for Gradle)
#   - ANDROID_HOME environment variable set
#
# Usage:
#   ./scripts/build_apk.sh debug     # Debug APK (no signing)
#   ./scripts/build_apk.sh release   # Release APK (requires keystore)
#   ./scripts/build_apk.sh bundle    # AAB for Play Store

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_TYPE="${1:-debug}"

cd "$PROJECT_ROOT"

echo "============================================"
echo "Research Analyst — APK Build ($BUILD_TYPE)"
echo "============================================"
echo ""

# --- Step 1: Check prerequisites ---
echo "[1/5] Checking prerequisites..."

command -v node >/dev/null 2>&1 || { echo "ERROR: Node.js not found. Install Node >= 18."; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "ERROR: npm not found."; exit 1; }

NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "ERROR: Node.js >= 18 required. Found: $(node -v)"
    exit 1
fi

if [ -z "${ANDROID_HOME:-}" ]; then
    # Try common locations
    if [ -d "$HOME/Android/Sdk" ]; then
        export ANDROID_HOME="$HOME/Android/Sdk"
    elif [ -d "$HOME/Library/Android/sdk" ]; then
        export ANDROID_HOME="$HOME/Library/Android/sdk"
    else
        echo "WARNING: ANDROID_HOME not set. Android build may fail."
    fi
fi

echo "  Node: $(node -v)"
echo "  npm: $(npm -v)"
echo "  ANDROID_HOME: ${ANDROID_HOME:-not set}"
echo ""

# --- Step 2: Install npm dependencies ---
echo "[2/5] Installing dependencies..."
npm ci --prefer-offline 2>/dev/null || npm install
echo ""

# --- Step 3: Initialize Capacitor (if not done) ---
echo "[3/5] Syncing Capacitor..."
if [ \! -d "android" ]; then
    echo "  Adding Android platform..."
    npx cap add android
fi
npx cap sync android
echo ""

# --- Step 4: Build APK ---
echo "[4/5] Building APK ($BUILD_TYPE)..."
cd android

case "$BUILD_TYPE" in
    debug)
        ./gradlew assembleDebug
        APK_PATH="app/build/outputs/apk/debug/app-debug.apk"
        ;;
    release)
        if [ \! -f "$PROJECT_ROOT/keystore.properties" ]; then
            echo "ERROR: keystore.properties not found for release build."
            echo "Create it from keystore.properties.template"
            exit 1
        fi
        ./gradlew assembleRelease
        APK_PATH="app/build/outputs/apk/release/app-release.apk"
        ;;
    bundle)
        if [ \! -f "$PROJECT_ROOT/keystore.properties" ]; then
            echo "ERROR: keystore.properties not found for bundle build."
            exit 1
        fi
        ./gradlew bundleRelease
        APK_PATH="app/build/outputs/bundle/release/app-release.aab"
        ;;
    *)
        echo "ERROR: Unknown build type '$BUILD_TYPE'. Use: debug, release, bundle"
        exit 1
        ;;
esac

cd "$PROJECT_ROOT"
echo ""

# --- Step 5: Report ---
echo "[5/5] Build complete"
echo ""

if [ -f "android/$APK_PATH" ]; then
    SIZE=$(du -h "android/$APK_PATH" | cut -f1)
    echo "  Output: android/$APK_PATH ($SIZE)"
    echo ""
    echo "  Install on device:"
    echo "    adb install android/$APK_PATH"
else
    echo "  WARNING: Expected output not found at android/$APK_PATH"
    echo "  Check the Gradle output above for errors."
fi

echo ""
echo "============================================"
echo "Done."
echo "============================================"
