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
from research_analyst.reports.svg_charts import C
from research_analyst.reports.visuals import VisualEngine

C_NAVY, C_GREEN, C_RED, C_VIOLET = C["navy"], C["green"], C["red"], C["violet"]


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


def _load_svg(visual):
    assert visual is not None
    assert visual.visual_type == "svg"
    return visual.content


# ---------------------------------------------------------------------------
# Shared visual language (server-rendered SVG charts — Phase F)
# ---------------------------------------------------------------------------


def test_financial_trends_renders_svg():
    svg = _load_svg(VisualEngine.svg_financial_trends(_financials(), "AAPL"))
    assert svg.startswith("<svg")
    assert "Margin Trends" in svg  # title present (ampersand is SVG-escaped)
    assert "width:100%" in svg  # fluid
    assert C_NAVY in svg  # revenue bars use the navy primary


def test_scenario_valuation_uses_palette_and_em_dash():
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
    svg = _load_svg(VisualEngine.svg_scenario_valuation(v))
    # Em-dash in the range label, not a hyphen
    assert "\u2013" in svg
    # Institutional palette present
    assert C_GREEN in svg and C_NAVY in svg


def test_peer_comparison_uses_palette():
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
    svg = _load_svg(VisualEngine.svg_peer_comparison("MSFT", peers))
    for color in (C_GREEN, C_NAVY, C_VIOLET):
        assert color in svg


def test_risk_heatmap_uses_palette():
    risks = [
        StructuredRisk(title="Regulatory", description="", category="regulatory",
                       probability="High (>50%)", impact="Critical",
                       timing="near_term", nature="structural"),
        StructuredRisk(title="Demand", description="", category="macro",
                       probability="Low (<20%)", impact="Low",
                       timing="long_term", nature="transitory"),
    ]
    matrix = RiskMatrix(ticker="AAPL", overall_risk_score=6, key_risk_summary="x", risks=risks)
    svg = _load_svg(VisualEngine.svg_risk_heatmap(matrix))
    assert C_RED in svg  # high-prob × critical => red
    assert "Risk Matrix" in svg


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


def test_svg_emission_embedded_in_report_markdown():
    """SVG visuals embed as raw markup inside a .chart-svg div (no JSON attr
    to truncate, no client-side rendering needed)."""
    from research_analyst.models import ReportSection, ReportVisual

    svg_markup = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<rect width="10" height="10"/></svg>'
    )
    visual = ReportVisual(
        visual_type="svg", title="Chart",
        content=svg_markup, ties_to="test", caption="",
        interactive={"type": "scenario", "scenarios": [{"label": "Base", "low": 90, "high": 110}]},
    )
    section = ReportSection(
        step_number=1, title="Step 1", content="body", visuals=[visual],
    )
    report = ReportOutput(
        report_type=ReportType.COMPREHENSIVE,
        ticker="AAPL", title="AAPL — Comprehensive",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        sections=[section],
    )
    md = report.to_markdown()
    assert '<div class="chart-svg">' in md
    assert "<svg" in md and "</svg>" in md
    assert "data-plotly" not in md
    # on-demand interactive view: button present with the lazy payload
    assert 'class="chart-interactive"' in md
    assert 'data-interactive="' in md
    assert "Interactive view" in md
