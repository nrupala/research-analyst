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
from typing import Any

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
            caption="Conceptual business model flow.",
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
    def d2_capital_allocation(
        ticker: str,
        capex_pct: float | None,
        buyback_pct: float | None,
        dividend_pct: float | None,
    ) -> ReportVisual:
        """Capital allocation flow as a server-rendered D2 diagram."""
        source = diagrams.d2_capital_allocation(ticker, capex_pct, buyback_pct, dividend_pct)
        return diagrams.diagram_visual(
            source,
            title=f"{ticker} — Capital Allocation Flow",
            ties_to="Capital allocation analysis (Step 4)",
            caption="FCF deployment breakdown. Most recent annual period.",
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
    def table_key_metrics(
        profile: CompanyProfile,
        financials: list[FinancialStatement],
        current_price: float,
        pe_ratio: float | None = None,
    ) -> ReportVisual:
        """Key metrics summary table."""
        latest = financials[0] if financials else None
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
        header = f"| Ticker | Name | Mkt Cap ({sym}B) | Gross Margin | Op Margin | P/E | EV/EBITDA | Rev Growth | ROE | D/E |"
        sep = "|:------|:-----|-----------:|------------:|----------:|----:|----------:|-----------:|----:|----:|"
        rows = [header, sep]

        for p in peers[:8]:
            mc = f"{sym}{float(p.market_cap) / 1e9:.1f}" if p.market_cap else "N/A"
            gm = f"{p.gross_margin:.1%}" if p.gross_margin is not None else "N/A"
            om = f"{p.operating_margin:.1%}" if p.operating_margin is not None else "N/A"
            pe = f"{p.pe_ratio:.1f}x" if p.pe_ratio is not None else "N/A"
            ev = f"{p.ev_ebitda:.1f}x" if p.ev_ebitda is not None else "N/A"
            rg = f"{p.revenue_growth_yoy:.1%}" if p.revenue_growth_yoy is not None else "N/A"
            roe = f"{p.roe:.1%}" if p.roe is not None else "N/A"
            de = f"{p.debt_to_equity:.2f}x" if p.debt_to_equity is not None else "N/A"
            rows.append(f"| **{p.ticker}** | {p.name[:20]} | {mc} | {gm} | {om} | {pe} | {ev} | {rg} | {roe} | {de} |")

        return ReportVisual(visual_type="table", title="Peer Comparison", content="\n".join(rows), ties_to="Competitive positioning (Step 3)")

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

        return ReportVisual(visual_type="table", title="Structured Risk Matrix", content="\n".join(rows), ties_to="Risk assessment (Step 5/6)")

    @staticmethod
    def table_financial_summary(financials: list[FinancialStatement], currency: str | None = None) -> ReportVisual:
        """Multi-period financial summary table."""
        if not financials:
            return ReportVisual(visual_type="table", title="Financial Summary", content="*No data.*", ties_to="Financial analysis")

        sym = currency_symbol(currency)
        sorted_fin = sorted(financials, key=lambda f: f.period_end_date or __import__("datetime").date.min)[-5:]
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

        return ReportVisual(visual_type="table", title="Financial Summary", content="\n".join(rows), ties_to="Financial analysis (Step 2)")

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

        return ReportVisual(visual_type="table", title="Macro Environment", content="\n".join(rows), ties_to="Macro context (Step 5)")

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
            rows.append(f"| **Consecutive Increases** | {div.consecutive_increase_years} yrs |")
        if div.had_cut:
            sc = f"{div.years_since_cut} yrs ago" if div.years_since_cut is not None else "yes"
            rows.append(f"| **Dividend Cut** | {sc} |")
        if div.safety_score is not None:
            rows.append(f"| **Safety Score** | {div.safety_score:.0f}/100 ({div.safety_grade}) |")
        if div.peer_median_yield is not None:
            rows.append(f"| **Peer Median Yield** | {pct(div.peer_median_yield)} ({div.yield_vs_peers or 'n/a'}) |")
        if div.us_10y_yield is not None:
            spread = div.yield_vs_treasury_spread
            sp = f" ({spread * 100:+.0f} bps)" if spread is not None else ""
            rows.append(f"| **vs 10Y Treasury** | {pct(div.us_10y_yield)}{sp} |")
        if div.attractiveness_rating:
            rows.append(f"| **Attractiveness** | {div.attractiveness_rating} |")

        return ReportVisual(
            visual_type="table",
            title=f"{label} & Yield Summary",
            content="\n".join(rows),
            ties_to="Dividend & yield analysis",
            caption=div.attractiveness_rationale or "Yields shown as annual percentages.",
        )

    @staticmethod
    def svg_dividend_history(div, currency=None):
        """Annual dividend-per-share history as server-rendered SVG."""
        annual = getattr(div, "annual_dividends", {}) or {}
        if len(annual) < 3:
            return None
        return svg_charts.svg_dividend_history(div, currency)
