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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""Stream B / F1.5 — saved scenarios + shareable links.

Semantics under test:
- Saving needs a valid KeyStore key (ownership needs an identity);
  without a key store the feature is dormant (503).
- A key sees, and can delete, ONLY its own scenarios; a foreign id
  is the same 404 as a missing one (no existence leak).
- The share link replays the scenario with NO key — the link is the
  credential — and the run meters to the owner as "shared".
- Deleting a scenario kills its share link.
- Scenarios persist to disk when a path is configured.
"""
# Module: tests/test_scenarios.py

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from research_analyst.entitlements import API_ACCESS, KeyStore, MeteringRecorder
from research_analyst.enums import ReportType, ScenarioType, SecurityType
from research_analyst.models import (
    CapitalAllocation,
    DividendAnalysis,
    ReportOutput,
    ResearchMetadata,
    ResearchResponse,
    RiskMatrix,
    ValuationRange,
    ValuationScenario,
)
from research_analyst.scenarios import MAX_SCENARIOS_PER_KEY, ScenarioStore
from research_analyst.server import _IPRateLimiter, create_app

GENERATED = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def _response(ticker: str) -> ResearchResponse:
    scenario = ValuationScenario(
        scenario_type=ScenarioType.BASE, label="Base Case", assumptions=[],
        revenue_growth=0.08, operating_margin=0.25,
        implied_price_low=110.0, implied_price_high=110.0,
        implied_upside_low=0.10, implied_upside_high=0.10,
    )
    report = ReportOutput(
        report_type=ReportType.COMPREHENSIVE, ticker=ticker,
        title=f"{ticker} — Comprehensive 7-Step Research Report",
        generated_at=GENERATED, sections=[],
        valuation=ValuationRange(
            ticker=ticker, current_price=100.0, scenarios=[scenario],
            primary_methodology="Hybrid (PE + EV/EBITDA)",
        ),
        risk_matrix=RiskMatrix(ticker=ticker, overall_risk_score=4.0),
        capital_allocation=CapitalAllocation(
            ticker=ticker, period="TTM", roic=0.15,
            roic_minus_wacc=0.06, shareholder_yield=0.03,
        ),
        dividend=DividendAnalysis(
            ticker=ticker, pays_dividend=False,
            no_dividend_context="No dividend currently paid.",
        ),
    )
    return ResearchResponse(
        ticker=ticker, security_type=SecurityType.EQUITY,
        company_name=f"{ticker} Inc.", generated_at=GENERATED,
        reports=[report],
        metadata=ResearchMetadata(data_sources=["yfinance (price data)"]),
    )


class _StubOrchestrator:
    def __init__(self):
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        return _response(request.ticker)


def _client(store=None, scenarios=None, metering=None, orchestrator=None):
    app = create_app(
        orchestrator=orchestrator or _StubOrchestrator(),
        rate_limiter=_IPRateLimiter(rate=1000, burst=1000),
        key_store=store,
        metering=metering,
        scenario_store=scenarios,
    )
    return TestClient(app, raise_server_exceptions=False)


def _key(store: KeyStore) -> tuple[str, str]:
    record, raw = store.create("api", {API_ACCESS}, plan="api_pro")
    return record.key_id, raw


# ---------------------------------------------------------------------------
# Store units
# ---------------------------------------------------------------------------


def test_store_crud_and_token_lookup(tmp_path):
    store = ScenarioStore(path=tmp_path / "scenarios.json")
    s = store.create(key_id="k1", name="Base", ticker="AAPL", report_type=None,
                     timeframe="1Y", custom_assumptions={"g": 1})
    assert s is not None
    assert store.list_for_key("k1") == [s]
    assert store.list_for_key("k2") == []
    assert store.by_share_token(s.share_token) is s
    assert store.by_share_token("nope") is None
    assert store.delete(s.scenario_id, "k2") is False  # foreign delete refused
    assert store.delete(s.scenario_id, "k1") is True
    assert store.by_share_token(s.share_token) is None


def test_store_persistence_round_trip(tmp_path):
    path = tmp_path / "scenarios.json"
    store = ScenarioStore(path=path)
    s = store.create(key_id="k1", name="Base", ticker="AAPL", report_type=None,
                     timeframe="1Y", custom_assumptions={})
    assert s is not None
    store2 = ScenarioStore(path=path)
    assert store2.by_share_token(s.share_token) is not None


def test_store_per_key_cap(tmp_path):
    store = ScenarioStore(path=tmp_path / "scenarios.json")
    for i in range(MAX_SCENARIOS_PER_KEY):
        assert store.create(key_id="k1", name=f"s{i}", ticker="AAPL",
                            report_type=None, timeframe="1Y",
                            custom_assumptions={}) is not None
    assert store.create(key_id="k1", name="over", ticker="AAPL", report_type=None,
                        timeframe="1Y", custom_assumptions={}) is None


# ---------------------------------------------------------------------------
# HTTP behavior
# ---------------------------------------------------------------------------


def test_dormant_without_key_store():
    client = _client(store=None)
    assert client.post("/api/scenarios", json={"name": "x", "ticker": "AAPL"}).status_code == 503
    assert client.get("/api/research/shared/whatever").status_code == 503


def test_key_required_and_validated():
    store = KeyStore()
    _, raw = _key(store)
    client = _client(store=store, scenarios=ScenarioStore())
    assert client.post("/api/scenarios", json={"name": "x", "ticker": "AAPL"}).status_code == 401
    bad = client.post("/api/scenarios", json={"name": "x", "ticker": "AAPL"},
                      headers={"x-ra-key": "ra_live_bogus"})
    assert bad.status_code == 401
    ok = client.post("/api/scenarios", json={"name": "", "ticker": "AAPL"},
                     headers={"x-ra-key": raw})
    assert ok.status_code == 400  # empty name
    ok = client.post("/api/scenarios", json={"name": "x", "ticker": "A" * 21},
                     headers={"x-ra-key": raw})
    assert ok.status_code == 400  # ticker fails the API model's validation


def test_create_list_share_delete_flow():
    store = KeyStore()
    owner_id, raw = _key(store)
    _, other_raw = _key(store)
    metering = MeteringRecorder()
    orchestrator = _StubOrchestrator()
    client = _client(store=store, scenarios=ScenarioStore(), metering=metering,
                     orchestrator=orchestrator)

    created = client.post(
        "/api/scenarios",
        json={"name": "Bull case", "ticker": "SHOP.TO",
              "custom_assumptions": {"revenue_growth": 0.2}},
        headers={"x-ra-key": raw},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["ticker"] == "SHOP.TO"
    assert body["share_path"].startswith("/api/research/shared/")
    scenario_id = body["scenario_id"]

    mine = client.get("/api/scenarios", headers={"x-ra-key": raw})
    assert [s["scenario_id"] for s in mine.json()["scenarios"]] == [scenario_id]
    theirs = client.get("/api/scenarios", headers={"x-ra-key": other_raw})
    assert theirs.json()["scenarios"] == []

    # The share link needs no key, replays the saved assumptions,
    # and meters to the owner.
    shared = client.get(body["share_path"])
    assert shared.status_code == 200
    assert shared.json()["ticker"] == "SHOP.TO"
    assert orchestrator.requests[-1].custom_assumptions == {"revenue_growth": 0.2}
    assert metering.month_usage(owner_id).get("shared") == 1

    # F1.6 formats ride the share link too.
    as_csv = client.get(body["share_path"] + "?format=csv")
    assert as_csv.status_code == 200
    assert as_csv.headers["content-type"].startswith("text/csv")

    # Foreign delete is a 404; owner delete works and kills the link.
    foreign = client.delete(f"/api/scenarios/{scenario_id}",
                            headers={"x-ra-key": other_raw})
    assert foreign.status_code == 404
    deleted = client.delete(f"/api/scenarios/{scenario_id}",
                            headers={"x-ra-key": raw})
    assert deleted.status_code == 200
    assert client.get(body["share_path"]).status_code == 404


def test_unknown_share_token_404():
    store = KeyStore()
    _key(store)
    client = _client(store=store, scenarios=ScenarioStore())
    assert client.get("/api/research/shared/does-not-exist").status_code == 404
