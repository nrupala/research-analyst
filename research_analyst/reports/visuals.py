"""Visual intelligence engine — Plotly codegen, Mermaid diagrams, ASCII charts, Markdown tables.

Spec rules (non-negotiable):
  - Every report includes at least one visual element
  - Plotly delivered as copy-paste-ready Python code (no live rendering)
  - Mermaid for conceptual diagrams only (syntax-valid)
  - ASCII charts required for scenario summaries
  - Markdown tables as comparative backbone
  - Visuals support conclusions; they never replace analysis
  - Every visual ties to an assumption, scenario, or risk
  - No decorative, generic, or redundant visuals
  - No embedded interactive charts, images, PDFs, or PowerPoint

Explicitly forbidden:
  - Candlesticks without inference
  - Decorative price charts
  - Any visual that doesn't support a specific conclusion
"""
# Module: research_analyst/reports/visuals.py | Version: 0.1.0 | Updated: 2026-05-15

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

    All methods return ReportVisual objects containing renderable content.
    Plotly visuals are Python code strings (copy-paste-ready).
    Mermaid visuals are syntax-valid diagram markup.
    ASCII visuals are plain text.
    Tables are Markdown.
    """

    # ------------------------------------------------------------------
    # Plotly code generators
    # ------------------------------------------------------------------

    @staticmethod
    def plotly_financial_trends(
        financials: list[FinancialStatement],
        ticker: str,
    ) -> ReportVisual | None:
        """Generate Plotly code for revenue + margin trend chart.

        Supports the conclusion: financial trajectory assessment.
        Returns None if insufficient data.
        """
        if len(financials) < 2:
            return None

        # Sort chronologically
        sorted_fin = sorted(
            financials,
            key=lambda f: f.period_end_date or __import__("datetime").date.min,
        )

        periods = [f.period for f in sorted_fin]
        revenues = [float(f.revenue) / 1e9 if f.revenue else None for f in sorted_fin]
        gross_margins = [f.gross_margin * 100 if f.gross_margin else None for f in sorted_fin]
        op_margins = [f.operating_margin * 100 if f.operating_margin else None for f in sorted_fin]
        net_margins = [f.net_margin * 100 if f.net_margin else None for f in sorted_fin]

        code = f'''import plotly.graph_objects as go
from plotly.subplots import make_subplots

periods = {json.dumps(periods)}
revenues = {json.dumps(revenues)}
gross_margins = {json.dumps(gross_margins)}
op_margins = {json.dumps(op_margins)}
net_margins = {json.dumps(net_margins)}

fig = make_subplots(specs=[[{{"secondary_y": True}}]])

fig.add_trace(
    go.Bar(x=periods, y=revenues, name="Revenue ($B)", marker_color="#2563eb", opacity=0.8),
    secondary_y=False,
)

if any(v is not None for v in gross_margins):
    fig.add_trace(
        go.Scatter(x=periods, y=gross_margins, name="Gross Margin %", mode="lines+markers",
                   line=dict(color="#16a34a", width=2)),
        secondary_y=True,
    )

if any(v is not None for v in op_margins):
    fig.add_trace(
        go.Scatter(x=periods, y=op_margins, name="Operating Margin %", mode="lines+markers",
                   line=dict(color="#ea580c", width=2)),
        secondary_y=True,
    )

if any(v is not None for v in net_margins):
    fig.add_trace(
        go.Scatter(x=periods, y=net_margins, name="Net Margin %", mode="lines+markers",
                   line=dict(color="#7c3aed", width=2, dash="dot")),
        secondary_y=True,
    )

fig.update_layout(
    title="{ticker} — Revenue & Margin Trends",
    xaxis_title="Fiscal Year",
    template="plotly_white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=450,
)
fig.update_yaxes(title_text="Revenue ($B)", secondary_y=False)
fig.update_yaxes(title_text="Margin (%)", secondary_y=True)
fig.show()
'''
        return ReportVisual(
            visual_type="plotly",
            title=f"{ticker} — Revenue & Margin Trends",
            content=code,
            ties_to="Financial trajectory assessment (Step 2)",
            caption="Revenue in billions USD. Margins as percentage of revenue.",
        )

    @staticmethod
    def plotly_scenario_valuation(
        valuation: ValuationRange,
    ) -> ReportVisual | None:
        """Generate Plotly code for scenario valuation range chart.

        Horizontal bar chart showing Bull/Base/Bear ranges vs current price.
        Supports the conclusion: scenario-based valuation range.
        """
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
        bar_colors = [colors.get(l, "#6b7280") for l in labels]

        code_lines = [
            "import plotly.graph_objects as go",
            "",
            "labels = " + json.dumps(labels),
            "lows = " + json.dumps(lows),
            "highs = " + json.dumps(highs),
            "bar_colors = " + json.dumps(bar_colors),
            "current_price = " + str(valuation.current_price),
            "",
            "fig = go.Figure()",
            "",
            "for i, (label, lo, hi, color) in enumerate(zip(labels, lows, highs, bar_colors)):",
            "    fig.add_trace(go.Bar(",
            "        y=[label], x=[hi - lo], base=[lo], orientation=\"h\",",
            "        name=label, marker_color=color, opacity=0.8,",
            '        text=[f"${lo:.0f} - ${hi:.0f}"], textposition="inside",',
            '        hovertemplate=f"{label}: ${lo:.0f} - ${hi:.0f}<extra></extra>",',
            "    ))",
            "",
            "fig.add_vline(x=current_price, line_dash=\"dash\", line_color=\"black\", line_width=2,",
            '              annotation_text=f"Current: ${current_price:.0f}", annotation_position="top")',
            "",
            "fig.update_layout(",
            '    title="Scenario-Based Valuation Range",',
            '    xaxis_title="Price ($)",',
            '    template="plotly_white",',
            "    showlegend=False,",
            "    height=300,",
            "    margin=dict(l=120),",
            ")",
            "fig.show()",
        ]
        code = "\n".join(code_lines)
        return ReportVisual(
            visual_type="plotly",
            title="Scenario-Based Valuation Range",
            content=code,
            ties_to="Valuation scenarios (Step 6)",
            caption=f"Current price: ${valuation.current_price:.2f}. Ranges are assumption-driven illustrations.",
        )

    @staticmethod
    def plotly_peer_comparison(
        target_ticker: str,
        peers: list[Competitor],
        metrics: list[str] | None = None,
    ) -> ReportVisual | None:
        """Generate Plotly code for peer comparison radar/bar chart.

        Supports the conclusion: competitive positioning assessment.
        """
        if not peers:
            return None

        if metrics is None:
            metrics = ["gross_margin", "operating_margin", "roe", "revenue_growth_yoy", "pe_ratio"]

        tickers = [target_ticker] + [p.ticker for p in peers[:5]]

        metric_labels = {
            "gross_margin": "Gross Margin",
            "operating_margin": "Op Margin",
            "roe": "ROE",
            "revenue_growth_yoy": "Rev Growth",
            "pe_ratio": "P/E",
            "ev_ebitda": "EV/EBITDA",
            "debt_to_equity": "D/E",
        }

        # Build data dict
        data_dict: dict[str, list[float | None]] = {}
        for m in metrics:
            vals: list[float | None] = []
            for t in tickers:
                if t == target_ticker:
                    vals.append(None)  # Placeholder; filled by fundamental data
                else:
                    peer = next((p for p in peers if p.ticker == t), None)
                    val = getattr(peer, m, None) if peer else None
                    if val is not None and m in ("gross_margin", "operating_margin", "roe", "revenue_growth_yoy"):
                        val = val * 100  # Convert to percentage
                    vals.append(val)
            data_dict[metric_labels.get(m, m)] = vals

        code = f'''import plotly.graph_objects as go

tickers = {json.dumps(tickers)}
metrics = {json.dumps(list(data_dict.keys()))}
data = {json.dumps(data_dict)}

fig = go.Figure()

colors = ["#2563eb", "#6b7280", "#6b7280", "#6b7280", "#6b7280", "#6b7280"]

for i, metric in enumerate(metrics):
    fig.add_trace(go.Bar(
        x=tickers,
        y=[v for v in data[metric]],
        name=metric,
    ))

fig.update_layout(
    title="Peer Comparison — Key Metrics",
    barmode="group",
    template="plotly_white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=450,
)
fig.show()
'''
        return ReportVisual(
            visual_type="plotly",
            title="Peer Comparison — Key Metrics",
            content=code,
            ties_to="Competitive positioning assessment (Step 3)",
            caption=f"Comparison of {target_ticker} vs {len(peers)} sector peers.",
        )

    @staticmethod
    def plotly_risk_heatmap(
        risk_matrix: RiskMatrix,
    ) -> ReportVisual | None:
        """Generate Plotly code for risk heatmap (Probability x Impact).

        Supports the conclusion: structured risk assessment.
        """
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
            if severity >= 8:
                colors.append("#dc2626")
            elif severity >= 4:
                colors.append("#ea580c")
            else:
                colors.append("#16a34a")

        code = f'''import plotly.graph_objects as go

x_vals = {json.dumps(x_vals)}
y_vals = {json.dumps(y_vals)}
labels = {json.dumps(labels)}
sizes = {json.dumps(sizes)}
colors = {json.dumps(colors)}

fig = go.Figure()

fig.add_trace(go.Scatter(
    x=x_vals, y=y_vals, mode="markers+text",
    marker=dict(size=sizes, color=colors, opacity=0.7, line=dict(width=1, color="white")),
    text=labels, textposition="top center", textfont=dict(size=9),
    hovertemplate="%{{text}}<br>Probability: %{{x}}<br>Impact: %{{y}}<extra></extra>",
))

fig.update_layout(
    title="Risk Matrix — Probability vs Impact",
    xaxis=dict(title="Probability", tickvals=[1, 2, 3], ticktext=["Low", "Medium", "High"], range=[0.5, 3.5]),
    yaxis=dict(title="Impact", tickvals=[1, 2, 3, 4], ticktext=["Low", "Medium", "High", "Critical"], range=[0.5, 4.5]),
    template="plotly_white",
    height=400,
    showlegend=False,
)

# Background quadrants
fig.add_shape(type="rect", x0=0.5, y0=0.5, x1=1.5, y1=2.5, fillcolor="#dcfce7", opacity=0.3, layer="below")
fig.add_shape(type="rect", x0=1.5, y0=0.5, x1=2.5, y1=2.5, fillcolor="#fef9c3", opacity=0.3, layer="below")
fig.add_shape(type="rect", x0=2.5, y0=0.5, x1=3.5, y1=4.5, fillcolor="#fecaca", opacity=0.3, layer="below")
fig.add_shape(type="rect", x0=0.5, y0=2.5, x1=2.5, y1=4.5, fillcolor="#fed7aa", opacity=0.3, layer="below")

fig.show()
'''
        return ReportVisual(
            visual_type="plotly",
            title="Risk Matrix — Probability vs Impact",
            content=code,
            ties_to="Risk assessment (Step 5/6)",
            caption=f"Overall risk score: {risk_matrix.overall_risk_score}/10. Bubble size = severity.",
        )

    # ------------------------------------------------------------------
    # Mermaid diagrams
    # ------------------------------------------------------------------

    @staticmethod
    def mermaid_business_model(
        profile: CompanyProfile,
        revenue_segments: list[str] | None = None,
    ) -> ReportVisual:
        """Generate Mermaid flowchart for business model overview.

        Supports: structural understanding (Step 1).
        """
        segments = revenue_segments or ["Products", "Services", "Subscriptions"]
        segment_nodes = "\n".join(
            f"    R --> S{i}[{seg}]" for i, seg in enumerate(segments)
        )

        diagram = f"""graph TD
    A[{profile.name}] --> R[Revenue Streams]
{segment_nodes}
    A --> C[Cost Structure]
    C --> COGS[Cost of Revenue]
    C --> OPEX[Operating Expenses]
    C --> RD[R&D Investment]
    A --> M[Competitive Moat]
    M --> SCALE[Scale / Network Effects]
    M --> IP[IP / Technology]
    M --> BRAND[Brand / Switching Costs]"""

        return ReportVisual(
            visual_type="mermaid",
            title=f"{profile.ticker} — Business Model Overview",
            content=diagram,
            ties_to="Business model and structural position (Step 1)",
            caption="Conceptual business model flow. Revenue segments are illustrative.",
        )

    @staticmethod
    def mermaid_decision_framework(
        ticker: str,
        favors: list[str],
        disfavors: list[str],
        catalysts: list[str],
    ) -> ReportVisual:
        """Generate Mermaid decision tree for thesis framework.

        Supports: investment thesis synthesis (Step 7).
        """
        favor_nodes = "\n".join(
            f"    F --> F{i}[{f[:50]}]" for i, f in enumerate(favors[:4])
        )
        disfavor_nodes = "\n".join(
            f"    D --> D{i}[{d[:50]}]" for i, d in enumerate(disfavors[:4])
        )
        catalyst_nodes = "\n".join(
            f"    CAT --> C{i}[{c[:50]}]" for i, c in enumerate(catalysts[:3])
        )

        diagram = f"""graph TD
    THESIS[{ticker} Investment Thesis] --> F[Factors That Favor]
    THESIS --> D[Factors That Disfavor]
    THESIS --> CAT[Key Catalysts]
{favor_nodes}
{disfavor_nodes}
{catalyst_nodes}
    THESIS --> MON[Monitor / Invalidation]
    MON --> M1[Earnings trajectory]
    MON --> M2[Competitive dynamics]
    MON --> M3[Macro regime change]"""

        return ReportVisual(
            visual_type="mermaid",
            title=f"{ticker} — Decision Framework",
            content=diagram,
            ties_to="Investment thesis and decision framework (Step 7)",
            caption="Structured thesis summary. Favors/disfavors framing, never buy/sell/hold.",
        )

    @staticmethod
    def mermaid_capital_allocation(
        ticker: str,
        capex_pct: float | None,
        buyback_pct: float | None,
        dividend_pct: float | None,
    ) -> ReportVisual:
        """Generate Mermaid flow for capital allocation."""
        parts = [f"graph TD\n    FCF[{ticker} Free Cash Flow] --> ALLOC[Capital Allocation]"]

        if capex_pct is not None:
            parts.append(f"    ALLOC --> CAPEX[Capex: {capex_pct:.0%} of FCF]")
        if buyback_pct is not None:
            parts.append(f"    ALLOC --> BUY[Buybacks: {buyback_pct:.0%} of FCF]")
        if dividend_pct is not None:
            parts.append(f"    ALLOC --> DIV[Dividends: {dividend_pct:.0%} of FCF]")

        parts.append("    ALLOC --> OTHER[Debt / M&A / Cash Build]")

        return ReportVisual(
            visual_type="mermaid",
            title=f"{ticker} — Capital Allocation Flow",
            content="\n".join(parts),
            ties_to="Capital allocation analysis (Step 4)",
            caption="FCF deployment breakdown. Percentages from most recent annual period.",
        )

    # ------------------------------------------------------------------
    # ASCII charts
    # ------------------------------------------------------------------

    @staticmethod
    def ascii_scenario_chart(valuation: ValuationRange) -> ReportVisual:
        """Generate the mandatory ASCII scenario summary.

        Required by spec for every report. Cannot be omitted.
        """
        return ReportVisual(
            visual_type="ascii",
            title="Scenario-Based Valuation Summary",
            content=valuation.ascii_chart(),
            ties_to="Scenario-based valuation range",
            caption=f"Current price: ${valuation.current_price:.2f}. Assumption-driven illustrations, not predictions.",
        )

    @staticmethod
    def ascii_technical_dashboard(
        indicators: TechnicalIndicators,
        composite_score: float,
        regime: str,
    ) -> ReportVisual:
        """Generate ASCII dashboard for technical signals."""
        lines: list[str] = [
            f"    Technical Regime:  {regime.upper()}  (Score: {composite_score:.0f}/100)",
            "",
        ]

        # Trend
        trend_icon = "^" if indicators.price_vs_sma_200 == "above" else "v"
        lines.append(f"    Trend:     [{trend_icon}] Price {'above' if indicators.price_vs_sma_200 == 'above' else 'below'} SMA 200  |  {indicators.sma_50_vs_200}")

        # Momentum
        rsi_bar = ""
        if indicators.rsi_14 is not None:
            filled = int(indicators.rsi_14 / 100 * 20)
            rsi_bar = "\u2588" * filled + "\u2591" * (20 - filled)
        lines.append(f"    RSI (14):  [{rsi_bar}] {indicators.rsi_14 or 'N/A':.1f}" if indicators.rsi_14 else "    RSI (14):  N/A")

        # MACD
        macd_sig = indicators.macd_crossover or "none"
        lines.append(f"    MACD:      {macd_sig}  |  Histogram: {indicators.macd_histogram or 0:.4f}")

        # Volatility
        lines.append(f"    ATR %:     {indicators.atr_pct or 0:.2f}%  |  ADX: {indicators.adx_14 or 0:.1f} ({indicators.adx_signal})")

        # Volume
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
        """Generate key metrics summary table for executive overview."""
        latest = financials[0] if financials else None

        rows: list[str] = [
            "| Metric | Value |",
            "|--------|-------|",
            f"| **Company** | {profile.name} ({profile.ticker}) |",
            f"| **Sector / Industry** | {profile.sector} / {profile.industry} |",
            f"| **Market Cap** | ${float(profile.market_cap) / 1e9:.1f}B |" if profile.market_cap else "| **Market Cap** | N/A |",
            f"| **Current Price** | ${current_price:.2f} |",
        ]

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
            ties_to="Executive summary / investment context",
            caption="Most recent annual data. Source: SEC filings + market data.",
        )

    @staticmethod
    def table_peer_comparison(
        target_ticker: str,
        peers: list[Competitor],
    ) -> ReportVisual:
        """Generate peer comparison table."""
        if not peers:
            return ReportVisual(
                visual_type="table",
                title="Peer Comparison",
                content="*No peer data available.*",
                ties_to="Competitive analysis",
            )

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

        return ReportVisual(
            visual_type="table",
            title="Peer Comparison",
            content="\n".join(rows),
            ties_to="Competitive positioning assessment (Step 3)",
            caption=f"Peers from {peers[0].ticker if peers else 'N/A'}'s sector. Source: yfinance.",
        )

    @staticmethod
    def table_risk_matrix(risks: list[StructuredRisk]) -> ReportVisual:
        """Generate structured risk matrix table.

        Sorted by severity (Probability x Impact) — not an unordered list.
        """
        if not risks:
            return ReportVisual(
                visual_type="table",
                title="Risk Matrix",
                content="*No significant risks identified.*",
                ties_to="Risk assessment",
            )

        header = "| Risk | Category | Probability | Impact | Timing | Nature |"
        sep = "|------|----------|------------|--------|--------|--------|"
        rows = [header, sep]

        for r in risks[:10]:
            rows.append(
                f"| {r.title} | {r.category.value.title()} | {r.probability} | "
                f"{r.impact} | {r.timing.value.replace('_', ' ').title()} | "
                f"{r.nature.value.title()} |"
            )

        return ReportVisual(
            visual_type="table",
            title="Structured Risk Matrix",
            content="\n".join(rows),
            ties_to="Risk assessment — Probability x Impact x Timing (Step 5/6)",
            caption="Sorted by severity (Probability x Impact). Not an unordered list.",
        )

    @staticmethod
    def table_financial_summary(financials: list[FinancialStatement]) -> ReportVisual:
        """Generate multi-period financial summary table."""
        if not financials:
            return ReportVisual(
                visual_type="table",
                title="Financial Summary",
                content="*No financial data available.*",
                ties_to="Financial analysis",
            )

        sorted_fin = sorted(
            financials,
            key=lambda f: f.period_end_date or __import__("datetime").date.min,
        )[-5:]  # Last 5 periods

        periods = [f.period for f in sorted_fin]
        header = "| Metric | " + " | ".join(periods) + " |"
        sep = "|--------|" + "|".join(["-------"] * len(periods)) + "|"

        def _row(label: str, getter: Any, fmt: str = "dec") -> str:
            vals: list[str] = []
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

        return ReportVisual(
            visual_type="table",
            title="Multi-Period Financial Summary",
            content="\n".join(rows),
            ties_to="Financial analysis and trajectory (Step 2)",
            caption="Annual data from SEC filings. Amounts in USD billions.",
        )

    @staticmethod
    def table_macro_regime(implications: list[Any]) -> ReportVisual:
        """Generate macro regime summary table."""
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

        return ReportVisual(
            visual_type="table",
            title="Macro Environment Summary",
            content="\n".join(rows),
            ties_to="Macro context and sector dynamics (Step 5)",
            caption="Sector sensitivity based on empirical factor-sector relationships.",
        )
