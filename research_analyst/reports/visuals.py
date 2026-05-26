"""Visual intelligence engine — Plotly JSON data, Mermaid syntax, ASCII charts, Markdown tables.

All Plotly visuals are delivered as JSON-serializable dicts with 'traces' and 'layout' keys.
The frontend calls Plotly.newPlot(divId, data.traces, data.layout) directly.

All Mermaid visuals are delivered as raw diagram syntax strings.
The frontend calls mermaid.render(id, syntax) directly.

No Python code blocks. No intermediary parsing. No service workers.
The browser libraries (Plotly.js, Mermaid.js) handle all rendering.
"""
# Module: research_analyst/reports/visuals.py | Version: 0.1.1 | Updated: 2026-05-25

from __future__ import annotations

import json
import logging
from typing import Any

from ..models import (
    CompanyProfile,
    Competitor,
    FinancialStatement,
    ReportVisual,
    RiskMatrix,
    StructuredRisk,
    TechnicalIndicators,
    ValuationRange,
)

logger = logging.getLogger(__name__)


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
    def plotly_financial_trends(
        financials: list[FinancialStatement],
        ticker: str,
    ) -> ReportVisual | None:
        """Revenue + margin trend chart as Plotly.js JSON."""
        if len(financials) < 2:
            return None

        sorted_fin = sorted(
            financials,
            key=lambda f: f.period_end_date or __import__("datetime").date.min,
        )

        periods = [f.period for f in sorted_fin]
        revenues = [float(f.revenue) / 1e9 if f.revenue else None for f in sorted_fin]
        gross_margins = [f.gross_margin * 100 if f.gross_margin else None for f in sorted_fin]
        op_margins = [f.operating_margin * 100 if f.operating_margin else None for f in sorted_fin]
        net_margins = [f.net_margin * 100 if f.net_margin else None for f in sorted_fin]

        traces: list[dict[str, Any]] = []

        traces.append({
            "x": periods, "y": revenues, "name": "Revenue ($B)",
            "type": "bar", "marker": {"color": "#2563eb", "opacity": 0.8},
            "yaxis": "y"
        })

        if any(v is not None for v in gross_margins):
            traces.append({
                "x": periods, "y": gross_margins, "name": "Gross Margin %",
                "type": "scatter", "mode": "lines+markers",
                "line": {"color": "#16a34a", "width": 2}, "yaxis": "y2"
            })

        if any(v is not None for v in op_margins):
            traces.append({
                "x": periods, "y": op_margins, "name": "Operating Margin %",
                "type": "scatter", "mode": "lines+markers",
                "line": {"color": "#ea580c", "width": 2}, "yaxis": "y2"
            })

        if any(v is not None for v in net_margins):
            traces.append({
                "x": periods, "y": net_margins, "name": "Net Margin %",
                "type": "scatter", "mode": "lines+markers",
                "line": {"color": "#7c3aed", "width": 2, "dash": "dot"}, "yaxis": "y2"
            })

        layout = {
            "title": f"{ticker} — Revenue & Margin Trends",
            "template": "plotly_white", "height": 420,
            "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
            "yaxis": {"title": "Revenue ($B)", "side": "left"},
            "yaxis2": {"title": "Margin (%)", "side": "right", "overlaying": "y"},
            "margin": {"t": 50, "b": 50, "l": 60, "r": 60},
        }

        return ReportVisual(
            visual_type="plotly_json",
            title=f"{ticker} — Revenue & Margin Trends",
            content=json.dumps({"traces": traces, "layout": layout}),
            ties_to="Financial trajectory assessment (Step 2)",
            caption="Revenue in billions USD. Margins as percentage of revenue.",
        )

    @staticmethod
    def plotly_scenario_valuation(valuation: ValuationRange) -> ReportVisual | None:
        """Scenario valuation range as Plotly.js JSON."""
        if not valuation.scenarios:
            return None

        labels = []
        lows = []
        highs = []
        for s in valuation.scenarios:
            if s.implied_price_low is not None and s.implied_price_high is not None:
                labels.append(s.label)
                lows.append(s.implied_price_low)
                highs.append(s.implied_price_high)

        if not labels:
            return None

        colors = {"Bull Case": "#16a34a", "Base Case": "#2563eb", "Bear Case": "#dc2626"}

        traces: list[dict[str, Any]] = []
        for i in range(len(labels)):
            traces.append({
                "y": [labels[i]], "x": [highs[i] - lows[i]], "base": [lows[i]],
                "type": "bar", "orientation": "h",
                "name": labels[i],
                "marker": {"color": colors.get(labels[i], "#6b7280"), "opacity": 0.8},
                "text": [f"${lows[i]:.0f} - ${highs[i]:.0f}"],
                "textposition": "inside", "showlegend": False,
            })

        layout: dict[str, Any] = {
            "title": "Scenario-Based Valuation Range",
            "template": "plotly_white", "height": 280,
            "xaxis": {"title": "Price ($)"},
            "margin": {"t": 50, "b": 50, "l": 120, "r": 30},
        }

        if valuation.current_price > 0:
            layout["shapes"] = [{
                "type": "line",
                "x0": valuation.current_price, "x1": valuation.current_price,
                "y0": -0.5, "y1": len(labels) - 0.5,
                "line": {"color": "black", "width": 2, "dash": "dash"},
            }]
            layout["annotations"] = [{
                "x": valuation.current_price, "y": len(labels) - 0.5,
                "text": f"Current: ${valuation.current_price:.0f}",
                "showarrow": False, "yshift": 15,
                "font": {"size": 11, "color": "black"},
            }]

        return ReportVisual(
            visual_type="plotly_json",
            title="Scenario-Based Valuation Range",
            content=json.dumps({"traces": traces, "layout": layout}),
            ties_to="Valuation scenarios (Step 6)",
            caption=f"Current price: ${valuation.current_price:.2f}. Assumption-driven illustrations.",
        )

    @staticmethod
    def plotly_peer_comparison(
        target_ticker: str,
        peers: list[Competitor],
    ) -> ReportVisual | None:
        """Peer comparison bar chart as Plotly.js JSON."""
        if not peers:
            return None

        tickers = [p.ticker for p in peers[:6]]
        metrics = {
            "Gross Margin %": [p.gross_margin * 100 if p.gross_margin else None for p in peers[:6]],
            "Op Margin %": [p.operating_margin * 100 if p.operating_margin else None for p in peers[:6]],
            "ROE %": [p.roe * 100 if p.roe else None for p in peers[:6]],
        }

        traces = []
        for name, vals in metrics.items():
            traces.append({"x": tickers, "y": vals, "name": name, "type": "bar"})

        layout = {
            "title": f"Peer Comparison — Key Metrics",
            "barmode": "group",
            "template": "plotly_white",
            "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
            "height": 400,
            "margin": {"t": 50, "b": 50, "l": 60, "r": 30},
        }

        return ReportVisual(
            visual_type="plotly_json",
            title="Peer Comparison — Key Metrics",
            content=json.dumps({"traces": traces, "layout": layout}),
            ties_to="Competitive positioning (Step 3)",
            caption=f"Comparison of {target_ticker} sector peers.",
        )

    @staticmethod
    def plotly_risk_heatmap(risk_matrix: RiskMatrix) -> ReportVisual | None:
        """Risk heatmap (Probability x Impact) as Plotly.js JSON."""
        if not risk_matrix.risks:
            return None

        prob_map = {"Low (<20%)": 1, "Medium (20-50%)": 2, "High (>50%)": 3}
        impact_map = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}

        x_vals = []
        y_vals = []
        labels = []
        sizes = []
        colors = []

        for r in risk_matrix.risks:
            x = prob_map.get(r.probability, 1)
            y = impact_map.get(r.impact, 1)
            x_vals.append(x)
            y_vals.append(y)
            labels.append(r.title[:30])
            sizes.append(20 + x * y * 5)
            severity = x * y
            colors.append("#dc2626" if severity >= 8 else "#ea580c" if severity >= 4 else "#16a34a")

        traces = [{
            "x": x_vals, "y": y_vals, "mode": "markers+text", "type": "scatter",
            "marker": {"size": sizes, "color": colors, "opacity": 0.7, "line": {"width": 1, "color": "white"}},
            "text": labels, "textposition": "top center", "textfont": {"size": 9},
        }]

        layout = {
            "title": "Risk Matrix — Probability vs Impact",
            "template": "plotly_white", "height": 380, "showlegend": False,
            "xaxis": {"title": "Probability", "tickvals": [1, 2, 3], "ticktext": ["Low", "Medium", "High"], "range": [0.5, 3.5]},
            "yaxis": {"title": "Impact", "tickvals": [1, 2, 3, 4], "ticktext": ["Low", "Medium", "High", "Critical"], "range": [0.5, 4.5]},
            "shapes": [
                {"type": "rect", "x0": 0.5, "y0": 0.5, "x1": 1.5, "y1": 2.5, "fillcolor": "#dcfce7", "opacity": 0.3, "layer": "below", "line": {"width": 0}},
                {"type": "rect", "x0": 1.5, "y0": 0.5, "x1": 2.5, "y1": 2.5, "fillcolor": "#fef9c3", "opacity": 0.3, "layer": "below", "line": {"width": 0}},
                {"type": "rect", "x0": 2.5, "y0": 0.5, "x1": 3.5, "y1": 4.5, "fillcolor": "#fecaca", "opacity": 0.3, "layer": "below", "line": {"width": 0}},
                {"type": "rect", "x0": 0.5, "y0": 2.5, "x1": 2.5, "y1": 4.5, "fillcolor": "#fed7aa", "opacity": 0.3, "layer": "below", "line": {"width": 0}},
            ],
            "margin": {"t": 50, "b": 50, "l": 60, "r": 30},
        }

        return ReportVisual(
            visual_type="plotly_json",
            title="Risk Matrix — Probability vs Impact",
            content=json.dumps({"traces": traces, "layout": layout}),
            ties_to="Risk assessment (Step 5/6)",
            caption=f"Overall risk score: {risk_matrix.overall_risk_score}/10.",
        )

    # ------------------------------------------------------------------
    # Mermaid diagrams — raw syntax, frontend calls mermaid.render()
    # ------------------------------------------------------------------

    @staticmethod
    def mermaid_business_model(
        profile: CompanyProfile,
        revenue_segments: list[str] | None = None,
    ) -> ReportVisual:
        """Business model flowchart as raw Mermaid syntax."""
        name = profile.name.replace('"', "'")
        segments = revenue_segments or ["Products", "Services", "Subscriptions"]
        seg_lines = "\n".join(f"    R --> S{i}[{seg}]" for i, seg in enumerate(segments))

        diagram = f"""graph TD
    A[{name}] --> R[Revenue Streams]
{seg_lines}
    A --> C[Cost Structure]
    C --> COGS[Cost of Revenue]
    C --> OPEX[Operating Expenses]
    A --> M[Competitive Moat]
    M --> SCALE[Scale / Network Effects]
    M --> IP[IP / Technology]"""

        return ReportVisual(
            visual_type="mermaid",
            title=f"{profile.ticker} — Business Model Overview",
            content=diagram,
            ties_to="Business model and structural position (Step 1)",
            caption="Conceptual business model flow.",
        )

    @staticmethod
    def mermaid_decision_framework(
        ticker: str,
        favors: list[str],
        disfavors: list[str],
        catalysts: list[str],
    ) -> ReportVisual:
        """Decision tree as raw Mermaid syntax."""
        # Truncate and sanitize text for Mermaid (no special chars)
        def clean(s: str, maxlen: int = 40) -> str:
            """Sanitize text for Mermaid node labels. Strip all special chars."""
            c = s.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
            c = c.replace('"', "").replace("'", "").replace(">", "").replace("<", "")
            c = c.replace("&", "and").replace(";", ",").replace("#", "")
            return c[:maxlen]

        lines = [f"graph TD"]
        lines.append(f"    THESIS[{ticker} Investment Thesis]")
        lines.append(f"    THESIS --> F[Factors That Favor]")
        lines.append(f"    THESIS --> D[Factors That Disfavor]")
        lines.append(f"    THESIS --> CAT[Key Catalysts]")

        for i, f in enumerate(favors[:4]):
            lines.append(f"    F --> F{i}[{clean(f)}]")
        for i, d in enumerate(disfavors[:4]):
            lines.append(f"    D --> D{i}[{clean(d)}]")
        for i, c in enumerate(catalysts[:3]):
            lines.append(f"    CAT --> C{i}[{clean(c)}]")

        lines.append(f"    THESIS --> MON[Monitor]")
        lines.append(f"    MON --> M1[Earnings trajectory]")
        lines.append(f"    MON --> M2[Competitive dynamics]")
        lines.append(f"    MON --> M3[Macro regime change]")

        return ReportVisual(
            visual_type="mermaid",
            title=f"{ticker} — Decision Framework",
            content="\n".join(lines),
            ties_to="Investment thesis (Step 7)",
            caption="Favors/disfavors framing. Never buy/sell/hold.",
        )

    @staticmethod
    def mermaid_capital_allocation(
        ticker: str,
        capex_pct: float | None,
        buyback_pct: float | None,
        dividend_pct: float | None,
    ) -> ReportVisual:
        """Capital allocation flow as raw Mermaid syntax."""
        lines = [f"graph TD", f"    FCF[{ticker} Free Cash Flow]"]
        lines.append(f"    FCF --> ALLOC[Capital Allocation]")

        if capex_pct is not None:
            lines.append(f"    ALLOC --> CAPEX[Capex: {capex_pct:.0%} of FCF]")
        if buyback_pct is not None:
            lines.append(f"    ALLOC --> BUY[Buybacks: {buyback_pct:.0%} of FCF]")
        if dividend_pct is not None:
            lines.append(f"    ALLOC --> DIV[Dividends: {dividend_pct:.0%} of FCF]")
        lines.append(f"    ALLOC --> OTHER[Debt / M&A / Cash Build]")

        return ReportVisual(
            visual_type="mermaid",
            title=f"{ticker} — Capital Allocation Flow",
            content="\n".join(lines),
            ties_to="Capital allocation analysis (Step 4)",
            caption="FCF deployment breakdown. Most recent annual period.",
        )

    # ------------------------------------------------------------------
    # ASCII charts
    # ------------------------------------------------------------------

    @staticmethod
    def ascii_scenario_chart(valuation: ValuationRange) -> ReportVisual:
        """Mandatory ASCII scenario summary."""
        return ReportVisual(
            visual_type="ascii",
            title="Scenario-Based Valuation Summary",
            content=valuation.ascii_chart(),
            ties_to="Scenario-based valuation range",
            caption=f"Current price: ${valuation.current_price:.2f}.",
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
        rows = [
            "| Metric | Value |",
            "|--------|-------|",
            f"| **Company** | {profile.name} ({profile.ticker}) |",
            f"| **Sector / Industry** | {profile.sector} / {profile.industry} |",
        ]
        if profile.market_cap:
            rows.append(f"| **Market Cap** | ${float(profile.market_cap) / 1e9:.1f}B |")
        rows.append(f"| **Current Price** | ${current_price:.2f} |")

        if latest:
            if latest.revenue:
                rows.append(f"| **Revenue (Latest)** | ${float(latest.revenue) / 1e9:.2f}B |")
            if latest.operating_margin is not None:
                rows.append(f"| **Operating Margin** | {latest.operating_margin:.1%} |")
            if latest.net_margin is not None:
                rows.append(f"| **Net Margin** | {latest.net_margin:.1%} |")
            if latest.roe is not None:
                rows.append(f"| **ROE** | {latest.roe:.1%} |")
            if latest.debt_to_equity is not None:
                rows.append(f"| **Debt/Equity** | {latest.debt_to_equity:.2f}x |")
            if latest.eps_diluted is not None:
                rows.append(f"| **EPS (Diluted)** | ${latest.eps_diluted:.2f} |")
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
    def table_peer_comparison(target_ticker: str, peers: list[Competitor]) -> ReportVisual:
        """Peer comparison table."""
        if not peers:
            return ReportVisual(visual_type="table", title="Peer Comparison", content="*No peer data.*", ties_to="Competitive analysis")

        header = "| Ticker | Name | Mkt Cap ($B) | Gross Margin | Op Margin | P/E | EV/EBITDA | Rev Growth | ROE | D/E |"
        sep = "|--------|------|-------------|-------------|-----------|-----|-----------|------------|-----|-----|"
        rows = [header, sep]

        for p in peers[:8]:
            mc = f"${float(p.market_cap) / 1e9:.1f}" if p.market_cap else "N/A"
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
        sep = "|------|----------|------------|--------|--------|--------|"
        rows = [header, sep]

        for r in risks[:10]:
            rows.append(f"| {r.title} | {r.category.value.title()} | {r.probability} | {r.impact} | {r.timing.value.replace('_', ' ').title()} | {r.nature.value.title()} |")

        return ReportVisual(visual_type="table", title="Structured Risk Matrix", content="\n".join(rows), ties_to="Risk assessment (Step 5/6)")

    @staticmethod
    def table_financial_summary(financials: list[FinancialStatement]) -> ReportVisual:
        """Multi-period financial summary table."""
        if not financials:
            return ReportVisual(visual_type="table", title="Financial Summary", content="*No data.*", ties_to="Financial analysis")

        sorted_fin = sorted(financials, key=lambda f: f.period_end_date or __import__("datetime").date.min)[-5:]
        periods = [f.period for f in sorted_fin]
        header = "| Metric | " + " | ".join(periods) + " |"
        sep = "|--------|" + "|".join(["-------"] * len(periods)) + "|"

        def _row(label, getter, fmt="dec"):
            vals = []
            for f in sorted_fin:
                v = getter(f)
                if v is None:
                    vals.append("N/A")
                elif fmt == "dec":
                    vals.append(f"${float(v) / 1e9:.2f}B")
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
        sep = "|--------|---------|--------|---------------|-----------|"
        rows = [header, sep]

        for impl in implications:
            factor = getattr(impl, "factor", "")
            current = getattr(impl, "current_value", "N/A")
            regime = getattr(impl, "regime", "")
            impact = getattr(impl, "implication", "neutral")
            magnitude = getattr(impl, "magnitude", "")
            rows.append(f"| {factor} | {current} | {regime} | {impact.title()} | {magnitude.title()} |")

        return ReportVisual(visual_type="table", title="Macro Environment", content="\n".join(rows), ties_to="Macro context (Step 5)")
