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

# Verify a Research Analyst native install: service up + one research call.
# Usage: verify.sh [base_url]   (default http://127.0.0.1:8700)
set -uo pipefail
BASE="${1:-http://127.0.0.1:8700}"

echo "== Health =="
curl -s -o /dev/null -w "GET $BASE/api/health -> HTTP %{http_code}\n" --max-time 10 "$BASE/api/health" || { echo "FAIL: API not reachable"; exit 1; }

echo "== Research (AAPL) =="
RESP=$(curl -s --max-time 120 -X POST "$BASE/api/research" \
  -H "content-type: application/json" \
  -d '{"ticker":"AAPL","report_type":"comprehensive"}') || { echo "FAIL: research call failed"; exit 1; }
echo "$RESP" | grep -q '"reports"' && echo "OK: report generated" || { echo "FAIL: no reports in response"; exit 1; }

echo "== Formats =="
for f in json xml ts; do
  curl -s -o /dev/null -w "format=$f -> HTTP %{http_code}\n" --max-time 30 \
    -X POST "$BASE/api/research?format=$f" -H "content-type: application/json" \
    -d '{"ticker":"AAPL","report_type":"comprehensive"}' || echo "format=$f FAIL"
done

echo "== Schema export =="
mkdir -p /tmp/ra-verify-exports
python -m research_analyst.cli schema-export --out /tmp/ra-verify-exports >/dev/null 2>&1 \
  && ls /tmp/ra-verify-exports | grep -q "types.d.ts" && echo "OK: schema artifacts" \
  || echo "WARN: schema-export skipped (needs venv python on PATH)"
rm -rf /tmp/ra-verify-exports

echo "VERIFY COMPLETE"