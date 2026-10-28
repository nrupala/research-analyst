# Copyright (C) 2026 2351485 ALBERTA INC.
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

"""Stream B / F1.2 — the keyed analysis-API lane.

Semantics under test:
- No key header -> the free public lane, untouched.
- A presented key governs by its own entitlements: invalid/revoked 401,
  no `api.access` 403, `api.access` admitted subject to the per-key
  rate cap and the monthly allowance (429 when either is exhausted).
- The allowance counts SERVED calls (metered after the pipeline runs),
  so tests seed the recorder to represent already-served calls.
- /api/usage reports the month truthfully: per-endpoint monthly
  counts, the allowance, and the remaining calls.
- Metering counts persist to disk when a path is configured, so a
  restart never resets a customer's usage.
"""
# Module: tests/test_metered_api.py

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from research_analyst import server as server_mod
from research_analyst.entitlements import (
    API_ACCESS,
    RA_PRO,
    TWF_PRO,
    KeyStore,
    MeteringRecorder,
)
from research_analyst.server import create_app


class _BoomOrchestrator:
    async def run(self, request):  # noqa: ARG002
        raise RuntimeError("STOP — pipeline must not run in gate tests")


def _client(store=None, metering=None):
    app = create_app(
        orchestrator=_BoomOrchestrator(), key_store=store, metering=metering
    )
    return TestClient(app, raise_server_exceptions=False)


def _research(client, raw=None):
    headers = {"x-ra-key": raw} if raw else {}
    return client.post("/api/research", json={"ticker": "AAA"}, headers=headers)


def test_keyless_call_uses_public_lane():
    client = _client()
    assert _research(client).status_code == 500  # admitted; pipeline boomed


def test_api_access_key_admitted():
    store = KeyStore()
    _, raw = store.create("api", {API_ACCESS}, plan="api_pro",
                          monthly_call_allowance=100_000)
    client = _client(store=store)
    assert _research(client, raw).status_code == 500


def test_twf_bundle_key_admitted_via_bundle_api_access():
    store = KeyStore()
    _, raw = store.create("twf", {TWF_PRO})
    client = _client(store=store)
    assert _research(client, raw).status_code == 500


def test_app_only_key_gets_403():
    store = KeyStore()
    _, raw = store.create("app", {RA_PRO}, plan="app_pro")
    client = _client(store=store)
    r = _research(client, raw)
    assert r.status_code == 403
    assert "API access" in r.json()["detail"]


def test_invalid_key_gets_401():
    store = KeyStore()
    store.create("api", {API_ACCESS})
    client = _client(store=store)
    assert _research(client, "ra_live_not_a_real_key").status_code == 401


def test_revoked_key_gets_401():
    store = KeyStore()
    record, raw = store.create("api", {API_ACCESS})
    store.revoke(record.key_id)
    client = _client(store=store)
    assert _research(client, raw).status_code == 401


def test_legacy_paid_key_passes_the_gate(monkeypatch):
    monkeypatch.setattr(server_mod.settings.billing, "paid_keys", ["legacy-1"])
    client = _client()
    assert _research(client, "legacy-1").status_code == 500


def test_allowance_exhausted_gets_429():
    store = KeyStore()
    record, raw = store.create("api", {API_ACCESS}, plan="api_pro",
                               monthly_call_allowance=2)
    metering = MeteringRecorder()
    metering.record(record.key_id, "research")
    metering.record(record.key_id, "research")  # 2 served calls this month
    client = _client(store=store, metering=metering)
    r = _research(client, raw)
    assert r.status_code == 429
    assert "allowance" in r.json()["detail"]


def test_allowance_not_yet_reached_admits():
    store = KeyStore()
    record, raw = store.create("api", {API_ACCESS}, plan="api_pro",
                               monthly_call_allowance=3)
    metering = MeteringRecorder()
    metering.record(record.key_id, "research")
    metering.record(record.key_id, "quant")
    client = _client(store=store, metering=metering)
    assert _research(client, raw).status_code == 500


def test_no_allowance_means_no_allowance_cap():
    store = KeyStore()
    record, raw = store.create("api", {API_ACCESS})
    metering = MeteringRecorder()
    for _ in range(50):
        metering.record(record.key_id, "research")
    client = _client(store=store, metering=metering)
    assert _research(client, raw).status_code == 500


def test_rate_cap_gets_429(monkeypatch):
    monkeypatch.setitem(server_mod._PLAN_RATE_CAPS_PER_MIN, "api_pro", 2)
    store = KeyStore()
    _, raw = store.create("api", {API_ACCESS}, plan="api_pro")
    client = _client(store=store)
    assert _research(client, raw).status_code == 500
    assert _research(client, raw).status_code == 500
    r = _research(client, raw)
    assert r.status_code == 429
    assert "Rate limit" in r.json()["detail"]


def test_usage_reports_month_truthfully():
    store = KeyStore()
    record, raw = store.create("api", {API_ACCESS}, plan="api_team",
                               monthly_call_allowance=1_000_000)
    metering = MeteringRecorder()
    first_of_month = datetime.now(UTC).strftime("%Y-%m-01")
    metering.record(record.key_id, "research")  # today
    metering.record(record.key_id, "research", day=first_of_month)
    metering.record(record.key_id, "quant", day=first_of_month)
    metering.record(record.key_id, "research", day="2020-01-15")  # old month
    client = _client(store=store, metering=metering)
    r = client.get("/api/usage", headers={"x-ra-key": raw})
    assert r.status_code == 200
    data = r.json()
    assert data["plan"] == "api_team"
    assert data["monthly_usage"] == {"research": 2, "quant": 1}
    assert data["monthly_total_requests"] == 3
    assert data["monthly_call_allowance"] == 1_000_000
    assert data["monthly_remaining"] == 1_000_000 - 3
    # Day fields stay for back-compat and count only today.
    assert data["total_requests"] == 1


def test_metering_persistence_round_trip(tmp_path):
    path = tmp_path / "metering.json"
    rec = MeteringRecorder(path=path)
    rec.record("key_a", "research")
    rec.record("key_a", "research", day="2020-01-15")  # ancient bucket
    rec2 = MeteringRecorder(path=path)
    assert rec2.usage("key_a") == {"research": 1}
    # Buckets older than ~92 days are pruned on load by design, so the
    # ancient record does not come back; the current month is intact.
    assert rec2.month_total("key_a", month="2020-01") == 0
    assert rec2.month_total("key_a") == 1


def test_metering_month_aggregation_ignores_other_months():
    rec = MeteringRecorder()
    rec.record("key_a", "research", day="2026-10-02")
    rec.record("key_a", "research", day="2026-10-31")
    rec.record("key_a", "quant", day="2026-09-30")
    assert rec.month_usage("key_a", month="2026-10") == {"research": 2}
    assert rec.month_total("key_a", month="2026-10") == 2
