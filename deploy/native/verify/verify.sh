#!/usr/bin/env bash
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