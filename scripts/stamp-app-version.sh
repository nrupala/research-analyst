#!/usr/bin/env bash
# Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

# stamp-app-version.sh — STANDARD app versioning (native build-time stamp).
#
# Derives the app version from the release tag (single source of truth) and
# stamps every native surface present in the checkout:
#   Android : android/app/build.gradle -> versionName=X.Y.Z, versionCode=M*10000+m*100+p
#   iOS     : ios/App/App/Info.plist    -> CFBundleShortVersionString=X.Y.Z, CFBundleVersion=code
#
# Web + PWA surfaces are stamped at AUTHOR time by scripts/bump-version.mjs.
# Run this in CI AFTER `npx cap add <platform>` / `cap sync`, BEFORE the platform build.
#
# Version resolution order: $1 arg > $RA_VERSION env > apk-v*/v* tag > package.json.
# See docs/VERSIONING.md for the full standard.
set -euo pipefail

raw="${1:-${RA_VERSION:-}}"
if [ -z "$raw" ] && [ "${GITHUB_REF_TYPE:-}" = "tag" ]; then
  raw="${GITHUB_REF_NAME:-}"
fi
is_tag=1
case "$raw" in
  apk-v*) raw="${raw#apk-v}" ;;
  v*)     raw="${raw#v}" ;;
  "")     raw="$(node -p "require('./package.json').version")"; is_tag=0 ;;
esac

if ! printf '%s' "$raw" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "stamp-app-version: could not resolve a semver X.Y.Z (got '$raw')" >&2
  exit 1
fi

MAJOR="${raw%%.*}"; rest="${raw#*.}"; MINOR="${rest%%.*}"; PATCH="${rest#*.}"
if [ "$MINOR" -ge 100 ] || [ "$PATCH" -ge 100 ]; then
  echo "stamp-app-version: minor/patch must be < 100 for the versionCode scheme (got $raw)" >&2
  exit 1
fi
CODE=$(( MAJOR * 10000 + MINOR * 100 + PATCH ))
NAME="$raw"
[ "$is_tag" -eq 0 ] && NAME="${raw}-dev"

stamped=0

# --- Android ---
GRADLE="android/app/build.gradle"
if [ -f "$GRADLE" ]; then
  sed -i -E "s/versionCode[[:space:]]+[0-9]+/versionCode ${CODE}/" "$GRADLE"
  sed -i -E "s/versionName[[:space:]]+\"[^\"]*\"/versionName \"${NAME}\"/" "$GRADLE"
  echo "android: versionName=${NAME} versionCode=${CODE}"
  grep -E "versionCode|versionName" "$GRADLE" || true
  stamped=1
fi

# --- iOS ---
PLIST="ios/App/App/Info.plist"
if [ -f "$PLIST" ]; then
  if [ -x /usr/libexec/PlistBuddy ]; then
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString ${raw}" "$PLIST" 2>/dev/null \
      || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string ${raw}" "$PLIST"
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${CODE}" "$PLIST" 2>/dev/null \
      || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string ${CODE}" "$PLIST"
  else
    # Portable fallback (Linux CI): replace the <string> value following each key.
    perl -0pi -e "s/(<key>CFBundleShortVersionString<\/key>\s*<string>)[^<]*(<\/string>)/\${1}${raw}\${2}/s" "$PLIST"
    perl -0pi -e "s/(<key>CFBundleVersion<\/key>\s*<string>)[^<]*(<\/string>)/\${1}${CODE}\${2}/s" "$PLIST"
  fi
  echo "ios: CFBundleShortVersionString=${raw} CFBundleVersion=${CODE}"
  stamped=1
fi

if [ "$stamped" -eq 0 ]; then
  echo "stamp-app-version: no native project found (android/ or ios/) — nothing to stamp" >&2
fi
