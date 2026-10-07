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

"""Tests for multi-ticker comparative reports (v0.2.0).

Offline, deterministic. No network, no yfinance — the single-ticker orchestrator
is replaced with a fake that returns synthetic ResearchResponse objects, so these
tests exercise the real ranking/alignment logic, the /api/compare endpoint, and
the comparative renderer end to end.
"""
# Module: tests/test_comparative.py | Version: 0.2.0 | Updated: 2026-07-18

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from research_analyst.comparative import (
    ComparativeOrchestrator,
    build_comparative_report,
    rank_metric,
)
from research_analyst.enums import ReportType, ScenarioType, SecurityType
from research_analyst.models import (
    CapitalAllocation,
    DividendAnalysis,
    ReportOutput,
    ResearchMetadata,
    ResearchRequest,
    ResearchResponse,
    RiskMatrix,
    ValuationRange,
    ValuationScenario,
)
from research_analyst.reports.comparative_renderer import render_html, render_markdown

# The endpoint tests exercise the FastAPI layer. fastapi/httpx are core deps
# (installed in CI via .github/workflows/ci.yml) but may be absent in a minimal
# offline environment; when they are, only the endpoint tests are skipped — the
# pure ranking/alignment and renderer tests still run.
try:
    from fastapi.testclient import TestClient

    from research_analyst.server import create_app, get_comparative_orchestrator

    _FASTAPI_AVAILABLE = True
except Exception:  # pragma: no cover - only when web deps are unavailable
    TestClient = None  # type: ignore[assignment,misc]
    create_app = None  # type: ignore[assignment]
    get_comparative_orchestrator = None  # type: ignore[assignment]
    _FASTAPI_AVAILABLE = False

requires_fastapi = pytest.mark.skipif(
    not _FASTAPI_AVAILABLE,
    reason="fastapi/httpx not installed in this environment; endpoint tests run in CI",
)


# ---------------------------------------------------------------------------
# Synthetic per-ticker response builder
# ---------------------------------------------------------------------------


def make_response(
    ticker: str,
    *,
    company: str | None = None,
    upside: float | None = 0.10,
    rev_growth: float | None = 0.08,
    op_margin: float | None = 0.25,
    roic: float | None = 0.15,
    roic_minus_wacc: float | None = 0.06,
    shareholder_yield: float | None = 0.03,
    pays_dividend: bool = True,
    div_yield: float | None = 0.025,
    payout_fcf: float | None = 0.45,
    safety: float | None = 80.0,
    div_growth_5y: float | None = 0.07,
    risk_score: float | None = 4.0,
    current_price: float = 100.0,
    sources: list[str] | None = None,
) -> ResearchResponse:
    """Build a comprehensive per-ticker ResearchResponse from scalar inputs."""
    base = ValuationScenario(
        scenario_type=ScenarioType.BASE,
        label="Base Case",
        assumptions=[],
        revenue_growth=rev_growth,
        operating_margin=op_margin,
        implied_price_low=current_price * (1 + (upside or 0)) if upside is not None else None,
        implied_price_high=current_price * (1 + (upside or 0)) if upside is not None else None,
        implied_upside_low=upside,
        implied_upside_high=upside,
    )
    valuation = ValuationRange(
        ticker=ticker,
        current_price=current_price,
        scenarios=[base],
        primary_methodology="Hybrid (PE + EV/EBITDA)",
    )
    capital = CapitalAllocation(
        ticker=ticker,
        period="TTM",
        roic=roic,
        roic_minus_wacc=roic_minus_wacc,
        shareholder_yield=shareholder_yield,
    )
    if pays_dividend:
        dividend = DividendAnalysis(
            ticker=ticker,
            pays_dividend=True,
            current_yield=div_yield,
            payout_ratio_fcf=payout_fcf,
            safety_score=safety,
            dividend_growth_5y_cagr=div_growth_5y,
        )
    else:
        dividend = DividendAnalysis(
            ticker=ticker,
            pays_dividend=False,
            no_dividend_context="Buyback-focused; no dividend currently paid.",
        )

    report = ReportOutput(
        report_type=ReportType.COMPREHENSIVE,
        ticker=ticker,
        title=f"{ticker} — Comprehensive 7-Step Research Report",
        generated_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        sections=[],
        valuation=valuation,
        risk_matrix=RiskMatrix(ticker=ticker, overall_risk_score=risk_score),
        capital_allocation=capital,
        dividend=dividend,
    )
    return ResearchResponse(
        ticker=ticker,
        security_type=SecurityType.EQUITY,
        company_name=company or f"{ticker} Inc.",
        generated_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        reports=[report],
        metadata=ResearchMetadata(
            data_sources=sources
            or ["yfinance (company profile)", "yfinance (financial statements)"],
        ),
    )


class FakeOrchestrator:
    """Stand-in for ResearchOrchestrator: canned responses, raises for invalids."""

    def __init__(self, responses: dict[str, ResearchResponse], invalid: set[str] | None = None):
        self._responses = responses
        self._invalid = invalid or set()

    async def run(self, request: ResearchRequest) -> ResearchResponse:
        ticker = request.ticker
        if ticker in self._invalid or ticker not in self._responses:
            raise ValueError(f"Cannot resolve ticker '{ticker}'.")
        return self._responses[ticker]


def build_client(
    responses: dict[str, ResearchResponse], invalid: set[str] | None = None
) -> TestClient:
    """FastAPI TestClient with the comparative orchestrator overridden by a fake."""
    fake = FakeOrchestrator(responses, invalid=invalid)
    comparative = ComparativeOrchestrator(orchestrator=fake)
    app = create_app()
    app.dependency_overrides[get_comparative_orchestrator] = lambda: comparative
    return TestClient(app)


_ADVICE_WORDS = ["buy", "sell", "hold", "strong buy", "overweight", "underweight"]


def _assert_no_advice(text: str) -> None:
    lowered = text.lower()
    # The only permitted occurrences are the explicit disclaimers that say the
    # tool is NOT giving buy/sell/hold advice.
    assert "buy or sell" in lowered or "buy, sell" in lowered
    for phrase in ("strong buy", "overweight", "underweight"):
        assert phrase not in lowered


# ---------------------------------------------------------------------------
# rank_metric — the pure ranking primitive
# ---------------------------------------------------------------------------


class TestRankMetric:
    def test_higher_is_better_ordering(self) -> None:
        result = rank_metric({"A": 0.30, "B": 0.10, "C": 0.20}, higher_is_better=True)
        assert result["A"].rank == 1 and result["A"].is_winner
        assert result["B"].rank == 3 and not result["B"].is_winner
        assert result["C"].rank == 2
        # Normalized: best -> 100, worst -> 0
        assert result["A"].normalized == 100.0
        assert result["B"].normalized == 0.0
        # Percentile: best beats both others -> 100
        assert result["A"].percentile == 100.0
        assert result["B"].percentile == 0.0

    def test_lower_is_better_ordering(self) -> None:
        # e.g. risk score or payout ratio — lower wins
        result = rank_metric({"A": 8.0, "B": 2.0, "C": 5.0}, higher_is_better=False)
        assert result["B"].rank == 1 and result["B"].is_winner
        assert result["B"].normalized == 100.0
        assert result["A"].rank == 3 and result["A"].normalized == 0.0
        assert not result["A"].is_winner

    def test_ties_share_winner_and_rank(self) -> None:
        result = rank_metric({"A": 5.0, "B": 5.0, "C": 1.0}, higher_is_better=True)
        assert result["A"].is_winner and result["B"].is_winner
        assert not result["C"].is_winner
        assert result["A"].rank == result["B"].rank == 1
        assert result["C"].rank == 2
        # Both tied leaders are >= the other + C -> percentile 100
        assert result["A"].percentile == 100.0

    def test_missing_values_skipped(self) -> None:
        result = rank_metric({"A": 0.2, "B": None, "C": 0.1}, higher_is_better=True)
        assert result["B"].value is None
        assert result["B"].rank is None
        assert result["B"].normalized is None
        assert not result["B"].is_winner
        # Ranking of A and C is unaffected by B's missing value.
        assert result["A"].is_winner and result["A"].rank == 1
        assert result["C"].rank == 2

    def test_single_valid_value(self) -> None:
        result = rank_metric({"A": 0.2, "B": None}, higher_is_better=True)
        assert result["A"].percentile == 100.0
        assert result["A"].normalized == 100.0
        assert result["A"].is_winner

    def test_all_equal_undifferentiated(self) -> None:
        result = rank_metric({"A": 3.0, "B": 3.0}, higher_is_better=True)
        assert result["A"].normalized == 100.0 and result["B"].normalized == 100.0
        assert result["A"].is_winner and result["B"].is_winner

    def test_all_missing(self) -> None:
        result = rank_metric({"A": None, "B": None}, higher_is_better=True)
        assert all(r.value is None and r.rank is None for r in result.values())


# ---------------------------------------------------------------------------
# build_comparative_report — the pure alignment + scorecard layer
# ---------------------------------------------------------------------------


class TestBuildComparativeReport:
    def test_alignment_and_winners(self) -> None:
        responses = [
            make_response("AAA", roic=0.20, div_yield=0.01, risk_score=3.0),
            make_response("BBB", roic=0.10, div_yield=0.04, risk_score=6.0),
        ]
        report = build_comparative_report(responses)
        assert report.tickers == ["AAA", "BBB"]

        by_name = {d.name: d for d in report.dimensions}
        assert "Valuation" in by_name
        assert "Profitability & Capital Quality" in by_name
        assert "Dividend & Income" in by_name
        assert "Risk" in by_name

        roic = next(
            m for m in by_name["Profitability & Capital Quality"].metrics if m.key == "roic"
        )
        assert roic.winners == ["AAA"]  # 0.20 > 0.10
        assert roic.ranks["AAA"] == 1 and roic.ranks["BBB"] == 2

        div = next(m for m in by_name["Dividend & Income"].metrics if m.key == "div_yield")
        assert div.winners == ["BBB"]  # 0.04 > 0.01

        risk = next(m for m in by_name["Risk"].metrics if m.key == "risk_score")
        assert risk.winners == ["AAA"]  # lower risk wins (3 < 6)
        assert risk.higher_is_better is False

        # Scorecard is sorted best-first and every ticker gets an overall score.
        assert report.scorecard[0].overall_score is not None
        assert {r.ticker for r in report.scorecard} == {"AAA", "BBB"}
        assert report.deferred_dimensions  # technical/macro documented as deferred

    def test_current_price_is_not_ranked(self) -> None:
        report = build_comparative_report(
            [make_response("AAA", current_price=50.0), make_response("BBB", current_price=500.0)]
        )
        val = next(d for d in report.dimensions if d.name == "Valuation")
        price = next(m for m in val.metrics if m.key == "current_price")
        assert price.rankable is False
        assert price.winners == []


# ---------------------------------------------------------------------------
# /api/compare endpoint
# ---------------------------------------------------------------------------


@requires_fastapi
class TestCompareEndpoint:
    def test_two_tickers(self) -> None:
        client = build_client({"KO": make_response("KO"), "PEP": make_response("PEP")})
        resp = client.post("/api/compare", json={"tickers": ["KO", "PEP"]})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tickers"] == ["KO", "PEP"]
        assert len(data["report"]["scorecard"]) == 2
        assert len(data["report"]["per_ticker_reports"]) == 2
        assert "informational purposes only" in data["report_markdown"].lower()
        _assert_no_advice(data["report_markdown"])

    def test_five_tickers(self) -> None:
        tickers = ["KO", "PEP", "MDLZ", "KHC", "GIS"]
        responses = {t: make_response(t, roic=0.10 + i * 0.02) for i, t in enumerate(tickers)}
        client = build_client(responses)
        resp = client.post("/api/compare", json={"tickers": tickers})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tickers"] == tickers
        assert len(data["report"]["scorecard"]) == 5
        assert not data["report"]["errors"]

    def test_invalid_ticker_in_set_is_graceful(self) -> None:
        client = build_client(
            {"KO": make_response("KO"), "PEP": make_response("PEP")},
            invalid={"ZZZZ"},
        )
        resp = client.post("/api/compare", json={"tickers": ["KO", "ZZZZ", "PEP"]})
        # Never crashes: the invalid ticker is skipped and recorded.
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tickers"] == ["KO", "PEP"]
        errors = data["report"]["errors"]
        assert len(errors) == 1 and errors[0]["ticker"] == "ZZZZ"
        # The two valid names are still fully ranked.
        assert len(data["report"]["scorecard"]) == 2

    def test_non_dividend_name_in_set(self) -> None:
        client = build_client(
            {
                "KO": make_response("KO", pays_dividend=True, div_yield=0.03),
                "GOOGL": make_response("GOOGL", pays_dividend=False),
            }
        )
        resp = client.post("/api/compare", json={"tickers": ["KO", "GOOGL"]})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        dims = {d["name"]: d for d in data["report"]["dimensions"]}
        div = next(m for m in dims["Dividend & Income"]["metrics"] if m["key"] == "div_yield")
        # Non-payer has no yield: value is None, and the payer wins the metric.
        assert div["values"]["GOOGL"] is None
        assert div["values"]["KO"] is not None
        assert div["winners"] == ["KO"]
        # Both names still scored on the non-dividend dimensions.
        assert all(r["overall_score"] is not None for r in data["report"]["scorecard"])

    def test_count_below_minimum_rejected(self) -> None:
        client = build_client({"KO": make_response("KO")})
        resp = client.post("/api/compare", json={"tickers": ["KO"]})
        assert resp.status_code == 400
        assert "between 2 and 5" in resp.json()["detail"]

    def test_count_above_maximum_rejected(self) -> None:
        client = build_client({t: make_response(t) for t in ["A", "B", "C", "D", "E", "F"]})
        resp = client.post("/api/compare", json={"tickers": ["A", "B", "C", "D", "E", "F"]})
        assert resp.status_code == 400
        assert "between 2 and 5" in resp.json()["detail"]

    def test_duplicate_tickers_collapse(self) -> None:
        client = build_client({"KO": make_response("KO"), "PEP": make_response("PEP")})
        resp = client.post("/api/compare", json={"tickers": ["KO", "ko", "PEP"]})
        assert resp.status_code == 200, resp.text
        assert resp.json()["tickers"] == ["KO", "PEP"]

    def test_research_endpoint_untouched(self) -> None:
        # /api/research must still be registered and independent of /api/compare.
        client = build_client({"KO": make_response("KO"), "PEP": make_response("PEP")})
        routes = {r.path for r in client.app.routes}
        assert "/api/research" in routes
        assert "/api/compare" in routes


# ---------------------------------------------------------------------------
# Renderer — Markdown + self-contained HTML
# ---------------------------------------------------------------------------


class TestComparativeRenderer:
    def _report(self):
        return build_comparative_report(
            [
                make_response("KO", roic=0.18, div_yield=0.03, risk_score=3.0),
                make_response("PEP", roic=0.12, div_yield=0.028, risk_score=4.0),
            ]
        )

    def test_markdown_has_core_sections(self) -> None:
        md = render_markdown(self._report())
        assert "# Comparative Research Report" in md
        assert "## Scorecard" in md
        assert "## Provenance & Data Sources" in md
        assert "informational purposes only" in md.lower()
        assert "Compliance:" in md
        assert "KO" in md and "PEP" in md
        _assert_no_advice(md)

    def test_html_is_self_contained(self) -> None:
        html_doc = render_html(self._report())
        assert html_doc.startswith("<!DOCTYPE html>")
        assert "<html" in html_doc and "</html>" in html_doc
        # Inline styles, no external asset references (fully offline).
        assert "<style>" in html_doc
        assert "http://" not in html_doc.replace("http://www.w3.org", "")  # no external asset URLs
        assert "src=" not in html_doc
        assert "informational purposes only" in html_doc.lower()
        assert "Compliance:" in html_doc
        assert "ra.devinfo.dev" in html_doc  # prepared-on footer
        _assert_no_advice(html_doc)

    def test_html_escapes_content(self) -> None:
        report = build_comparative_report(
            [
                make_response("KO", company="Coca-Cola <script>"),
                make_response("PEP"),
            ]
        )
        html_doc = render_html(report)
        assert "<script>" not in html_doc
        assert "&lt;script&gt;" in html_doc

    def test_source_records_carried_and_enumerated(self) -> None:
        # Issue #74: every named source appears in the comparative report with
        # its reference link — not just a bare label list.
        from research_analyst.models import SourceRecord

        ko = make_response("KO")
        ko.metadata.source_records = [
            SourceRecord(
                name="yfinance (company profile)", url="https://finance.yahoo.com/quote/KO"
            ),
            SourceRecord(
                name="SEC EDGAR (10-K filings)",
                url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=KO&type=10-K",
            ),
        ]
        report = build_comparative_report([ko, make_response("PEP")])
        assert report.source_records["KO"][0].url == "https://finance.yahoo.com/quote/KO"
        md = render_markdown(report)
        assert "[yfinance (company profile)](https://finance.yahoo.com/quote/KO)" in md
        assert "SEC EDGAR (10-K filings)" in md
        html_doc = render_html(report)
        assert 'href="https://finance.yahoo.com/quote/KO"' in html_doc
