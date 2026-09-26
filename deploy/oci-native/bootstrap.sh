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

#
# Reloadable image: recreate the Research Analyst OCI-native origin on oracle-aetheris.
# Native systemd + venv + uvicorn behind the existing Cloudflare Tunnel. NO Docker.
#
# Run on the box as a sudo-capable user, from inside the repo:
#   cd /opt/research-analyst/deploy/oci-native && sudo bash bootstrap.sh
# Safe to re-run (idempotent-ish).
#
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

# 1. System user (no login)
sudo useradd --system --no-create-home --shell /usr/sbin/nologin ra 2>/dev/null || true

# 2. Clone / update repo -> /opt/research-analyst
sudo mkdir -p /opt/research-analyst && sudo chown ra:ra /opt/research-analyst
if [ ! -d /opt/research-analyst/.git ]; then
  sudo -u ra git clone https://github.com/nrupala/research-analyst.git /opt/research-analyst
fi
cd /opt/research-analyst
sudo -u ra git checkout main
sudo -u ra git pull --ff-only
sudo -u ra git rev-parse HEAD

# 3. venv + install  (box is Python 3.12.3; all deps ship cp312 aarch64 wheels — nothing compiles)
sudo -u ra python3 -m venv /opt/research-analyst/.venv
sudo -u ra /opt/research-analyst/.venv/bin/pip install -U pip
sudo -u ra /opt/research-analyst/.venv/bin/pip install .

# 4. Persistent cache dir (owned by ra)
sudo mkdir -p /var/lib/research-analyst/cache && sudo chown -R ra:ra /var/lib/research-analyst

# 5. Env file (fill RA_MARKET_FRED_API_KEY on box — see ra.env.example)
sudo mkdir -p /etc/research-analyst
if [ ! -f /etc/research-analyst/ra.env ]; then
  sudo cp "$HERE/ra.env.example" /etc/research-analyst/ra.env
  sudo chown root:ra /etc/research-analyst/ra.env
  sudo chmod 640 /etc/research-analyst/ra.env
  echo ">>> Edit /etc/research-analyst/ra.env and set RA_MARKET_FRED_API_KEY before first start <<<"
fi

# 6. systemd unit -> enable + start
sudo cp "$HERE/ra.service" /etc/systemd/system/ra.service
sudo systemctl daemon-reload
sudo systemctl enable --now ra.service
sleep 4
sudo systemctl status ra.service --no-pager | head -8
curl -s http://127.0.0.1:8700/api/health; echo
# Expect: {"status":"ok","service":"research-analyst","version":"0.2.1"}
#
# FRED stays dormant until the real key is in ra.env AND the service is restarted:
#   sudo systemctl restart ra
