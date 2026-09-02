#!/usr/bin/env bash
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