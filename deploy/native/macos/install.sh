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

# Install Research Analyst as a launchd user agent on macOS.
# NOTE: the PWA webapp (ra.devinfo.dev, installable, offline-capable) is the
# PRIMARY macOS surface — this native launchd path is optional for users who
# want a local always-on instance (e.g. sync jobs, local TUI/API).
set -euo pipefail

APP_DIR="${1:-$HOME/research-analyst}"
LAUNCH_DIR="$HOME/Library/LaunchAgents"

echo "Installing RA native service (launchd) from $APP_DIR"
if [ ! -d "$APP_DIR" ]; then
  echo "Cloning repository..."
  git clone https://github.com/nrupala/research-analyst.git "$APP_DIR"
fi

cd "$APP_DIR"
echo "Creating venv + installing..."
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install .

mkdir -p "$LAUNCH_DIR" "$HOME/Library/Logs"

# Render the plist with the real python path + app dir
sed -e "s|/usr/local/bin/python3|$APP_DIR/.venv/bin/python3|" \
    -e "s|/opt/research-analyst|$APP_DIR|g" \
    deploy/native/macos/com.researchanalyst.ra.plist > "$LAUNCH_DIR/com.researchanalyst.ra.plist"

launchctl load "$LAUNCH_DIR/com.researchanalyst.ra.plist"
echo "Loaded. Verify: launchctl list | grep researchanalyst"
echo "Health:   curl -s http://127.0.0.1:8700/api/health"
echo
echo "Primary macOS surface reminder: the installable PWA at"
echo "  https://ra.devinfo.dev  (Chrome/Safari: Install app) needs no native install."