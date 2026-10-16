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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""Stream C — first-party telemetry.

Semantics under test:
- The request log line carries ONLY ts/route/method/status/ms/key_id:
  never the raw API key, never a query string, never an IP.
- A valid key logs as its record id; an invalid one as "invalid";
  no key as "anonymous".
- Aggregates answer the pricing questions: requests by route/status
  class, route durations, pipeline runs with avg CPU-seconds, cache
  hit rate, error counts by route + exception type.
- Aggregates persist (restart-safe) and prune past the retention
  window.
- The summary endpoint is dormant (503) until RA_TELEMETRY_ADMIN_KEY
  is set, then requires the X-RA-Admin-Key header (401 otherwise).
- A served research run records one pipeline timing and one cache
  miss; the repeat call records a cache hit.
"""
# Module: tests/test_telemetry.py

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from research_analyst.config import settings
from research_analyst.entitlements import API_ACCESS, KeyStore
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
from research_analyst.server import create_app
from research_analyst.telemetry import TelemetryRecorder


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _log_entries(directory) -> list[dict]:
    path = directory / f"requests-{_today()}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().strip().splitlines() if line]


# ---------------------------------------------------------------------------
# Recorder units
# ---------------------------------------------------------------------------


def test_request_log_line_content_rules(tmp_path):
    rec = TelemetryRecorder(directory=tmp_path)
    rec.record_request(
        route="/api/research", method="POST", status=200,
        duration_ms=12.34, key_id="key_abc",
    )
    entries = _log_entries(tmp_path)
    assert len(entries) == 1
    entry = entries[0]
    assert set(entry) == {"ts", "route", "method", "status", "ms", "key_id"}
    assert entry["route"] == "/api/research"
    assert entry["status"] == 200
    assert entry["key_id"] == "key_abc"


def test_aggregates_and_summary(tmp_path):
    rec = TelemetryRecorder(directory=tmp_path)
    rec.record_request(route="/api/research", method="POST", status=200,
                       duration_ms=100.0, key_id="anonymous")
    rec.record_request(route="/api/research", method="POST", status=500,
                       duration_ms=300.0, key_id="anonymous")
    rec.record_timing("research_pipeline", wall_ms=900.0, cpu_ms=450.0)
    rec.record_cache(True)
    rec.record_cache(False)
    rec.record_cache(True)
    rec.record_error("/api/research", "RuntimeError")
    s = rec.summary()
    assert s["requests_total"] == 2
    assert s["requests"]["/api/research|2xx"] == 1
    assert s["requests"]["/api/research|5xx"] == 1
    assert s["route_durations"]["/api/research"]["count"] == 2
    assert s["route_durations"]["/api/research"]["avg_ms"] == 200.0
    timing = s["pipeline_timings"]["research_pipeline"]
    assert timing["runs"] == 1
    assert timing["avg_cpu_s"] == 0.45
    assert s["cache"]["hits"] == 2
    assert s["cache"]["hit_rate"] == round(2 / 3, 3)
    assert s["errors"]["/api/research|RuntimeError"] == 1


def test_persistence_round_trip(tmp_path):
    rec = TelemetryRecorder(directory=tmp_path)
    rec.record_cache(True)
    rec.record_request(route="/api/health", method="GET", status=200,
                       duration_ms=1.0, key_id="anonymous")
    rec.flush()
    rec2 = TelemetryRecorder(directory=tmp_path)
    assert rec2.summary()["cache"]["hits"] == 1
    assert rec2.summary()["requests_total"] == 1


def test_prune_drops_days_outside_retention(tmp_path):
    (tmp_path / "telemetry.json").write_text(json.dumps({
        "requests": {
            "2000-01-01": {"/api/research|2xx": 5},
            _today(): {"/api/health|2xx": 1},
        },
        "durations": {}, "timings": {}, "cache": {}, "errors": {},
    }))
    rec = TelemetryRecorder(directory=tmp_path, retention_days=90)
    assert rec.summary("2000-01-01")["requests_total"] == 0
    assert rec.summary()["requests_total"] == 1


def test_in_memory_recorder_without_directory():
    rec = TelemetryRecorder(directory=None)
    rec.record_cache(False)
    rec.record_timing("research_pipeline", wall_ms=10.0, cpu_ms=5.0)
    s = rec.summary()
    assert s["cache"]["misses"] == 1
    assert s["cache"]["hit_rate"] == 0.0
    assert s["pipeline_timings"]["research_pipeline"]["runs"] == 1


# ---------------------------------------------------------------------------
# HTTP wiring
# ---------------------------------------------------------------------------


def _make_response(ticker: str) -> ResearchResponse:
    scenario = ValuationScenario(
        scenario_type=ScenarioType.BASE,
        label="Base Case",
        assumptions=[],
        revenue_growth=0.08,
        operating_margin=0.25,
        implied_price_low=110.0,
        implied_price_high=110.0,
        implied_upside_low=0.10,
        implied_upside_high=0.10,
    )
    report = ReportOutput(
        report_type=ReportType.COMPREHENSIVE,
        ticker=ticker,
        title=f"{ticker} — Comprehensive 7-Step Research Report",
        generated_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        sections=[],
        valuation=ValuationRange(
            ticker=ticker,
            current_price=100.0,
            scenarios=[scenario],
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
        ticker=ticker,
        security_type=SecurityType.EQUITY,
        company_name=f"{ticker} Inc.",
        generated_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        reports=[report],
        metadata=ResearchMetadata(data_sources=["Nasdaq (price data)"]),
    )


class _GoodOrchestrator:
    async def run(self, request):
        return _make_response(request.ticker)


class _BoomOrchestrator:
    async def run(self, request):  # noqa: ARG002
        raise RuntimeError("boom")


def _client(tmp_path, orchestrator, store=None):
    recorder = TelemetryRecorder(directory=tmp_path)
    app = create_app(orchestrator=orchestrator, key_store=store, telemetry=recorder)
    return TestClient(app, raise_server_exceptions=False), recorder


def test_valid_key_logs_record_id_never_raw_key(tmp_path):
    store = KeyStore()
    record, raw = store.create("api", {API_ACCESS}, plan="api_pro")
    client, _ = _client(tmp_path, _BoomOrchestrator(), store=store)
    resp = client.post("/api/research", json={"ticker": "AAA"},
                       headers={"x-ra-key": raw})
    assert resp.status_code == 500  # admitted; pipeline boomed
    entries = _log_entries(tmp_path)
    research_entries = [e for e in entries if e["route"] == "/api/research"]
    assert research_entries[-1]["key_id"] == record.key_id
    assert raw not in (tmp_path / f"requests-{_today()}.jsonl").read_text()


def test_invalid_key_logs_invalid_never_raw_key(tmp_path):
    store = KeyStore()
    client, _ = _client(tmp_path, _BoomOrchestrator(), store=store)
    resp = client.post("/api/research", json={"ticker": "AAA"},
                       headers={"x-ra-key": "ra_live_bogus"})
    assert resp.status_code == 401
    entries = _log_entries(tmp_path)
    assert entries[-1]["key_id"] == "invalid"
    assert "bogus" not in json.dumps(entries)


def test_anonymous_request_and_pipeline_error_counted(tmp_path):
    client, recorder = _client(tmp_path, _BoomOrchestrator())
    resp = client.post("/api/research", json={"ticker": "AAA"})
    assert resp.status_code == 500
    entries = _log_entries(tmp_path)
    assert entries[-1]["key_id"] == "anonymous"
    s = recorder.summary()
    assert s["errors"]["/api/research|RuntimeError"] == 1
    assert s["requests"]["/api/research|5xx"] == 1


def test_research_run_records_timing_and_cache(tmp_path):
    client, recorder = _client(tmp_path, _GoodOrchestrator())
    assert client.post("/api/research", json={"ticker": "AAA"}).status_code == 200
    assert client.post("/api/research", json={"ticker": "AAA"}).status_code == 200
    s = recorder.summary()
    assert s["pipeline_timings"]["research_pipeline"]["runs"] == 1
    assert s["cache"]["misses"] == 1
    assert s["cache"]["hits"] == 1
    assert s["cache"]["hit_rate"] == 0.5


# ---------------------------------------------------------------------------
# Operator summary endpoint
# ---------------------------------------------------------------------------


def test_summary_endpoint_dormant_without_admin_key(tmp_path):
    client, _ = _client(tmp_path, _BoomOrchestrator())
    assert client.get("/api/telemetry/summary").status_code == 503


def test_summary_endpoint_requires_admin_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.telemetry, "admin_key", "test-admin")
    client, _ = _client(tmp_path, _BoomOrchestrator())
    assert client.get("/api/telemetry/summary").status_code == 401
    assert client.get(
        "/api/telemetry/summary", headers={"x-ra-admin-key": "wrong"}
    ).status_code == 401
    client.get("/api/health")
    resp = client.get("/api/telemetry/summary",
                      headers={"x-ra-admin-key": "test-admin"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["requests_total"] >= 1
    assert "/api/health|2xx" in body["requests"]
    bad = client.get("/api/telemetry/summary?day=15-10-2026",
                     headers={"x-ra-admin-key": "test-admin"})
    assert bad.status_code == 400
