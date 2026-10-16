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

"""Stream B / F1.6 — export of our analysis (CSV / PDF / embed).

The licensing boundary is under test, not just the formats: exports
carry RA's computed analysis (scenarios, risk, allocation, dividend,
declared sources) and never source data — there is no price-history
or statement content in any export shape. Missing values export as
"Not available", never zero. The embed card is the ONLY framed
surface; every other response keeps X-Frame-Options: DENY.
"""
# Module: tests/test_report_export.py

import csv
import io
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from research_analyst.api_models import ResearchAPIResponse
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
from research_analyst.report_export import embed_card_html, research_csv, research_pdf
from research_analyst.server import _IPRateLimiter, _render_payload, create_app

GENERATED = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
MARKDOWN = "# Reliance Industries — Report\n\n**Current Price:** ₹1,196.00\n\n" + (
    "## Analysis\n\nScenario work with a rupee figure ₹2,000 and growth.\n\n" * 40
)


def _report(ticker: str = "RELIANCE.NS") -> ReportOutput:
    scenario = ValuationScenario(
        scenario_type=ScenarioType.BASE,
        label="Base Case",
        assumptions=[],
        revenue_growth=0.08,
        operating_margin=0.25,
        implied_price_low=110.0,
        implied_price_high=130.0,
        implied_upside_low=0.10,
        implied_upside_high=0.30,
    )
    return ReportOutput(
        report_type=ReportType.COMPREHENSIVE,
        ticker=ticker,
        title=f"{ticker} — Comprehensive 7-Step Research Report",
        generated_at=GENERATED,
        sections=[],
        valuation=ValuationRange(
            ticker=ticker,
            current_price=1196.0,
            scenarios=[scenario],
            primary_methodology="Hybrid (PE + EV/EBITDA)",
        ),
        risk_matrix=RiskMatrix(ticker=ticker, overall_risk_score=4.0),
        capital_allocation=CapitalAllocation(
            ticker=ticker, period="TTM", roic=0.15,
            roic_minus_wacc=0.06, shareholder_yield=0.03,
        ),
        dividend=DividendAnalysis(
            ticker=ticker, pays_dividend=True,
            current_yield=None,  # missing stays missing in exports
            payout_ratio_fcf=0.45, safety_score=80.0,
            dividend_growth_5y_cagr=0.07,
        ),
    )


def _api_response(ticker: str = "RELIANCE.NS") -> ResearchAPIResponse:
    return ResearchAPIResponse(
        request_id="test1234",
        ticker=ticker,
        company_name="Reliance Industries Limited",
        security_type="equity",
        currency="INR",
        reports=[_report(ticker)],
        metadata=ResearchMetadata(
            data_sources=["yfinance (price data)", "Example Filings (statements)"],
            data_as_of="2026-10-14 (previous close)",
        ),
        reports_markdown=[MARKDOWN],
    )


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def test_csv_carries_analysis_tables_and_sources():
    rows = list(csv.reader(io.StringIO(research_csv(_api_response()))))
    assert rows[0] == ["group", "metric", "value"]
    as_dict = {(r[0], r[1]): r[2] for r in rows[1:] if len(r) == 3}
    assert as_dict[("report", "ticker")] == "RELIANCE.NS"
    assert as_dict[("report", "currency")] == "INR"
    assert as_dict[("valuation", "current_price")] == "1196.00"
    assert as_dict[("valuation", "price_source")] == "Yahoo Finance"
    assert as_dict[("valuation", "Base Case — implied price high")] == "130.00"
    assert as_dict[("valuation", "Base Case — implied upside low")] == "10.0%"
    assert as_dict[("risk", "overall_risk_score")] == "4.00"
    assert as_dict[("capital_allocation", "roic")] == "15.0%"
    assert "Example Filings (statements)" in as_dict[("report", "data_sources_declared")]


def test_csv_missing_value_is_not_available_never_zero():
    rows = list(csv.reader(io.StringIO(research_csv(_api_response()))))
    as_dict = {(r[0], r[1]): r[2] for r in rows[1:] if len(r) == 3}
    assert as_dict[("dividend", "current_yield")] == "Not available"


def test_csv_has_no_source_data_groups():
    rows = list(csv.reader(io.StringIO(research_csv(_api_response()))))
    groups = {r[0] for r in rows[1:]}
    assert groups <= {"report", "valuation", "risk", "capital_allocation", "dividend"}


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def test_pdf_is_a_valid_multi_page_document():
    pdf = research_pdf(_api_response())
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    text = pdf.decode("latin-1")
    assert text.count("/Type /Page ") >= 2  # long markdown paginates
    assert "Reliance Industries" in text
    assert "Page 1 of" in text


def test_pdf_maps_rupee_sign_instead_of_corrupting_it():
    pdf = research_pdf(_api_response())
    text = pdf.decode("latin-1")
    assert "\u20b9" not in text  # the raw sign is not WinAnsi-encodable
    assert "Rs. 1,196.00" in text


# ---------------------------------------------------------------------------
# Embed card (unit)
# ---------------------------------------------------------------------------


def test_embed_card_shows_price_source_and_disclaimer():
    card = embed_card_html(_api_response(), app_url="https://ra.aimlds.org")
    assert "₹1196.00" in card  # money() format: no thousands grouping
    assert "(source: Yahoo Finance)" in card
    assert "Base case value range: ₹110.00" in card
    assert "https://ra.aimlds.org" in card
    assert "fonts.googleapis" not in card  # no third-party assets, ever
    assert "http" not in card.split("href=")[0].split("<style>")[1]  # CSS is local


def test_embed_card_escapes_company_name():
    resp = _api_response()
    resp.company_name = "<script>alert(1)</script> Ltd"
    card = embed_card_html(resp, app_url="https://ra.aimlds.org")
    assert "<script>alert(1)</script>" not in card
    assert "&lt;script&gt;" in card


# ---------------------------------------------------------------------------
# HTTP wiring
# ---------------------------------------------------------------------------


class _StubOrchestrator:
    async def run(self, request):
        return ResearchResponse(
            ticker=request.ticker,
            security_type=SecurityType.EQUITY,
            company_name="Reliance Industries Limited",
            currency="INR",
            generated_at=GENERATED,
            reports=[_report(request.ticker)],
            metadata=ResearchMetadata(
                data_sources=["yfinance (price data)"],
                data_as_of="2026-10-14 (previous close)",
            ),
        )


def _client():
    app = create_app(
        orchestrator=_StubOrchestrator(),
        rate_limiter=_IPRateLimiter(rate=1000, burst=1000),
    )
    return TestClient(app, raise_server_exceptions=False)


def test_research_json_now_carries_currency():
    client = _client()
    resp = client.post("/api/research", json={"ticker": "RELIANCE.NS"})
    assert resp.status_code == 200
    assert resp.json()["currency"] == "INR"


def test_research_csv_download():
    client = _client()
    resp = client.post("/api/research?format=csv", json={"ticker": "RELIANCE.NS"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="research-RELIANCE.NS.csv"' in resp.headers["content-disposition"]
    assert "current_price" in resp.text


def test_research_pdf_download():
    client = _client()
    resp = client.post("/api/research?format=pdf", json={"ticker": "RELIANCE.NS"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content.startswith(b"%PDF-1.4")


def test_embed_endpoint_is_the_only_frameable_surface():
    client = _client()
    card = client.get("/api/research/embed", params={"ticker": "RELIANCE.NS"})
    assert card.status_code == 200
    assert card.headers["content-type"].startswith("text/html")
    assert "x-frame-options" not in card.headers
    assert "frame-ancestors *" in card.headers["content-security-policy"]
    assert "x-ra-frame-policy" not in card.headers  # marker consumed server-side
    health = client.get("/api/health")
    assert health.headers["x-frame-options"] == "DENY"


def test_render_payload_rejects_csv_without_content():
    with pytest.raises(HTTPException) as exc:
        _render_payload({}, "csv", "research")
    assert exc.value.status_code == 400


def test_embed_card_recognizes_canonical_declaration_name():
    """Declarations now carry the display name itself (canonical-name
    fix); the card's source note must still resolve."""
    resp = _api_response()
    resp.metadata.data_sources = ["Yahoo Finance (price data)"]
    card = embed_card_html(resp, app_url="https://ra.aimlds.org")
    assert "(source: Yahoo Finance)" in card
