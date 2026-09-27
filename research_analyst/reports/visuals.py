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

"""Visual intelligence engine — Plotly JSON data, Mermaid syntax, ASCII charts, Markdown tables.

All Plotly visuals are delivered as JSON-serializable dicts with 'traces' and 'layout' keys.
The frontend calls Plotly.newPlot(divId, data.traces, data.layout) directly.

All Mermaid visuals are delivered as raw diagram syntax strings.
The frontend calls mermaid.render(id, syntax) directly.

No Python code blocks. No intermediary parsing. No service workers.
The browser libraries (Plotly.js, Mermaid.js) handle all rendering.
"""
# Module: research_analyst/reports/visuals.py | Version: 0.1.1 | Updated: 2026-06-02

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from ..quant import to_bps
from ..models import (
    CompanyProfile,
    Competitor,
    DividendAnalysis,
    FinancialStatement,
    ReportVisual,
    RiskMatrix,
    StructuredRisk,
    TechnicalIndicators,
    ValuationRange,
)
from .currency import currency_symbol
from . import diagrams
from . import svg_charts

logger = logging.getLogger(__name__)

# Metrics rendered in the multi-period financial summary, used to decide
# whether a period carries any data at all.
_SUMMARY_METRICS = (
    "revenue", "gross_profit", "operating_income", "net_income",
    "gross_margin", "operating_margin", "net_margin", "eps_diluted",
    "free_cash_flow", "roe", "debt_to_equity",
)


def _has_any_metric(fin: Any) -> bool:
    """True when at least one summary metric is present for this period."""
    return any(getattr(fin, name, None) is not None for name in _SUMMARY_METRICS)


# ---------------------------------------------------------------------------

class VisualEngine:
    """Generates constraint-safe visuals for research reports.

    Plotly methods return ReportVisual with visual_type="plotly_json"
    and content = JSON string of {"traces": [...], "layout": {...}}.

    Mermaid methods return ReportVisual with visual_type="mermaid"
    and content = raw Mermaid diagram syntax.

    The frontend detects visual_type and calls the appropriate library.
    """

    # ------------------------------------------------------------------
    # Plotly JSON generators — frontend calls Plotly.newPlot() directly
    # ------------------------------------------------------------------

    @staticmethod
    def svg_financial_trends(financials, ticker, currency=None):
        """Revenue + margin trend chart as server-rendered SVG."""
        return svg_charts.svg_financial_trends(financials, ticker, currency)

    @staticmethod
    def svg_scenario_valuation(valuation, currency=None):
        """Scenario valuation range as server-rendered SVG."""
        if not valuation.scenarios:
            return None
        return svg_charts.svg_scenario_valuation(valuation, currency)

    @staticmethod
    def svg_peer_comparison(target_ticker, peers, currency=None):
        """Peer comparison margins/ROE as server-rendered SVG."""
        return svg_charts.svg_peer_comparison(target_ticker, peers, currency)

    @staticmethod
    def svg_risk_heatmap(risk_matrix):
        """Risk matrix probability x impact as server-rendered SVG."""
        if not risk_matrix or not risk_matrix.risks:
            return None
        return svg_charts.svg_risk_heatmap(risk_matrix)

    # ------------------------------------------------------------------
    # Diagrams — D2 source, rendered server-side to static SVG
    # ------------------------------------------------------------------

    @staticmethod
    def d2_business_model(
        profile: CompanyProfile,
        revenue_segments: list[str] | None = None,
    ) -> ReportVisual:
        """Business model flowchart as a server-rendered D2 diagram."""
        source = diagrams.d2_business_model(profile.ticker, revenue_segments)
        return diagrams.diagram_visual(
            source,
            title=f"{profile.ticker} — Business Model Overview",
            ties_to="Business model and structural position (Step 1)",
            caption="Conceptual business model flow (illustrative \u2014 not company-specific).",
        )

    @staticmethod
    def d2_decision_framework(
        ticker: str,
        favors: list[str],
        disfavors: list[str],
        catalysts: list[str],
    ) -> ReportVisual:
        """Decision framework as a server-rendered D2 diagram."""
        source = diagrams.d2_decision_framework(ticker, favors, disfavors, catalysts)
        return diagrams.diagram_visual(
            source,
            title=f"{ticker} — Decision Framework",
            ties_to="Investment thesis (Step 7)",
            caption="Favors/disfavors framing. Never buy/sell/hold.",
        )

    @staticmethod
    def svg_thesis_balance(
        ticker: str, n_favor: int, n_disfavor: int, tilt: str
    ) -> ReportVisual:
        """Thesis evidence balance as a server-rendered SVG."""
        return svg_charts.svg_thesis_balance(ticker, n_favor, n_disfavor, tilt)

    @staticmethod
    def svg_unit_economics(
        ticker: str, margins: dict[str, float | None]
    ) -> ReportVisual | None:
        """Unit-economics margin bars as a server-rendered SVG."""
        return svg_charts.svg_unit_economics(ticker, margins)

    @staticmethod
    def d2_catalyst_watchlist(
        ticker: str, near_term: list[str], structural: list[str]
    ) -> ReportVisual:
        """Catalyst watchlist as a server-rendered D2 diagram."""
        source = diagrams.d2_catalyst_watchlist(ticker, near_term, structural)
        return diagrams.diagram_visual(
            source,
            title=f"{ticker} \u2014 Catalyst Watchlist",
            ties_to="Catalysts and monitoring (Step 7)",
            caption="Near-term vs structural catalysts feeding the monitoring decision.",
        )

    @staticmethod
    def d2_capital_allocation(
        ticker: str,
        capex_pct: float | None,
        buyback_pct: float | None,
        dividend_pct: float | None,
        capex_abs: float | None = None,
        buyback_abs: float | None = None,
        dividend_abs: float | None = None,
        currency: str | None = "USD",
        period: str | None = None,
        ties_to: str = "Capital allocation analysis",
    ) -> ReportVisual:
        """Capital allocation flow as a server-rendered D2 diagram."""
        source = diagrams.d2_capital_allocation(
            ticker, capex_pct, buyback_pct, dividend_pct,
            capex_abs=capex_abs, buyback_abs=buyback_abs,
            div_abs=dividend_abs, currency=currency,
        )
        caption = "Capital deployed by destination"
        if period:
            caption += f" ({period})"
        caption += ". Percentages are shares of total capital deployed."
        return diagrams.diagram_visual(
            source,
            title=f"{ticker} — Capital Allocation Flow",
            ties_to=ties_to,
            caption=caption,
        )

    # ------------------------------------------------------------------
    # ASCII charts
    # ------------------------------------------------------------------

    @staticmethod
    def ascii_scenario_chart(valuation: ValuationRange, currency: str | None = None) -> ReportVisual:
        """Mandatory ASCII scenario summary."""
        return ReportVisual(
            visual_type="ascii",
            title="Scenario-Based Valuation Summary",
            content=valuation.ascii_chart(),
            ties_to="Scenario-based valuation range",
            caption=f"Current price: {currency_symbol(currency)}{valuation.current_price:.2f}.",
        )

    @staticmethod
    def ascii_technical_dashboard(
        indicators: TechnicalIndicators,
        composite_score: float,
        regime: str,
    ) -> ReportVisual:
        """ASCII dashboard for technical signals."""
        lines = [
            f"    Technical Regime:  {regime.upper()}  (Score: {composite_score:.0f}/100)",
            "",
        ]

        trend_icon = "^" if indicators.price_vs_sma_200 == "above" else "v"
        lines.append(f"    Trend:     [{trend_icon}] Price {indicators.price_vs_sma_200 or 'N/A'} SMA 200  |  {indicators.sma_50_vs_200}")

        if indicators.rsi_14 is not None:
            filled = int(indicators.rsi_14 / 100 * 20)
            rsi_bar = chr(9608) * filled + chr(9617) * (20 - filled)
            lines.append(f"    RSI (14):  [{rsi_bar}] {indicators.rsi_14:.1f}")
        else:
            lines.append("    RSI (14):  N/A")

        lines.append(f"    MACD:      {indicators.macd_crossover or 'none'}  |  Histogram: {indicators.macd_histogram or 0:.4f}")
        lines.append(f"    ATR %:     {indicators.atr_pct or 0:.2f}%  |  ADX: {indicators.adx_14 or 0:.1f} ({indicators.adx_signal})")
        lines.append(f"    Volume:    {indicators.volume_trend}  |  OBV: {indicators.obv_trend}")

        return ReportVisual(
            visual_type="ascii",
            title="Technical Dashboard",
            content="\n".join(lines),
            ties_to="Technical analysis signals",
            caption="Composite score: 0=bearish, 100=bullish.",
        )

    # ------------------------------------------------------------------
    # Markdown tables
    # ------------------------------------------------------------------

    @staticmethod
    def _latest_statement(financials: list) -> Any | None:
        """Latest statement by period end date — never assume list order.

        Providers are not contractually most-recent-first, so "latest" must be
        derived from the data, not from position 0.
        """
        if not financials:
            return None
        dated = [f for f in financials if getattr(f, "period_end_date", None)]
        if dated:
            return max(dated, key=lambda f: f.period_end_date)
        return financials[0]

    @staticmethod
    def table_key_metrics(
        profile: CompanyProfile,
        financials: list[FinancialStatement],
        current_price: float,
        pe_ratio: float | None = None,
    ) -> ReportVisual:
        """Key metrics summary table."""
        latest = VisualEngine._latest_statement(financials)
        sym = currency_symbol(profile.currency)
        rows = [
            "| Metric | Value |",
            "|:-------|------:|",
            f"| **Company** | {profile.name} ({profile.ticker}) |",
            f"| **Sector / Industry** | {profile.sector} / {profile.industry} |",
        ]
        if profile.market_cap:
            rows.append(f"| **Market Cap** | {sym}{float(profile.market_cap) / 1e9:.1f}B |")
        rows.append(f"| **Current Price** | {sym}{current_price:.2f} |")

        if latest:
            if latest.revenue:
                rows.append(f"| **Revenue (Latest)** | {sym}{float(latest.revenue) / 1e9:.2f}B |")
            if latest.operating_margin is not None:
                rows.append(f"| **Operating Margin** | {latest.operating_margin:.1%} |")
            if latest.net_margin is not None:
                rows.append(f"| **Net Margin** | {latest.net_margin:.1%} |")
            if latest.roe is not None:
                rows.append(f"| **ROE** | {latest.roe:.1%} |")
            if latest.debt_to_equity is not None:
                rows.append(f"| **Debt/Equity** | {latest.debt_to_equity:.2f}x |")
            if latest.eps_diluted is not None:
                rows.append(f"| **EPS (Diluted)** | {sym}{latest.eps_diluted:.2f} |")
        if pe_ratio:
            rows.append(f"| **P/E Ratio** | {pe_ratio:.1f}x |")

        return ReportVisual(
            visual_type="table",
            title="Key Metrics Summary",
            content="\n".join(rows),
            ties_to="Executive summary",
            caption="Most recent annual data.",
        )

    @staticmethod
    def table_peer_comparison(target_ticker: str, peers: list[Competitor], currency: str | None = None) -> ReportVisual:
        """Peer comparison table."""
        if not peers:
            return ReportVisual(visual_type="table", title="Peer Comparison", content="*No peer data.*", ties_to="Competitive analysis")

        sym = currency_symbol(currency)
        header = (
            f"| Ticker | Name | Mkt Cap ({sym}B) | Gross Margin | Op Margin | P/E "
            f"| EV/EBITDA | Rev Growth | ROE | D/E | Div Yield |"
        )
        sep = (
            "|:------|:-----|-----------:|------------:|----------:|----:"
            "----------:|-----------:|----:|----:|----------:|"
        )
        rows = [header, sep]
        not_meaningful = 0

        for p in peers[:8]:
            mc = f"{sym}{float(p.market_cap) / 1e9:.1f}" if p.market_cap else "N/A"
            gm = f"{p.gross_margin:.1%}" if p.gross_margin is not None else "N/A"
            om = f"{p.operating_margin:.1%}" if p.operating_margin is not None else "N/A"
            if p.pe_ratio is None:
                pe = "N/A"
            elif p.pe_ratio <= 0:
                # A non-positive P/E is not a valuation signal, it is a symptom
                # of negative or absent earnings. Rendering "-45.0x" invites the
                # reader to treat it as an extreme observation.
                pe = "n/m"
                not_meaningful += 1
            else:
                pe = f"{p.pe_ratio:.1f}x"
            ev = f"{p.ev_ebitda:.1f}x" if p.ev_ebitda is not None else "N/A"
            rg = f"{p.revenue_growth_yoy:.1%}" if p.revenue_growth_yoy is not None else "N/A"
            roe = f"{p.roe:.1%}" if p.roe is not None else "N/A"
            de = f"{p.debt_to_equity:.2f}x" if p.debt_to_equity is not None else "N/A"
            dy = f"{p.dividend_yield:.2%}" if p.dividend_yield is not None else "N/A"
            # Full company name: the paid source-data export re-parses this
            # table, so truncating it here loses data for the customer.
            rows.append(
                f"| **{p.ticker}** | {p.name} | {mc} | {gm} | {om} | {pe} | "
                f"{ev} | {rg} | {roe} | {de} | {dy} |"
            )

        caption = (
            "Profitability, valuation, growth, and leverage versus peers. "
            "N/A = data unavailable for that peer."
        )
        if not_meaningful:
            caption += (
                f" n/m = P/E not meaningful for {not_meaningful} peer"
                f"{'s' if not_meaningful != 1 else ''} "
                "(non-positive earnings); those values are excluded from "
                "peer-multiple medians."
            )
        caption += " Div Yield is trailing dividend yield."

        return ReportVisual(
            visual_type="table", title="Peer Comparison", content="\n".join(rows),
            ties_to="Competitive positioning (Step 3)",
            caption=caption,
        )

    @staticmethod
    def table_risk_matrix(risks: list[StructuredRisk]) -> ReportVisual:
        """Structured risk matrix table sorted by severity."""
        if not risks:
            return ReportVisual(visual_type="table", title="Risk Matrix", content="*No risks identified.*", ties_to="Risk assessment")

        header = "| Risk | Category | Probability | Impact | Timing | Nature |"
        sep = "|:-----|:---------|-----------:|------:|:------|:------|"
        rows = [header, sep]

        for r in risks[:10]:
            rows.append(f"| {r.title} | {r.category.value.title()} | {r.probability} | {r.impact} | {r.timing.value.replace('_', ' ').title()} | {r.nature.value.title()} |")

        return ReportVisual(
            visual_type="table", title="Structured Risk Matrix", content="\n".join(rows),
            ties_to="Risk assessment (Step 5/6)",
            caption="Top risks by severity (probability \u00d7 impact). Timing and nature per the risk framework; score derivation published below.",
        )

    @staticmethod
    def table_financial_summary(financials: list[FinancialStatement], currency: str | None = None) -> ReportVisual:
        """Multi-period financial summary table."""
        if not financials:
            return ReportVisual(visual_type="table", title="Financial Summary", content="*No data.*", ties_to="Financial analysis")

        sym = currency_symbol(currency)
        by_date = sorted(
            financials, key=lambda f: f.period_end_date or __import__("datetime").date.min
        )
        # A period where every metric is null carries no information and renders
        # as an all-N/A column, which reads as a data outage rather than an
        # absent year. Drop it, then say so — silently omitting a year would be
        # its own kind of dishonesty.
        complete = [f for f in by_date if _has_any_metric(f)]
        omitted = [f for f in by_date if not _has_any_metric(f)]
        sorted_fin = complete[-5:]
        periods = [f.period for f in sorted_fin]
        header = "| Metric | " + " | ".join(periods) + " |"
        sep = "|:-------|" + "|".join(["-------:"] * len(periods)) + "|"

        def _row(label, getter, fmt="dec"):
            vals = []
            for f in sorted_fin:
                v = getter(f)
                if v is None:
                    vals.append("N/A")
                elif fmt == "dec":
                    vals.append(f"{sym}{float(v) / 1e9:.2f}B")
                elif fmt == "pct":
                    vals.append(f"{v:.1%}")
                elif fmt == "float":
                    vals.append(f"{v:.2f}")
                elif fmt == "ratio":
                    vals.append(f"{v:.2f}x")
                else:
                    vals.append(str(v))
            return f"| **{label}** | " + " | ".join(vals) + " |"

        rows = [header, sep]
        rows.append(_row("Revenue", lambda f: f.revenue, "dec"))
        rows.append(_row("Gross Profit", lambda f: f.gross_profit, "dec"))
        rows.append(_row("Operating Income", lambda f: f.operating_income, "dec"))
        rows.append(_row("Net Income", lambda f: f.net_income, "dec"))
        rows.append(_row("Gross Margin", lambda f: f.gross_margin, "pct"))
        rows.append(_row("Operating Margin", lambda f: f.operating_margin, "pct"))
        rows.append(_row("Net Margin", lambda f: f.net_margin, "pct"))
        rows.append(_row("EPS (Diluted)", lambda f: f.eps_diluted, "float"))
        rows.append(_row("Free Cash Flow", lambda f: f.free_cash_flow, "dec"))
        rows.append(_row("ROE", lambda f: f.roe, "pct"))
        rows.append(_row("Debt/Equity", lambda f: f.debt_to_equity, "ratio"))

        period_note = f" ({periods[0]}\u2013{periods[-1]})" if len(periods) > 1 else (f" ({periods[0]})" if periods else "")
        caption = (
            f"Annual financials{period_note}. Money figures in {sym} billions; "
            "margins as % of revenue."
        )
        if omitted:
            names = ", ".join(f.period for f in omitted)
            caption += (
                f" {names} omitted: no data available for any metric in "
                f"{'that period' if len(omitted) == 1 else 'those periods'}."
            )
        return ReportVisual(
            visual_type="table", title="Financial Summary", content="\n".join(rows),
            ties_to="Financial analysis (Step 2)",
            caption=caption,
        )

    @staticmethod
    def table_macro_regime(implications: list) -> ReportVisual:
        """Macro regime summary table."""
        header = "| Factor | Current | Regime | Sector Impact | Magnitude |"
        sep = "|:-------|:--------|:------|--------------:|:----------|"
        rows = [header, sep]

        for impl in implications:
            factor = getattr(impl, "factor", "")
            current = getattr(impl, "current_value", "N/A")
            regime = getattr(impl, "regime", "")
            impact = getattr(impl, "implication", "neutral")
            magnitude = getattr(impl, "magnitude", "")
            rows.append(f"| {factor} | {current} | {regime} | {impact.title()} | {magnitude.title()} |")

        return ReportVisual(
            visual_type="table", title="Macro Environment", content="\n".join(rows),
            ties_to="Macro context (Step 5)",
            caption="How each macro factor is classified today and what it implies for the sector.",
        )

    # ------------------------------------------------------------------
    # Dividend & yield (v0.1.1)
    # ------------------------------------------------------------------

    @staticmethod
    def table_dividend_summary(div: DividendAnalysis, currency: str | None = None) -> ReportVisual:
        """Dividend & yield summary table."""
        label = div.income_label or "Dividend"
        sym = currency_symbol(currency)
        rows = ["| Metric | Value |", "|:-------|------:|"]

        if not div.pays_dividend:
            rows.append(f"| **{label}** | None |")
            if div.no_dividend_context:
                rows.append(f"| **Policy** | {div.no_dividend_context} |")
            return ReportVisual(
                visual_type="table",
                title=f"{label} & Yield Summary",
                content="\n".join(rows),
                ties_to="Dividend & yield analysis",
                caption="No dividend currently paid.",
            )

        def pct(v: float | None) -> str:
            return f"{v:.2%}" if v is not None else "N/A"

        yield_label = "Current Yield (TTM)" if div.is_etf else "Current Yield (fwd)"
        if div.current_yield is not None:
            rows.append(f"| **{yield_label}** | {pct(div.current_yield)} |")
        if div.trailing_yield is not None:
            rows.append(f"| **Trailing Yield (12m)** | {pct(div.trailing_yield)} |")
        if div.five_year_avg_yield is not None:
            rows.append(f"| **5Y Avg Yield** | {pct(div.five_year_avg_yield)} |")
        if div.annual_dividend_rate is not None:
            rows.append(f"| **Annual Rate** | {sym}{div.annual_dividend_rate:.2f}/share |")
        if div.dividend_growth_1y is not None:
            rows.append(f"| **Growth (1Y)** | {pct(div.dividend_growth_1y)} |")
        if div.dividend_growth_3y_cagr is not None:
            rows.append(f"| **Growth (3Y CAGR)** | {pct(div.dividend_growth_3y_cagr)} |")
        if div.dividend_growth_5y_cagr is not None:
            rows.append(f"| **Growth (5Y CAGR)** | {pct(div.dividend_growth_5y_cagr)} |")
        if div.payout_ratio_eps is not None:
            rows.append(f"| **Payout (EPS)** | {div.payout_ratio_eps:.0%} |")
        if div.payout_ratio_fcf is not None:
            rows.append(f"| **Payout (FCF)** | {div.payout_ratio_fcf:.0%} |")
        if div.fcf_coverage is not None:
            rows.append(f"| **FCF Coverage** | {div.fcf_coverage:.2f}x |")
        if div.consecutive_increase_years:
            yrs = div.consecutive_increase_years
            rows.append(
                f"| **Consecutive Increases** | {yrs} "
                f"year{'s' if yrs != 1 else ''} |"
            )
        if div.had_cut:
            sc = f"{div.years_since_cut} yrs ago" if div.years_since_cut is not None else "yes"
            rows.append(f"| **Dividend Cut** | {sc} |")
        if div.safety_score is not None:
            rows.append(f"| **Safety Score** | {div.safety_score:.0f}/100 ({div.safety_grade}) |")
        if div.peer_median_yield is not None:
            rows.append(f"| **Peer Median Yield** | {pct(div.peer_median_yield)} ({div.yield_vs_peers or 'n/a'}) |")
        if div.us_10y_yield is not None:
            # Two separate numbers, deliberately not merged into one row. A row
            # labelled "vs 10Y Treasury" whose value is the Treasury's own yield
            # invites the reader to mistake one company's rate for another's.
            rows.append(f"| **10Y Treasury Yield** | {pct(div.us_10y_yield)} |")
            spread = div.yield_vs_treasury_spread
            if spread is not None:
                direction = "above" if spread > 0 else "below"
                # The parenthetical is the *spread magnitude* (percentage
                # points), not the company's own yield. Using current_yield here
                # would reintroduce exactly the conflation the split removes, and
                # would crash when current_yield is None.
                rows.append(
                    f"| **Spread vs 10Y Treasury** | {to_bps(spread):+.0f} bps "
                    f"({abs(spread) * 100:.2f} pp {direction} 10Y) |"
                )
        if div.attractiveness_rating:
            rows.append(f"| **Attractiveness** | {div.attractiveness_rating} |")

        caption = div.attractiveness_rationale or "Yields shown as annual percentages."
        annual = getattr(div, "annual_dividends", {}) or {}
        current_year = date.today().year
        partial = {k: v for k, v in annual.items() if int(k) >= current_year}
        if partial:
            names = ", ".join(sorted(partial))
            caption += (
                f" {names} is a partial year (dividends received to date, not "
                "a full-year total); growth rates exclude it."
            )
        if div.us_10y_yield is not None:
            caption += (
                f" 10Y Treasury is a market rate for the US sovereign, shown as "
                f"the benchmark the {'distribution' if div.is_etf else 'dividend'} "
                "yield is compared against."
            )

        return ReportVisual(
            visual_type="table",
            title=f"{label} & Yield Summary",
            content="\n".join(rows),
            ties_to="Dividend & yield analysis",
            caption=caption,
        )

    @staticmethod
    def svg_dividend_history(div, currency=None):
        """Annual dividend-per-share history as server-rendered SVG."""
        annual = getattr(div, "annual_dividends", {}) or {}
        if len(annual) < 3:
            return None
        return svg_charts.svg_dividend_history(div, currency)
