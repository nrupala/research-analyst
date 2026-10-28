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

"""Server wiring tests for entitlements: retired source-data endpoint, /api/usage, metering.

Offline: the pipeline is stubbed to fail fast so gate behavior (401 vs 500)
can be asserted without running any provider.
"""
# Module: tests/test_entitlements_api.py

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from research_analyst.entitlements import (
    RA_PRO,
    KeyStore,
    MeteringRecorder,
    WhiteLabelProfile,
)
from research_analyst.reports.comparative_renderer import render_html
from research_analyst.server import create_app


class _BoomOrchestrator:
    async def run(self, request):  # noqa: ARG002
        raise RuntimeError("STOP — pipeline must not run in gate tests")


def _app(**kwargs):
    store = kwargs.pop("key_store", None)
    metering = kwargs.pop("metering", None)
    app = create_app(orchestrator=_BoomOrchestrator(), key_store=store, metering=metering)
    return TestClient(app, raise_server_exceptions=False)


def _issue(entitlements):
    store = KeyStore()
    _, raw = store.create("test", entitlements)
    return store, raw


def test_source_data_endpoint_retired():
    # Owner ruling 2026-10-15: source data is never sold or redistributed.
    # The endpoint is gone for everyone — keyed or not.
    client = _app()
    r = client.post("/api/research/data", json={"ticker": "AAA"})
    assert r.status_code == 404


def test_source_data_endpoint_retired_with_store_and_key():
    store, raw = _issue({RA_PRO})
    client = _app(key_store=store)
    r = client.post(
        "/api/research/data", json={"ticker": "AAA"}, headers={"x-ra-key": raw}
    )
    assert r.status_code == 404


def test_public_research_open_when_only_store_configured():
    # H2 (2026-10-15): a KeyStore arms /api/usage only;
    # the free public endpoints must stay open (the UI carries no key).
    store, _ = _issue({RA_PRO})
    client = _app(key_store=store)
    r = client.post("/api/research", json={"ticker": "AAA"})
    assert r.status_code == 500  # gate passed; pipeline boomed


def test_public_research_gated_in_legacy_paid_keys_mode(monkeypatch):
    from research_analyst import server as server_mod

    monkeypatch.setattr(server_mod.settings.billing, "paid_keys", ["legacy-1"])
    client = _app()
    r = client.post("/api/research", json={"ticker": "AAA"})
    assert r.status_code == 401
    r = client.post(
        "/api/research", json={"ticker": "AAA"}, headers={"x-ra-key": "legacy-1"}
    )
    assert r.status_code == 500  # legacy key passes; pipeline boomed


def test_quant_gated_in_legacy_paid_keys_mode(monkeypatch):
    from research_analyst import server as server_mod

    monkeypatch.setattr(server_mod.settings.billing, "paid_keys", ["legacy-1"])
    client = _app()
    r = client.get("/api/research/quant", params={"ticker": "AAA"})
    assert r.status_code == 401  # gate fires before the engine runs


def test_usage_requires_key():
    store, raw = _issue({RA_PRO})
    client = _app(key_store=store)
    assert client.get("/api/usage").status_code == 401
    r = client.get("/api/usage", headers={"x-ra-key": raw})
    assert r.status_code == 200
    data = r.json()
    assert data["entitlements"] == [RA_PRO]
    assert "raw" not in str(data).lower()
    assert data["total_requests"] == 0


def test_usage_reflects_metered_calls():
    store, raw = _issue({RA_PRO})
    metering = MeteringRecorder()
    client = _app(key_store=store, metering=metering)
    headers = {"x-ra-key": raw}
    metering.record("key_x", "research")  # someone else's usage
    record = store.verify(raw)
    metering.record(record.key_id, "resolve")
    r = client.get("/api/usage", headers=headers)
    data = r.json()
    assert data["usage"] == {"resolve": 1}
    assert data["total_requests"] == 1


def test_white_label_footer_chrome_only():
    from research_analyst.comparative import ComparativeReport

    report = ComparativeReport(
        requested_tickers=["AAA"],
        generated_at=datetime(2026, 9, 25, tzinfo=UTC),
        tickers=["AAA"],
    )

    profile = WhiteLabelProfile(
        org_name="Acme Advisory",
        footer_note="Prepared for Acme clients.",
        show_support_link=False,
        accent_color="#0b5fff",
    )
    html = render_html(report, white_label=profile)
    assert "Acme Advisory" in html
    assert "Prepared for Acme clients." in html
    assert "buymeacoffee" not in html.lower()
    assert "#0b5fff" in html
    # Evidence chrome untouched: disclaimer + compliance still present.
    assert "disclaimer" in html.lower()
    assert "Compliance:" in html

    plain = render_html(report)
    assert "ra.devinfo.dev" in plain
    assert "Buy Me a Coffee" in plain
