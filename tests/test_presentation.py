"""Snapshot/regression tests for the presentation layer (Phase 3).

Guards the "institutional, client-ready polish" so it doesn't rot:
  * shared Plotly visual language (palette, base layout, hover) is applied to
    every chart builder,
  * markdown tables use right-aligned, data-friendly alignment rows,
  * HTML/Markdown exports wrap tables in the fluid .table-scroll container so
    the graphical components flow exactly like the top menu on any screen.
"""
# Module: tests/test_presentation.py | Version: 1.0 | Updated: 2026-08-31

from __future__ import annotations

import json
from datetime import UTC, datetime

from research_analyst.enums import ReportType, SecurityType
from research_analyst.models import (
    CompanyProfile,
    FinancialStatement,
    ReportOutput,
    ResearchMetadata,
    ResearchResponse,
    RiskMatrix,
    StructuredRisk,
    ValuationRange,
    ValuationScenario,
)
from research_analyst.reports.visuals import PLOTLY_COLORS, VisualEngine


def _financials(n: int = 3) -> list[FinancialStatement]:
    fs = []
    for i in range(n):
        fs.append(
            FinancialStatement(
                period=f"FY202{n}",
                period_end_date=datetime(2020 + n, 12, 31).date(),
                revenue=50_000_000_000 + i * 10_000_000_000,
                gross_profit=20_000_000_000 + i * 5_000_000_000,
                operating_income=10_000_000_000 + i * 3_000_000_000,
                net_income=8_000_000_000 + i * 2_000_000_000,
                free_cash_flow=9_000_000_000 + i * 2_000_000_000,
                eps_diluted=3.0 + i,
                gross_margin=0.40,
                operating_margin=0.20,
                net_margin=0.16,
                roe=0.25,
                debt_to_equity=0.5,
            )
        )
    return fs


def _load_plotly(visual):
    assert visual is not None
    return json.loads(visual.content)


# ---------------------------------------------------------------------------
# Shared visual language
# ---------------------------------------------------------------------------


def test_financial_trends_uses_shared_palette():
    data = _load_plotly(VisualEngine.plotly_financial_trends(_financials(), "AAPL"))
    layout = data["layout"]
    # Common foundation
    assert layout["template"] == "plotly_white"
    assert layout["height"] == 420
    assert layout["font"]["family"].startswith("-apple-system")
    assert layout["margin"]["l"] == 68  # shared PLOTLY_MARGIN
    assert "hoverlabel" in layout
    # Traces use the shared palette, not raw hex
    trace_colors = [t["marker"]["color"] for t in data["traces"] if t["type"] == "bar"]
    assert trace_colors == [PLOTLY_COLORS["blue"]]


def test_scenario_valuation_uses_shared_palette_and_em_dash():
    v = ValuationRange(
        ticker="AAPL",
        current_price=100.0,
        primary_methodology="DCF",
        scenarios=[
            ValuationScenario(
                scenario_type="bull", label="Bull Case", assumptions=[],
                implied_price_low=150.0, implied_price_high=200.0,
                revenue_growth=0.1, operating_margin=0.2, pe_multiple=25.0,
                ev_ebitda_multiple=None, narrative="",
            ),
            ValuationScenario(
                scenario_type="base", label="Base Case", assumptions=[],
                implied_price_low=100.0, implied_price_high=130.0,
                revenue_growth=0.05, operating_margin=0.18, pe_multiple=20.0,
                ev_ebitda_multiple=None, narrative="",
            ),
        ],
    )
    data = _load_plotly(VisualEngine.plotly_scenario_valuation(v))
    layout = data["layout"]
    assert layout["template"] == "plotly_white"
    # Em-dash in the bar text, not a hyphen
    assert " – " in data["traces"][0]["text"][0]
    # Colors come from the shared palette
    bar_colors = {t["marker"]["color"] for t in data["traces"]}
    assert PLOTLY_COLORS["green"] in bar_colors and PLOTLY_COLORS["blue"] in bar_colors


def test_peer_comparison_uses_shared_palette():
    from research_analyst.models import Competitor

    peers = [
        Competitor(
            ticker="MSFT", name="Microsoft", market_cap=2_000_000_000_000,
            gross_margin=0.68, operating_margin=0.42, pe_ratio=30.0,
            ev_ebitda=20.0, revenue_growth_yoy=0.15, roe=0.35, debt_to_equity=0.4,
        ),
        Competitor(
            ticker="GOOGL", name="Alphabet", market_cap=1_500_000_000_000,
            gross_margin=0.58, operating_margin=0.30, pe_ratio=25.0,
            ev_ebitda=18.0, revenue_growth_yoy=0.12, roe=0.30, debt_to_equity=0.2,
        ),
    ]
    data = _load_plotly(VisualEngine.plotly_peer_comparison("MSFT", peers))
    assert data["layout"]["barmode"] == "group"
    colors = {t["marker"]["color"] for t in data["traces"]}
    assert colors == {PLOTLY_COLORS["green"], PLOTLY_COLORS["blue"], PLOTLY_COLORS["violet"]}


def test_risk_heatmap_uses_shared_palette():
    risks = [
        StructuredRisk(title="Regulatory", description="", category="regulatory",
                       probability="High (>50%)", impact="Critical",
                       timing="near_term", nature="structural"),
        StructuredRisk(title="Demand", description="", category="macro",
                       probability="Low (<20%)", impact="Low",
                       timing="long_term", nature="transitory"),
    ]
    matrix = RiskMatrix(ticker="AAPL", overall_risk_score=6, key_risk_summary="x", risks=risks)
    data = _load_plotly(VisualEngine.plotly_risk_heatmap(matrix))
    colors = data["traces"][0]["marker"]["color"]
    assert PLOTLY_COLORS["red"] in colors  # high-prob × critical => red
    assert data["layout"]["template"] == "plotly_white"


# ---------------------------------------------------------------------------
# Markdown tables — analyst-friendly alignment
# ---------------------------------------------------------------------------


def test_financial_summary_table_right_aligns_numerics():
    vis = VisualEngine.table_financial_summary(_financials(), "USD")
    assert "|:-------|" in vis.content  # metric column left-aligned
    assert "-------:|" in vis.content  # numeric columns right-aligned


def test_key_metrics_table_right_aligns_values():
    profile = CompanyProfile(
        ticker="AAPL", name="Apple Inc.", sector="Technology", industry="Consumer Electronics",
        currency="USD", security_type=SecurityType.EQUITY, description="",
    )
    vis = VisualEngine.table_key_metrics(profile, _financials(1), 150.0, 25.0)
    assert "------:|" in vis.content  # value column right-aligned


# ---------------------------------------------------------------------------
# Fluid exports — same flow as the top menu
# ---------------------------------------------------------------------------


def _comparative_report_min():
    from research_analyst.comparative import (
        ComparativeReport,
        DimensionComparison,
        MetricComparison,
    )

    resp = ResearchResponse(
        ticker="AAPL", security_type=SecurityType.EQUITY, company_name="Apple Inc.",
        currency="USD", generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        reports=[], metadata=ResearchMetadata(),
    )
    metric = MetricComparison(
        dimension="Valuation", key="pe_ratio", label="P/E", unit="ratio",
        higher_is_better=False, values={"AAPL": 25.0}, ranks={"AAPL": 1},
        winners=[], normalized={"AAPL": 60}, rankable=True, available=True,
        source="test",
    )
    dim = DimensionComparison(name="Valuation", metrics=[metric])
    return ComparativeReport(
        requested_tickers=["AAPL"], tickers=["AAPL"],
        company_names={"AAPL": "Apple Inc."}, currencies={"AAPL": "USD"},
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        scorecard=[], dimensions=[dim], per_ticker_reports=[resp],
    )


def test_compare_html_wraps_tables_fluid():
    from research_analyst.reports.comparative_renderer import render_html

    report = _comparative_report_min()
    html_out = render_html(report)
    assert "class=\"table-scroll\"" in html_out
    assert "@media (max-width: 640px)" in html_out
    assert "overflow-x: auto" in html_out  # horizontal pan on narrow screens


def test_report_markdown_unchanged_structure():
    """The polish must not break the report contract (sections/headings)."""
    report = ReportOutput(
        report_type=ReportType.COMPREHENSIVE,
        ticker="AAPL", title="AAPL — Comprehensive",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        sections=[],
    )
    md = report.to_markdown()
    assert "# AAPL — Comprehensive" in md
    assert "**Disclaimer:**" in md
