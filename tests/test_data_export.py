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

"""Tests for the source-data bundle export + paid endpoint (Phase 8c-2).

* build_bundle produces a typed, serializable bundle from a ResearchResponse
* bundle_to_csv flattens it (spreadsheet-friendly)
* the /api/research/data endpoint returns JSON/CSV; free for now (2026-09-28:
  the paid-key gate is neutralized)
"""
# Module: tests/test_data_export.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

import json
from datetime import UTC, datetime

from research_analyst.data_export import build_bundle, bundle_to_csv
from research_analyst.enums import ReportType, SecurityType
from research_analyst.models import (
    DividendAnalysis,
    ReportOutput,
    ReportSection,
    ReportVisual,
    ResearchMetadata,
    ResearchResponse,
    ValuationRange,
    ValuationScenario,
)


def _response() -> ResearchResponse:
    scenario = ValuationScenario(
        scenario_type="base", label="Base Case", assumptions=[],
        implied_price_low=100.0, implied_price_high=130.0,
        revenue_growth=0.05, operating_margin=0.18, pe_multiple=20.0,
        ev_ebitda_multiple=None, narrative="",
    )
    valuation = ValuationRange(
        ticker="AAPL", current_price=100.0, primary_methodology="DCF",
        scenarios=[scenario],
    )
    dividend = DividendAnalysis(
        # Real model field names. `payout_ratio` was passed here previously and
        # silently discarded by Pydantic (`extra='ignore'`), which is how a
        # phantom key survived review; the exporter then read the same phantom
        # name and shipped null.
        ticker="AAPL", current_yield=0.025,
        payout_ratio_eps=0.15, payout_ratio_fcf=0.22,
        annual_dividends={"2023": 2.0, "2024": 2.25}, annual_dividend_rate=2.2,
        pays_dividend=True,
    )
    table_visual = ReportVisual(
        visual_type="table", title="Key Metrics",
        content="| Ticker | P/E |\n|---|---:|\n| AAPL | 25.0 |\n| MSFT | 30.0 |",
        ties_to="test",
    )
    section = ReportSection(
        step_number=1, title="Step 1", content="x",
        visuals=[table_visual],
    )
    report = ReportOutput(
        report_type=ReportType.COMPREHENSIVE, ticker="AAPL",
        title="AAPL — Comprehensive",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        sections=[section], valuation=valuation, dividend=dividend,
    )
    return ResearchResponse(
        ticker="AAPL", security_type=SecurityType.EQUITY, company_name="Apple Inc.",
        currency="USD", generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        reports=[report], metadata=ResearchMetadata(data_sources=["stub"]),
    )


def test_build_bundle_shape():
    b = build_bundle(_response())
    assert b["ticker"] == "AAPL"
    assert b["currency"] == "USD"
    assert b["scenarios"][0]["label"] == "Base Case"
    assert b["metrics"]["current_price"] == 100.0
    assert b["metrics"]["dividend_yield"] == 0.025
    assert b["tables"][0]["title"] == "Key Metrics"
    assert b["tables"][0]["rows"][1][0] == "AAPL"


def test_build_bundle_json_serializable():
    b = build_bundle(_response())
    json.dumps(b)  # must not raise


def test_bundle_to_csv_flat():
    csv_text = bundle_to_csv(build_bundle(_response()))
    assert "ticker,company,currency" in csv_text
    assert "AAPL" in csv_text
    assert "scenario" in csv_text.lower() or "scenarios" in csv_text.lower()


# --- paid endpoint ---

import pytest  # noqa: E402

try:
    from fastapi.testclient import TestClient  # noqa: E402

    from research_analyst.server import _IPRateLimiter, create_app  # noqa: E402
    _FASTAPI = True
except Exception:
    TestClient = None
    _FASTAPI = False


def _client(paid_keys: list[str] | None = None):
    import research_analyst.config as cfg

    cfg.settings.billing.paid_keys = paid_keys or []
    return TestClient(create_app(rate_limiter=_IPRateLimiter(rate=1000, burst=1000)))


requires_fastapi = pytest.mark.skipif(
    not _FASTAPI, reason="fastapi not installed"
)


@requires_fastapi
def test_data_endpoint_open_when_no_keys():
    """No paid keys configured -> endpoint open (local/demo mode)."""
    resp = _client([]).post(
        "/api/research/data",
        json={"ticker": "AAPL", "report_type": "comprehensive"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAPL"
    assert "scenarios" in data


@requires_fastapi
def test_data_endpoint_free_when_paid_keys_configured():
    """Everything free for now (2026-09-28): no 401 even with paid keys set.

    The paid-key gate is neutralized; a valid key is still accepted but not
    required.
    """
    client = _client(["secret-key-1"])
    resp = client.post(
        "/api/research/data",
        json={"ticker": "AAPL", "report_type": "comprehensive"},
    )
    assert resp.status_code == 200
    ok = client.post(
        "/api/research/data",
        json={"ticker": "AAPL", "report_type": "comprehensive"},
        headers={"X-RA-Key": "secret-key-1"},
    )
    assert ok.status_code == 200


@requires_fastapi
def test_data_endpoint_csv_format():
    resp = _client([]).post(
        "/api/research/data?format=csv",
        json={"ticker": "AAPL", "report_type": "comprehensive"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "Content-Disposition" in resp.headers
    assert "ticker" in resp.text