"""Report renderer — assembles analysis outputs into complete 7-step Markdown reports.

This is the final assembly layer. It takes:
  - A ReportTemplate (the 7-step structure)
  - All analysis outputs (fundamental, technical, macro, competitive, valuation, risk)
  - Visual elements from VisualEngine

And produces a complete ReportOutput with every section populated, every assumption
traced, and every visual tied to a conclusion.

Design:
  - Deterministic: same inputs always produce the same report
  - Template-driven: section titles come from templates, never invented
  - Data-gap transparent: missing data is explicitly called out, never silently skipped
  - Visual enforcement: at least one visual per report (spec mandate)
"""
# Module: research_analyst/reports/renderer.py | Version: 0.1.1 | Updated: 2026-06-02

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..enums import ReportType, SecurityType
from ..models import (
    Assumption,
    CapitalAllocation,
    CompanyProfile,
    FinancialStatement,
    PriceSeries,
    ReportOutput,
    ReportSection,
    ReportVisual,
    RiskMatrix,
    TechnicalIndicators,
    ValuationRange,
)
from .templates import ReportTemplate, StepTemplate, get_template
from .visuals import VisualEngine
from .currency import money

logger = logging.getLogger(__name__)


class ReportRenderer:
    """Assembles analysis into complete research reports.

    Usage:
        renderer = ReportRenderer()
        report = renderer.render(
            report_type=ReportType.COMPREHENSIVE,
            profile=profile,
            prices=prices,
            financials=financials,
            fundamental=fundamental_analysis,
            technical_indicators=indicators,
            technical=technical_analysis,
            macro=macro_analysis,
            competitive=competitive_analysis,
            valuation=valuation_range,
            risk_matrix=risk_matrix,
        )
    """

    def __init__(self) -> None:
        self._visuals = VisualEngine()

    def render(
        self,
        report_type: ReportType,
        profile: CompanyProfile,
        prices: PriceSeries,
        financials: list[FinancialStatement],
        fundamental: Any = None,
        technical_indicators: TechnicalIndicators | None = None,
        technical: Any = None,
        macro: Any = None,
        competitive: Any = None,
        valuation: ValuationRange | None = None,
        risk_matrix: RiskMatrix | None = None,
        capital_allocation: CapitalAllocation | None = None,
        dividend: Any = None,
    ) -> ReportOutput:
        """Render a complete report from analysis outputs.

        Follows the exact 7-step template for the given report type.
        Never reorders, merges, renames, or skips steps.

        Args:
            report_type: Which of the three report modes to render.
            profile: Company/ETF profile.
            prices: Price series with current price.
            financials: Financial statements.
            fundamental: FundamentalAnalysis output.
            technical_indicators: Raw TechnicalIndicators.
            technical: TechnicalAnalysis output (scored/interpreted).
            macro: MacroAnalysis output.
            competitive: CompetitiveAnalysis output.
            valuation: ValuationRange with scenarios.
            risk_matrix: RiskMatrix with structured risks.
            capital_allocation: CapitalAllocation analysis.

        Returns:
            Complete ReportOutput ready for Markdown serialization.
        """
        template = get_template(report_type)

        # Pack all data into a context dict for step renderers
        ctx: dict[str, Any] = {
            "profile": profile,
            "prices": prices,
            "financials": financials,
            "fundamental": fundamental,
            "technical_indicators": technical_indicators,
            "technical": technical,
            "macro": macro,
            "competitive": competitive,
            "valuation": valuation,
            "risk_matrix": risk_matrix,
            "capital_allocation": capital_allocation,
            "dividend": dividend,
        }

        sections: list[ReportSection] = []
        visual_count = 0

        for step_tmpl in template.steps:
            section, n_visuals = self._render_step(step_tmpl, report_type, ctx)
            sections.append(section)
            visual_count += n_visuals

        # Visual enforcement: if zero visuals, log warning (spec violation)
        if visual_count == 0:
            logger.warning(
                "Report for %s (%s) has zero visuals. "
                "Spec requires at least one visual per report.",
                profile.ticker, report_type.value,
            )

        title = template.title_format.format(ticker=profile.ticker)

        return ReportOutput(
            report_type=report_type,
            ticker=profile.ticker,
            title=title,
            generated_at=datetime.now(timezone.utc),
            sections=sections,
            valuation=valuation,
            risk_matrix=risk_matrix,
            capital_allocation=capital_allocation,
            dividend=dividend,
        )

    # ------------------------------------------------------------------
    # Step renderers — dispatch by report type + step number
    # ------------------------------------------------------------------

    def _render_step(
        self,
        step: StepTemplate,
        report_type: ReportType,
        ctx: dict[str, Any],
    ) -> tuple[ReportSection, int]:
        """Render a single step. Returns (section, visual_count)."""

        # Dispatch to type-specific renderer if it exists,
        # otherwise use generic renderer
        renderer_key = f"_render_{report_type.value}_step{step.step_number}"
        renderer = getattr(self, renderer_key, None)

        if renderer is not None:
            return renderer(step, ctx)

        # Fallback: generic step renderer
        return self._render_generic_step(step, ctx)

    # ------------------------------------------------------------------
    # Dividend & yield block — shared across report types (v0.1.1)
    # ------------------------------------------------------------------

    def _build_dividend_block(
        self, ctx: dict[str, Any], *, compact: bool = False
    ) -> tuple[list[str], list[ReportVisual], list[Assumption], list[str]]:
        """Build the dividend & yield sub-section injected into the relevant step
        of every report type. Returns (parts, visuals, assumptions, gaps).

        compact=True (tactical) emits an income/event-focused subset: yield,
        yield vs 10Y Treasury, and the ex-dividend date. Full mode adds growth,
        payout, consistency, safety, peer comparison, and a history chart.
        """
        div = ctx.get("dividend")
        parts: list[str] = []
        visuals: list[ReportVisual] = []
        assumptions: list[Assumption] = []
        gaps: list[str] = []

        if div is None:
            return parts, visuals, assumptions, gaps

        label = getattr(div, "income_label", "Dividend")
        parts.append(f"### {label} & Yield Analysis")

        if not getattr(div, "pays_dividend", False):
            context = getattr(div, "no_dividend_context", "") or "No dividend currently paid."
            parts.append(f"- **{label}:** None. {context}")
            parts.append("")
            assumptions.extend(getattr(div, "assumptions", []))
            gaps.extend(getattr(div, "data_gaps", []))
            return parts, visuals, assumptions, gaps

        if div.current_yield is not None:
            ylabel = "Distribution yield" if div.is_etf else "Dividend yield"
            rate = f" forward ({money(div.annual_dividend_rate, ctx['profile'].currency)}/share)" if div.annual_dividend_rate else ""
            parts.append(f"- {ylabel}: **{div.current_yield:.2%}**{rate}")
        if div.us_10y_yield is not None and div.yield_vs_treasury_spread is not None:
            rel = "above" if div.yield_vs_treasury_spread > 0 else "below"
            parts.append(
                f"- vs 10Y Treasury ({div.us_10y_yield:.2%}): "
                f"**{abs(div.yield_vs_treasury_spread) * 100:.0f} bps {rel}**"
            )
        if compact and div.ex_dividend_date is not None:
            parts.append(f"- Ex-dividend date: **{div.ex_dividend_date.isoformat()}** (near-term event)")

        if not compact:
            if div.peer_median_yield is not None:
                parts.append(
                    f"- vs peer median ({div.peer_median_yield:.2%}): "
                    f"**{div.yield_vs_peers or 'n/a'}**"
                )
            growth_bits: list[str] = []
            if div.dividend_growth_1y is not None:
                growth_bits.append(f"1Y {div.dividend_growth_1y:.1%}")
            if div.dividend_growth_3y_cagr is not None:
                growth_bits.append(f"3Y CAGR {div.dividend_growth_3y_cagr:.1%}")
            if div.dividend_growth_5y_cagr is not None:
                growth_bits.append(f"5Y CAGR {div.dividend_growth_5y_cagr:.1%}")
            if growth_bits:
                parts.append(f"- Dividend growth: **{', '.join(growth_bits)}**")
            payout_bits: list[str] = []
            if div.payout_ratio_eps is not None:
                payout_bits.append(f"{div.payout_ratio_eps:.0%} of EPS")
            if div.payout_ratio_fcf is not None:
                payout_bits.append(f"{div.payout_ratio_fcf:.0%} of FCF")
            if payout_bits:
                parts.append(f"- Payout ratio: **{' / '.join(payout_bits)}**")
            if div.consecutive_increase_years:
                parts.append(
                    f"- Consecutive annual increases: **{div.consecutive_increase_years} years**"
                )
            if div.had_cut:
                sc = (
                    f"{div.years_since_cut} years ago"
                    if div.years_since_cut is not None else "in history"
                )
                parts.append(f"- Dividend cut: **{sc}**")
            if div.safety_score is not None:
                parts.append(
                    f"- Safety score: **{div.safety_score:.0f}/100 ({div.safety_grade})**"
                )

        if div.attractiveness_rating:
            rationale = f" — {div.attractiveness_rationale}" if div.attractiveness_rationale else ""
            parts.append(f"- Attractiveness: **{div.attractiveness_rating}**{rationale}")
        parts.append("")

        visuals.append(VisualEngine.table_dividend_summary(div))
        if not compact:
            chart = VisualEngine.plotly_dividend_history(div)
            if chart:
                visuals.append(chart)

        assumptions.extend(getattr(div, "assumptions", []))
        gaps.extend(getattr(div, "data_gaps", []))
        return parts, visuals, assumptions, gaps

    # ------------------------------------------------------------------
    # Comprehensive report step renderers
    # ------------------------------------------------------------------

    def _build_etf_block(
        self, ctx: dict[str, Any]
    ) -> tuple[list[str], list[ReportVisual], list[Assumption], list[str]]:
        """ETF-as-subject overview block (Slice B, Option A).

        Surfaces fund overview + assets under management from fields the
        profile already carries. Expense ratio, distribution yield, tracking
        index and holdings are deferred to Slice B-B and recorded as data
        gaps. Returns empty lists for non-ETF subjects (equity path unchanged).
        """
        profile: CompanyProfile = ctx["profile"]
        parts: list[str] = []
        visuals: list[ReportVisual] = []
        assumptions: list[Assumption] = []
        gaps: list[str] = []

        if profile.security_type is not SecurityType.ETF:
            return parts, visuals, assumptions, gaps

        parts.append("### ETF Overview")
        if profile.description:
            parts.append(f"**Strategy:** {profile.description[:500]}")
        else:
            gaps.append("ETF strategy description unavailable.")

        if profile.market_cap:
            parts.append(
                f"**Assets Under Management:** "
                f"{money(profile.market_cap, profile.currency)}"
            )
            assumptions.append(
                Assumption(
                    label="Assets Under Management",
                    value=money(profile.market_cap, profile.currency),
                    source="market_cap from security profile (AUM proxy)",
                )
            )
        else:
            gaps.append("Assets under management unavailable.")

        gaps.append(
            "Expense ratio, distribution yield, tracking index and top "
            "holdings pending ETF-metadata integration (Slice B-B)."
        )
        return parts, visuals, assumptions, gaps

    def _render_comprehensive_step1(
        self, step: StepTemplate, ctx: dict[str, Any]
    ) -> tuple[ReportSection, int]:
        """Step 1: Executive Summary & Investment Context."""
        profile: CompanyProfile = ctx["profile"]
        prices: PriceSeries = ctx["prices"]
        financials: list[FinancialStatement] = ctx["financials"]
        fundamental = ctx.get("fundamental")

        parts: list[str] = []
        visuals: list[ReportVisual] = []
        assumptions: list[Assumption] = []
        gaps: list[str] = []

        # Company description
        if profile.description:
            parts.append(profile.description[:500])
            parts.append("")

        # ETF-as-subject overview (Slice B)
        etf_parts, etf_visuals, etf_assumptions, etf_gaps = self._build_etf_block(ctx)
        if etf_parts:
            parts.extend(etf_parts)
            parts.append("")
            visuals.extend(etf_visuals)
            assumptions.extend(etf_assumptions)
            gaps.extend(etf_gaps)

        # Price context
        parts.append(f"**Current Price:** {money(prices.current_price, profile.currency)}")
        if prices.price_52w_high > 0:
            parts.append(
                f"**52-Week Range:** {money(prices.price_52w_low, profile.currency)} - {money(prices.price_52w_high, profile.currency)}"
            )
        if prices.ytd_return:
            parts.append(f"**YTD Return:** {prices.ytd_return:.1%}")
        parts.append("")

        # Key metrics table
        pe = None
        if financials and financials[0].eps_diluted and financials[0].eps_diluted > 0:
            pe = prices.current_price / financials[0].eps_diluted

        table = VisualEngine.table_key_metrics(profile, financials, prices.current_price, pe)
        visuals.append(table)

        # Fundamental headline
        if fundamental:
            rev_growth = getattr(fundamental, "revenue_growth_yoy", None)
            op_margin = getattr(fundamental, "operating_margin_latest", None)
            bs_grade = getattr(fundamental, "balance_sheet_grade", "")
            eq_grade = getattr(fundamental, "earnings_quality_grade", "")

            if rev_growth is not None:
                parts.append(f"**Revenue Growth (YoY):** {rev_growth:.1%}")
            if op_margin is not None:
                parts.append(f"**Operating Margin:** {op_margin:.1%}")
            if bs_grade:
                parts.append(f"**Balance Sheet:** {bs_grade}")
            if eq_grade:
                parts.append(f"**Earnings Quality:** {eq_grade}")
        else:
            gaps.append("Fundamental analysis not available.")

        return ReportSection(
            step_number=step.step_number,
            title=step.title,
            content="\n".join(parts),
            visuals=visuals,
            assumptions=assumptions,
            data_gaps=gaps,
        ), len(visuals)

    def _render_comprehensive_step2(
        self, step: StepTemplate, ctx: dict[str, Any]
    ) -> tuple[ReportSection, int]:
        """Step 2: Fundamental Analysis & Financial Trajectory."""
        financials: list[FinancialStatement] = ctx["financials"]
        fundamental = ctx.get("fundamental")
        profile: CompanyProfile = ctx["profile"]

        parts: list[str] = []
        visuals: list[ReportVisual] = []
        assumptions: list[Assumption] = []
        gaps: list[str] = []

        if not financials:
            parts.append("**Data Gap:** No financial statements available from SEC or market data providers.")
            gaps.append("Financial statements unavailable.")
            return ReportSection(
                step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps,
            ), 0

        # Financial summary table
        fin_table = VisualEngine.table_financial_summary(financials)
        visuals.append(fin_table)

        # Plotly trend chart
        plotly_chart = VisualEngine.plotly_financial_trends(financials, profile.ticker)
        if plotly_chart:
            visuals.append(plotly_chart)

        # Fundamental narrative
        if fundamental:
            parts.append("### Growth")
            rev_growth = getattr(fundamental, "revenue_growth_yoy", None)
            cagr_3 = getattr(fundamental, "revenue_cagr_3y", None)
            cagr_5 = getattr(fundamental, "revenue_cagr_5y", None)

            if rev_growth is not None:
                parts.append(f"- Revenue growth (YoY): **{rev_growth:.1%}**")
            if cagr_3 is not None:
                parts.append(f"- Revenue CAGR (3Y): **{cagr_3:.1%}**")
            if cagr_5 is not None:
                parts.append(f"- Revenue CAGR (5Y): **{cagr_5:.1%}**")
            parts.append("")

            parts.append("### Profitability")
            gm = getattr(fundamental, "gross_margin_latest", None)
            gm_trend = getattr(fundamental, "gross_margin_trend", "")
            om = getattr(fundamental, "operating_margin_latest", None)
            om_trend = getattr(fundamental, "operating_margin_trend", "")
            fcf_margin = getattr(fundamental, "fcf_margin_latest", None)

            if gm is not None:
                parts.append(f"- Gross margin: **{gm:.1%}** (trend: {gm_trend})")
            if om is not None:
                parts.append(f"- Operating margin: **{om:.1%}** (trend: {om_trend})")
            if fcf_margin is not None:
                parts.append(f"- FCF margin: **{fcf_margin:.1%}**")
            parts.append("")

            parts.append("### Balance Sheet & Earnings Quality")
            bs = getattr(fundamental, "balance_sheet_grade", "")
            eq = getattr(fundamental, "earnings_quality_grade", "")
            nd_ebitda = getattr(fundamental, "net_debt_to_ebitda", None)

            if bs:
                parts.append(f"- Balance sheet grade: **{bs}**")
            if eq:
                parts.append(f"- Earnings quality: **{eq}**")
            if nd_ebitda is not None:
                parts.append(f"- Net Debt / EBITDA: **{nd_ebitda:.1f}x**")
            parts.append("")

            # Capital allocation
            cap_alloc = getattr(fundamental, "capital_allocation", None)
            if cap_alloc:
                parts.append("### Capital Allocation")
                roic = getattr(cap_alloc, "roic", None)
                roic_wacc = getattr(cap_alloc, "roic_minus_wacc", None)
                assessment = getattr(cap_alloc, "assessment", "")

                if roic is not None:
                    parts.append(f"- ROIC: **{roic:.1%}**")
                if roic_wacc is not None:
                    spread_label = "above" if roic_wacc > 0 else "below"
                    parts.append(f"- ROIC vs WACC: **{abs(roic_wacc):.1%} {spread_label}** cost of capital")
                if assessment:
                    parts.append(f"- Assessment: {assessment}")

                # Mermaid capital allocation
                capex_pct = getattr(cap_alloc, "capex_pct_of_fcf", None)
                buyback_pct = getattr(cap_alloc, "buyback_pct_of_fcf", None)
                div_pct = getattr(cap_alloc, "dividend_pct_of_fcf", None)
                mermaid = VisualEngine.mermaid_capital_allocation(
                    profile.ticker, capex_pct, buyback_pct, div_pct
                )
                visuals.append(mermaid)

            # Pull assumptions from fundamental
            fund_assumptions = getattr(fundamental, "assumptions", [])
            assumptions.extend(fund_assumptions)
            fund_gaps = getattr(fundamental, "data_gaps", [])
            gaps.extend(fund_gaps)

        # Dividend & yield (v0.1.1)
        d_parts, d_visuals, d_assumptions, d_gaps = self._build_dividend_block(ctx)
        parts.extend(d_parts)
        visuals.extend(d_visuals)
        assumptions.extend(d_assumptions)
        gaps.extend(d_gaps)

        return ReportSection(
            step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps,
        ), len(visuals)

    def _render_comprehensive_step3(
        self, step: StepTemplate, ctx: dict[str, Any]
    ) -> tuple[ReportSection, int]:
        """Step 3: Competitive Position & Market Structure."""
        competitive = ctx.get("competitive")
        profile: CompanyProfile = ctx["profile"]

        parts: list[str] = []
        visuals: list[ReportVisual] = []
        assumptions: list[Assumption] = []
        gaps: list[str] = []

        if not competitive:
            parts.append("**Data Gap:** Competitive analysis not available.")
            gaps.append("Peer discovery returned no results.")
            return ReportSection(
                step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps,
            ), 0

        landscape = getattr(competitive, "landscape", None)
        peers = landscape.peers if landscape else []

        # Peer table
        if peers:
            peer_table = VisualEngine.table_peer_comparison(profile.ticker, peers)
            visuals.append(peer_table)

        # Positioning summary
        summary = getattr(competitive, "positioning_summary", "")
        if summary:
            parts.append(summary)
            parts.append("")

        # Advantages
        advantages = getattr(competitive, "competitive_advantages", [])
        if advantages:
            parts.append("### Competitive Advantages")
            for adv in advantages:
                parts.append(f"- {adv}")
            parts.append("")

        # Disadvantages
        disadvantages = getattr(competitive, "competitive_disadvantages", [])
        if disadvantages:
            parts.append("### Competitive Disadvantages")
            for dis in disadvantages:
                parts.append(f"- {dis}")
            parts.append("")

        # Moat indicators
        moat = getattr(competitive, "competitive_moat_indicators", [])
        if moat:
            parts.append("### Moat Indicators")
            for m in moat:
                parts.append(f"- {m}")
            parts.append("")

        comp_assumptions = getattr(competitive, "assumptions", [])
        assumptions.extend(comp_assumptions)
        comp_gaps = getattr(competitive, "data_gaps", [])
        gaps.extend(comp_gaps)

        return ReportSection(
            step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps,
        ), len(visuals)

    def _render_comprehensive_step4(
        self, step: StepTemplate, ctx: dict[str, Any]
    ) -> tuple[ReportSection, int]:
        """Step 4: Technical Analysis & Market Structure."""
        technical = ctx.get("technical")
        indicators = ctx.get("technical_indicators")
        prices: PriceSeries = ctx["prices"]

        parts: list[str] = []
        visuals: list[ReportVisual] = []
        assumptions: list[Assumption] = []
        gaps: list[str] = []

        if not technical or not indicators:
            parts.append("**Data Gap:** Technical analysis not available (insufficient price data).")
            gaps.append("Technical indicators could not be computed.")
            return ReportSection(
                step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps,
            ), 0

        regime = getattr(technical, "regime", "neutral")
        composite = getattr(technical, "composite_score", 50.0)

        parts.append(f"**Technical Regime:** {regime.upper()} (Composite Score: {composite:.0f}/100)")
        parts.append("")

        # ASCII dashboard
        ascii_dash = VisualEngine.ascii_technical_dashboard(indicators, composite, regime)
        visuals.append(ascii_dash)

        # Signals
        signals = getattr(technical, "signals", [])
        if signals:
            parts.append("### Signal Summary")
            for sig in signals:
                icon = "+" if sig.signal == "bullish" else ("-" if sig.signal == "bearish" else "~")
                parts.append(f"- [{icon}] **{sig.indicator}:** {sig.description}")
            parts.append("")

        # Key levels
        support = getattr(technical, "nearest_support", None)
        resistance = getattr(technical, "nearest_resistance", None)
        if support or resistance:
            parts.append("### Key Levels")
            if support:
                dist = getattr(technical, "support_distance_pct", 0)
                parts.append(f"- Nearest support: **{money(support, ctx['profile'].currency)}** ({dist:.1%} below)")
            if resistance:
                dist = getattr(technical, "resistance_distance_pct", 0)
                parts.append(f"- Nearest resistance: **{money(resistance, ctx['profile'].currency)}** ({dist:.1%} above)")
            parts.append("")

        # Patterns
        patterns = getattr(technical, "patterns", [])
        if patterns:
            parts.append("### Detected Patterns")
            for p in patterns:
                parts.append(f"- {p}")
            parts.append("")

        tech_assumptions = getattr(technical, "assumptions", [])
        assumptions.extend(tech_assumptions)
        tech_gaps = getattr(technical, "data_gaps", [])
        gaps.extend(tech_gaps)

        return ReportSection(
            step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps,
        ), len(visuals)

    def _render_comprehensive_step5(
        self, step: StepTemplate, ctx: dict[str, Any]
    ) -> tuple[ReportSection, int]:
        """Step 5: Macro Context & Sector Dynamics."""
        macro = ctx.get("macro")

        parts: list[str] = []
        visuals: list[ReportVisual] = []
        assumptions: list[Assumption] = []
        gaps: list[str] = []

        if not macro:
            parts.append("**Data Gap:** Macro analysis not available.")
            gaps.append("Macro data unavailable.")
            return ReportSection(
                step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps,
            ), 0

        favorability = getattr(macro, "macro_favorability", "neutral")
        score = getattr(macro, "macro_score", 50.0)

        parts.append(f"**Macro Favorability:** {favorability.upper()} (Score: {score:.0f}/100)")
        parts.append("")

        # Regime summary
        parts.append("### Regime Classification")
        for regime_attr in ["rate_regime", "inflation_regime", "growth_regime", "credit_regime", "volatility_regime"]:
            val = getattr(macro, regime_attr, "unknown")
            label = regime_attr.replace("_regime", "").replace("_", " ").title()
            parts.append(f"- {label}: **{val}**")
        parts.append("")

        # Implications table
        implications = getattr(macro, "implications", [])
        if implications:
            macro_table = VisualEngine.table_macro_regime(implications)
            visuals.append(macro_table)

        # Second-order effects
        for impl in implications:
            effects = getattr(impl, "second_order_effects", [])
            if effects:
                factor = getattr(impl, "factor", "")
                parts.append(f"### Second-Order Effects: {factor}")
                for effect in effects:
                    parts.append(f"- {effect}")
                parts.append("")

        # Cycle
        cycle = getattr(macro, "cycle_description", "")
        if cycle:
            parts.append(f"### Cycle Positioning\n\n{cycle}")
            parts.append("")

        macro_assumptions = getattr(macro, "assumptions", [])
        assumptions.extend(macro_assumptions)
        macro_gaps = getattr(macro, "data_gaps", [])
        gaps.extend(macro_gaps)

        return ReportSection(
            step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps,
        ), len(visuals)

    def _render_comprehensive_step6(
        self, step: StepTemplate, ctx: dict[str, Any]
    ) -> tuple[ReportSection, int]:
        """Step 6: Risk Assessment & Scenario-Based Valuation."""
        risk_matrix: RiskMatrix | None = ctx.get("risk_matrix")
        valuation: ValuationRange | None = ctx.get("valuation")

        parts: list[str] = []
        visuals: list[ReportVisual] = []
        assumptions: list[Assumption] = []
        gaps: list[str] = []

        # ---- Risk Matrix ----
        parts.append("### Risk Assessment")
        parts.append("")

        if risk_matrix and risk_matrix.risks:
            parts.append(f"**Overall Risk Score:** {risk_matrix.overall_risk_score}/10")
            parts.append(f"**Key Risks:** {risk_matrix.key_risk_summary}")
            parts.append("")

            # Risk table
            risk_table = VisualEngine.table_risk_matrix(risk_matrix.risks)
            visuals.append(risk_table)

            # Plotly risk heatmap
            risk_heatmap = VisualEngine.plotly_risk_heatmap(risk_matrix)
            if risk_heatmap:
                visuals.append(risk_heatmap)

            # Detail top 3 risks
            parts.append("### Top Risks (Detailed)")
            for r in risk_matrix.risks[:3]:
                parts.append(f"\n**{r.title}** ({r.category.value.title()})")
                parts.append(f"- Probability: {r.probability} | Impact: {r.impact} | "
                             f"Timing: {r.timing.value.replace('_', ' ').title()} | "
                             f"Nature: {r.nature.value.title()}")
                parts.append(f"- {r.description}")
                if r.mitigants:
                    parts.append(f"- Mitigants: {'; '.join(r.mitigants[:2])}")
                if r.second_order_effects:
                    parts.append(f"- Second-order: {'; '.join(r.second_order_effects[:2])}")
                if r.monitoring_triggers:
                    parts.append(f"- Monitor: {'; '.join(r.monitoring_triggers[:2])}")
            parts.append("")
        else:
            gaps.append("Risk matrix not available.")

        # ---- Valuation ----
        parts.append("### Scenario-Based Valuation Range")
        parts.append("")

        if valuation and valuation.scenarios:
            parts.append(f"**Current Price:** {money(valuation.current_price, ctx['profile'].currency)}")
            parts.append(f"**Primary Methodology:** {valuation.primary_methodology}")
            parts.append("")

            # Mandatory ASCII chart
            ascii_chart = VisualEngine.ascii_scenario_chart(valuation)
            visuals.append(ascii_chart)

            # Plotly scenario chart
            plotly_scenario = VisualEngine.plotly_scenario_valuation(valuation)
            if plotly_scenario:
                visuals.append(plotly_scenario)

            # Scenario details
            for s in valuation.scenarios:
                parts.append(f"\n**{s.label}:** {money(s.implied_price_low, ctx['profile'].currency, 0)} - {money(s.implied_price_high, ctx['profile'].currency, 0)}")
                if s.implied_upside_low is not None and s.implied_upside_high is not None:
                    parts.append(f"  Implied move: {s.implied_upside_low:.1%} to {s.implied_upside_high:.1%}")
                parts.append(f"  {s.narrative}")

                # Scenario assumptions
                for a in s.assumptions:
                    assumptions.append(a)

            # Variant perception
            vp = valuation.variant_perception
            if vp:
                parts.append("\n### Variant Perception")
                parts.append(f"- **Consensus:** {vp.consensus_view}")
                parts.append(f"- **Variant View:** {vp.variant_view}")
                parts.append(f"- **Why It Matters:** {vp.why_it_matters}")
        else:
            gaps.append("Valuation range not available.")

        return ReportSection(
            step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps,
        ), len(visuals)

    def _render_comprehensive_step7(
        self, step: StepTemplate, ctx: dict[str, Any]
    ) -> tuple[ReportSection, int]:
        """Step 7: Investment Thesis & Decision Framework."""
        profile: CompanyProfile = ctx["profile"]
        fundamental = ctx.get("fundamental")
        technical = ctx.get("technical")
        macro = ctx.get("macro")
        competitive = ctx.get("competitive")
        valuation: ValuationRange | None = ctx.get("valuation")
        risk_matrix: RiskMatrix | None = ctx.get("risk_matrix")

        parts: list[str] = []
        visuals: list[ReportVisual] = []
        assumptions: list[Assumption] = []
        gaps: list[str] = []

        favors: list[str] = []
        disfavors: list[str] = []
        catalysts: list[str] = []

        # ---- Collect favors / disfavors from all domains ----

        # Fundamental
        if fundamental:
            rev_growth = getattr(fundamental, "revenue_growth_yoy", None)
            bs_grade = getattr(fundamental, "balance_sheet_grade", "")
            eq_grade = getattr(fundamental, "earnings_quality_grade", "")
            om_trend = getattr(fundamental, "operating_margin_trend", "")

            if rev_growth and rev_growth > 0.05:
                favors.append(f"Revenue growing at {rev_growth:.1%} YoY.")
            elif rev_growth and rev_growth < -0.05:
                disfavors.append(f"Revenue declining at {rev_growth:.1%} YoY.")

            if bs_grade == "Strong":
                favors.append("Strong balance sheet provides financial flexibility.")
            elif bs_grade == "Weak":
                disfavors.append("Weak balance sheet limits strategic options.")

            if eq_grade == "High":
                favors.append("High earnings quality (strong cash conversion).")
            elif eq_grade == "Low":
                disfavors.append("Low earnings quality raises accrual concerns.")

            if om_trend == "expanding":
                favors.append("Operating margins expanding.")
            elif om_trend == "contracting":
                disfavors.append("Operating margins contracting.")

        # Technical
        if technical:
            regime = getattr(technical, "regime", "")
            if regime == "bullish":
                favors.append("Bullish technical regime supports near-term momentum.")
            elif regime == "bearish":
                disfavors.append("Bearish technical regime indicates negative momentum.")

        # Macro
        if macro:
            favorability = getattr(macro, "macro_favorability", "")
            if favorability == "favorable":
                favors.append("Favorable macro environment for the sector.")
            elif favorability == "unfavorable":
                disfavors.append("Unfavorable macro environment creates headwinds.")

        # Competitive
        if competitive:
            adv_count = len(getattr(competitive, "competitive_advantages", []))
            disadv_count = len(getattr(competitive, "competitive_disadvantages", []))
            if adv_count > disadv_count:
                favors.append(f"Favorable competitive position ({adv_count} advantages vs {disadv_count} disadvantages).")
            elif disadv_count > adv_count:
                disfavors.append(f"Weak competitive position ({disadv_count} disadvantages vs {adv_count} advantages).")

        # Valuation
        if valuation and valuation.scenarios:
            from ..enums import ScenarioType
            base = next((s for s in valuation.scenarios if s.scenario_type == ScenarioType.BASE), None)
            if base and base.implied_upside_low is not None and base.implied_upside_high is not None:
                avg_upside = (base.implied_upside_low + base.implied_upside_high) / 2
                if avg_upside > 0.10:
                    favors.append(f"Base case implies {avg_upside:.1%} upside from current price.")
                elif avg_upside < -0.10:
                    disfavors.append(f"Base case implies {abs(avg_upside):.1%} downside from current price.")

        # Catalysts
        catalysts.append("Upcoming earnings report and guidance update.")
        catalysts.append("Macro regime shift (rate cuts, fiscal stimulus).")
        catalysts.append("Competitive dynamics (M&A, new product launch, market share shift).")

        # ---- Thesis narrative ----
        parts.append("### Factors That Favor the Thesis")
        if favors:
            for f in favors:
                parts.append(f"- {f}")
        else:
            parts.append("- No strong favorable factors identified.")
        parts.append("")

        parts.append("### Factors That Disfavor the Thesis")
        if disfavors:
            for d in disfavors:
                parts.append(f"- {d}")
        else:
            parts.append("- No strong unfavorable factors identified.")
        parts.append("")

        parts.append("### Key Catalysts")
        for c in catalysts:
            parts.append(f"- {c}")
        parts.append("")

        # Risk-adjusted view
        if risk_matrix:
            parts.append(f"### Risk-Adjusted View")
            parts.append(f"Overall risk score: **{risk_matrix.overall_risk_score}/10**")
            parts.append(f"{risk_matrix.key_risk_summary}")
            parts.append("")

        # Monitoring triggers
        parts.append("### What to Monitor")
        parts.append("- Earnings trajectory and guidance revisions.")
        parts.append("- Margin trend (expanding or compressing).")
        parts.append("- Competitive dynamics and market share data.")
        parts.append("- Macro regime changes (rates, inflation, growth).")
        parts.append("- Technical support/resistance breaks.")
        parts.append("")

        # Mermaid decision framework
        mermaid = VisualEngine.mermaid_decision_framework(
            profile.ticker, favors[:4], disfavors[:4], catalysts[:3]
        )
        visuals.append(mermaid)

        # Mermaid business model (if Step 1 didn't include one for this template)
        biz_model = VisualEngine.mermaid_business_model(profile)
        visuals.append(biz_model)

        return ReportSection(
            step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps,
        ), len(visuals)


    # ==================================================================
    # TACTICAL report step renderers
    # ==================================================================

    def _render_tactical_step1(self, step, ctx):
        """Step 1: Current Setup & Near-Term Context."""
        profile = ctx["profile"]
        prices = ctx["prices"]
        technical = ctx.get("technical")
        parts = []
        visuals = []
        assumptions = []
        gaps = []

        if profile.description:
            parts.append(profile.description[:300])
            parts.append("")

        parts.append(f"**Current Price:** {money(prices.current_price, profile.currency)}")
        if prices.price_52w_high > 0:
            pct_from_high = (prices.current_price - prices.price_52w_high) / prices.price_52w_high
            parts.append(f"**52-Week Range:** {money(prices.price_52w_low, profile.currency)} - {money(prices.price_52w_high, profile.currency)} (currently {pct_from_high:.1%} from high)")
        if prices.ytd_return:
            parts.append(f"**YTD Return:** {prices.ytd_return:.1%}")
        if prices.total_return_1y:
            parts.append(f"**1Y Total Return:** {prices.total_return_1y:.1%}")
        parts.append("")

        if technical:
            regime = getattr(technical, "regime", "")
            score = getattr(technical, "composite_score", 50)
            parts.append(f"**Technical Regime:** {regime.upper()} (Score: {score:.0f}/100)")

        table = VisualEngine.table_key_metrics(profile, ctx["financials"], prices.current_price,
            prices.current_price / ctx["financials"][0].eps_diluted if ctx["financials"] and ctx["financials"][0].eps_diluted and ctx["financials"][0].eps_diluted > 0 else None)
        visuals.append(table)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), len(visuals)

    def _render_tactical_step2(self, step, ctx):
        """Step 2: Technical Analysis & Price Structure."""
        technical = ctx.get("technical")
        indicators = ctx.get("technical_indicators")
        prices = ctx["prices"]
        parts = []
        visuals = []
        assumptions = []
        gaps = []

        if not technical or not indicators:
            parts.append("**Data Gap:** Technical analysis not available.")
            gaps.append("Technical indicators could not be computed.")
            return ReportSection(step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), 0

        regime = getattr(technical, "regime", "neutral")
        composite = getattr(technical, "composite_score", 50.0)
        parts.append(f"**Technical Regime:** {regime.upper()} (Composite Score: {composite:.0f}/100)")
        parts.append("")

        ascii_dash = VisualEngine.ascii_technical_dashboard(indicators, composite, regime)
        visuals.append(ascii_dash)

        signals = getattr(technical, "signals", [])
        if signals:
            parts.append("### Signal Summary")
            for sig in signals:
                icon = "+" if sig.signal == "bullish" else ("-" if sig.signal == "bearish" else "~")
                parts.append(f"- [{icon}] **{sig.indicator}:** {sig.description}")
            parts.append("")

        support = getattr(technical, "nearest_support", None)
        resistance = getattr(technical, "nearest_resistance", None)
        if support or resistance:
            parts.append("### Key Levels")
            if support:
                dist = getattr(technical, "support_distance_pct", 0)
                parts.append(f"- Nearest support: **{money(support, ctx['profile'].currency)}** ({dist:.1%} below)")
            if resistance:
                dist = getattr(technical, "resistance_distance_pct", 0)
                parts.append(f"- Nearest resistance: **{money(resistance, ctx['profile'].currency)}** ({dist:.1%} above)")
            parts.append("")

        patterns = getattr(technical, "patterns", [])
        if patterns:
            parts.append("### Detected Patterns")
            for p in patterns:
                parts.append(f"- {p}")

        tech_assumptions = getattr(technical, "assumptions", [])
        assumptions.extend(tech_assumptions)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), len(visuals)

    def _render_tactical_step3(self, step, ctx):
        """Step 3: Macro & Sector Context."""
        macro = ctx.get("macro")
        parts = []
        visuals = []
        assumptions = []
        gaps = []

        if not macro:
            parts.append("**Data Gap:** Macro analysis not available.")
            gaps.append("Macro data unavailable.")
            return ReportSection(step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), 0

        favorability = getattr(macro, "macro_favorability", "neutral")
        score = getattr(macro, "macro_score", 50.0)
        parts.append(f"**Macro Favorability:** {favorability.upper()} (Score: {score:.0f}/100)")
        parts.append("")

        for attr in ["rate_regime", "inflation_regime", "growth_regime", "volatility_regime"]:
            val = getattr(macro, attr, "unknown")
            label = attr.replace("_regime", "").replace("_", " ").title()
            parts.append(f"- {label}: **{val}**")
        parts.append("")

        implications = getattr(macro, "implications", [])
        if implications:
            macro_table = VisualEngine.table_macro_regime(implications)
            visuals.append(macro_table)

            for impl in implications:
                effects = getattr(impl, "second_order_effects", [])
                if effects:
                    factor = getattr(impl, "factor", "")
                    parts.append(f"### Near-Term Impact: {factor}")
                    for e in effects[:2]:
                        parts.append(f"- {e}")
                    parts.append("")

        cycle = getattr(macro, "cycle_description", "")
        if cycle:
            parts.append(f"### Cycle Context\n{cycle}")

        macro_assumptions = getattr(macro, "assumptions", [])
        assumptions.extend(macro_assumptions)
        macro_gaps = getattr(macro, "data_gaps", [])
        gaps.extend(macro_gaps)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), len(visuals)

    def _render_tactical_step4(self, step, ctx):
        """Step 4: Near-Term Fundamental Catalysts."""
        fundamental = ctx.get("fundamental")
        financials = ctx["financials"]
        profile = ctx["profile"]
        parts = []
        visuals = []
        assumptions = []
        gaps = []

        if not financials:
            gaps.append("Financial data unavailable.")
            parts.append("**Data Gap:** No financial data available.")
            return ReportSection(step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), 0

        if fundamental:
            parts.append("### Earnings Trajectory")
            rev_growth = getattr(fundamental, "revenue_growth_yoy", None)
            eps_growth = getattr(fundamental, "eps_growth_yoy", None)
            eq = getattr(fundamental, "earnings_quality_grade", "")
            if rev_growth is not None:
                parts.append(f"- Revenue growth (YoY): **{rev_growth:.1%}**")
            if eps_growth is not None:
                parts.append(f"- EPS growth (YoY): **{eps_growth:.1%}**")
            if eq:
                parts.append(f"- Earnings quality: **{eq}**")
            parts.append("")

            om_trend = getattr(fundamental, "operating_margin_trend", "")
            gm_trend = getattr(fundamental, "gross_margin_trend", "")
            if om_trend or gm_trend:
                parts.append("### Margin Trajectory")
                if gm_trend:
                    parts.append(f"- Gross margin trend: **{gm_trend}**")
                if om_trend:
                    parts.append(f"- Operating margin trend: **{om_trend}**")
                parts.append("")

        # Financial summary table as visual
        fin_table = VisualEngine.table_financial_summary(financials)
        visuals.append(fin_table)

        fund_assumptions = getattr(fundamental, "assumptions", []) if fundamental else []
        assumptions.extend(fund_assumptions)

        # Dividend & yield — compact, income/event focused (v0.1.1)
        d_parts, d_visuals, d_assumptions, d_gaps = self._build_dividend_block(ctx, compact=True)
        parts.extend(d_parts)
        visuals.extend(d_visuals)
        assumptions.extend(d_assumptions)
        gaps.extend(d_gaps)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), len(visuals)

    def _render_tactical_step5(self, step, ctx):
        """Step 5: Near-Term Risk Map."""
        risk_matrix = ctx.get("risk_matrix")
        parts = []
        visuals = []
        gaps = []

        if not risk_matrix or not risk_matrix.risks:
            gaps.append("Risk matrix not available.")
            parts.append("**Data Gap:** Risk assessment not available.")
            return ReportSection(step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, data_gaps=gaps), 0

        parts.append(f"**Overall Risk Score:** {risk_matrix.overall_risk_score}/10")
        parts.append(f"**Key Risks:** {risk_matrix.key_risk_summary}")
        parts.append("")

        # Filter near-term risks
        from ..enums import RiskDuration
        near_term = [r for r in risk_matrix.risks if r.timing == RiskDuration.NEAR_TERM]
        other = [r for r in risk_matrix.risks if r.timing != RiskDuration.NEAR_TERM]

        if near_term:
            parts.append("### Near-Term Risks (< 6 months)")
            for r in near_term[:5]:
                parts.append(f"\n**{r.title}** ({r.probability} probability, {r.impact} impact)")
                parts.append(f"- {r.description}")
                if r.monitoring_triggers:
                    parts.append(f"- Watch for: {'; '.join(r.monitoring_triggers[:2])}")
            parts.append("")

        if other:
            parts.append("### Medium/Long-Term Risks")
            for r in other[:3]:
                parts.append(f"- **{r.title}:** {r.probability} probability, {r.impact} impact. {r.nature.value.title()}.")

        risk_table = VisualEngine.table_risk_matrix(risk_matrix.risks)
        visuals.append(risk_table)

        risk_heatmap = VisualEngine.plotly_risk_heatmap(risk_matrix)
        if risk_heatmap:
            visuals.append(risk_heatmap)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, data_gaps=gaps), len(visuals)

    def _render_tactical_step6(self, step, ctx):
        """Step 6: Scenario-Based Valuation Range."""
        valuation = ctx.get("valuation")
        parts = []
        visuals = []
        assumptions = []
        gaps = []

        if not valuation or not valuation.scenarios:
            gaps.append("Valuation not available.")
            parts.append("**Data Gap:** Valuation range not available.")
            return ReportSection(step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), 0

        parts.append(f"**Current Price:** {money(valuation.current_price, ctx['profile'].currency)}")
        parts.append(f"**Methodology:** {valuation.primary_methodology}")
        parts.append("")

        ascii_chart = VisualEngine.ascii_scenario_chart(valuation)
        visuals.append(ascii_chart)

        plotly_chart = VisualEngine.plotly_scenario_valuation(valuation)
        if plotly_chart:
            visuals.append(plotly_chart)

        for s in valuation.scenarios:
            parts.append(f"\n**{s.label}:** {money(s.implied_price_low, ctx['profile'].currency, 0)} - {money(s.implied_price_high, ctx['profile'].currency, 0)}")
            if s.implied_upside_low is not None and s.implied_upside_high is not None:
                parts.append(f"  Implied move: {s.implied_upside_low:.1%} to {s.implied_upside_high:.1%}")
            parts.append(f"  {s.narrative}")
            for a in s.assumptions:
                assumptions.append(a)

        vp = valuation.variant_perception
        if vp:
            parts.append("\n### Variant Perception")
            parts.append(f"- **Consensus:** {vp.consensus_view}")
            parts.append(f"- **Variant View:** {vp.variant_view}")
            parts.append(f"- **Why It Matters:** {vp.why_it_matters}")

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), len(visuals)

    def _render_tactical_step7(self, step, ctx):
        """Step 7: Tactical Assessment & Positioning Context."""
        profile = ctx["profile"]
        technical = ctx.get("technical")
        macro = ctx.get("macro")
        fundamental = ctx.get("fundamental")
        valuation = ctx.get("valuation")
        risk_matrix = ctx.get("risk_matrix")
        parts = []
        visuals = []
        gaps = []

        favors = []
        disfavors = []

        # Technical signals
        if technical:
            regime = getattr(technical, "regime", "")
            if regime == "bullish":
                favors.append("Bullish technical regime with positive momentum.")
            elif regime == "bearish":
                disfavors.append("Bearish technical regime with negative momentum.")

            signals = getattr(technical, "signals", [])
            for sig in signals:
                if sig.signal == "bullish" and sig.strength == "strong":
                    favors.append(f"{sig.indicator}: {sig.description}")
                elif sig.signal == "bearish" and sig.strength == "strong":
                    disfavors.append(f"{sig.indicator}: {sig.description}")

        # Macro
        if macro:
            fav = getattr(macro, "macro_favorability", "")
            if fav == "favorable":
                favors.append("Favorable macro environment for the sector.")
            elif fav == "unfavorable":
                disfavors.append("Unfavorable macro environment creates headwinds.")

        # Fundamental momentum
        if fundamental:
            rev_growth = getattr(fundamental, "revenue_growth_yoy", None)
            om_trend = getattr(fundamental, "operating_margin_trend", "")
            if rev_growth and rev_growth > 0.05:
                favors.append(f"Revenue growing at {rev_growth:.1%} YoY.")
            elif rev_growth and rev_growth < -0.05:
                disfavors.append(f"Revenue declining at {rev_growth:.1%} YoY.")
            if om_trend == "expanding":
                favors.append("Operating margins expanding.")
            elif om_trend == "contracting":
                disfavors.append("Operating margins contracting.")

        # Valuation
        if valuation and valuation.scenarios:
            from ..enums import ScenarioType
            base = next((s for s in valuation.scenarios if s.scenario_type == ScenarioType.BASE), None)
            if base and base.implied_upside_low is not None and base.implied_upside_high is not None:
                avg = (base.implied_upside_low + base.implied_upside_high) / 2
                if avg > 0.10:
                    favors.append(f"Base case implies {avg:.1%} upside.")
                elif avg < -0.10:
                    disfavors.append(f"Base case implies {abs(avg):.1%} downside.")

        parts.append("### Factors That Favor Near-Term Positioning")
        for f in (favors or ["No strong favorable signals identified."]):
            parts.append(f"- {f}")
        parts.append("")

        parts.append("### Factors That Disfavor Near-Term Positioning")
        for d in (disfavors or ["No strong unfavorable signals identified."]):
            parts.append(f"- {d}")
        parts.append("")

        # Risk context
        if risk_matrix:
            parts.append(f"### Risk Context")
            parts.append(f"Overall risk score: **{risk_matrix.overall_risk_score}/10**")
            parts.append(f"{risk_matrix.key_risk_summary}")
            parts.append("")

        parts.append("### Monitoring Triggers")
        parts.append("- Earnings report and guidance revision")
        parts.append("- Technical support/resistance breaks")
        parts.append("- Macro regime shift (rate decision, inflation print)")
        parts.append("- Volume confirmation of price moves")

        mermaid = VisualEngine.mermaid_decision_framework(
            profile.ticker, favors[:4], disfavors[:4],
            ["Earnings report", "Technical breakout/breakdown", "Macro shift"]
        )
        visuals.append(mermaid)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, data_gaps=gaps), len(visuals)

    # ==================================================================
    # LONG-TERM report step renderers
    # ==================================================================

    def _render_long_term_step1(self, step, ctx):
        """Step 1: Business Overview & Structural Position."""
        profile = ctx["profile"]
        parts = []
        visuals = []

        if profile.description:
            parts.append(profile.description[:500])
            parts.append("")

        parts.append(f"**Sector:** {profile.sector}")
        parts.append(f"**Industry:** {profile.industry}")
        if profile.market_cap:
            parts.append(f"**Market Cap:** {money(float(profile.market_cap) / 1e9, profile.currency, 1)}B")
        if profile.employees:
            parts.append(f"**Employees:** {profile.employees:,}")
        parts.append("")

        biz_model = VisualEngine.mermaid_business_model(profile)
        visuals.append(biz_model)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals), len(visuals)

    def _render_long_term_step2(self, step, ctx):
        """Step 2: Financial Analysis & Quality of Earnings."""
        financials = ctx["financials"]
        fundamental = ctx.get("fundamental")
        profile = ctx["profile"]
        parts = []
        visuals = []
        assumptions = []
        gaps = []

        if not financials:
            gaps.append("No financial statements available.")
            parts.append("**Data Gap:** No financial data available.")
            return ReportSection(step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), 0

        fin_table = VisualEngine.table_financial_summary(financials)
        visuals.append(fin_table)

        plotly_chart = VisualEngine.plotly_financial_trends(financials, profile.ticker)
        if plotly_chart:
            visuals.append(plotly_chart)

        if fundamental:
            parts.append("### Growth")
            for attr, label in [("revenue_growth_yoy", "Revenue Growth (YoY)"), ("revenue_cagr_3y", "Revenue CAGR (3Y)"), ("revenue_cagr_5y", "Revenue CAGR (5Y)")]:
                val = getattr(fundamental, attr, None)
                if val is not None:
                    parts.append(f"- {label}: **{val:.1%}**")
            parts.append("")

            parts.append("### Profitability")
            for attr, label in [("gross_margin_latest", "Gross Margin"), ("operating_margin_latest", "Operating Margin"), ("net_margin_latest", "Net Margin"), ("fcf_margin_latest", "FCF Margin")]:
                val = getattr(fundamental, attr, None)
                if val is not None:
                    trend = getattr(fundamental, attr.replace("_latest", "_trend"), "")
                    t = f" ({trend})" if trend else ""
                    parts.append(f"- {label}: **{val:.1%}**{t}")
            parts.append("")

            parts.append("### Earnings Quality & Balance Sheet")
            bs = getattr(fundamental, "balance_sheet_grade", "")
            eq = getattr(fundamental, "earnings_quality_grade", "")
            nd = getattr(fundamental, "net_debt_to_ebitda", None)
            fcf_ni = getattr(fundamental, "fcf_to_net_income", None)
            if bs:
                parts.append(f"- Balance sheet: **{bs}**")
            if eq:
                parts.append(f"- Earnings quality: **{eq}**")
            if nd is not None:
                parts.append(f"- Net Debt / EBITDA: **{nd:.1f}x**")
            if fcf_ni is not None:
                parts.append(f"- FCF / Net Income: **{fcf_ni:.2f}x**")

            fund_assumptions = getattr(fundamental, "assumptions", [])
            assumptions.extend(fund_assumptions)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), len(visuals)

    def _render_long_term_step3(self, step, ctx):
        """Step 3: Competitive Landscape & Moat Assessment."""
        competitive = ctx.get("competitive")
        profile = ctx["profile"]
        parts = []
        visuals = []
        assumptions = []
        gaps = []

        if not competitive:
            gaps.append("Competitive analysis not available.")
            parts.append("**Data Gap:** No peer data available.")
            return ReportSection(step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), 0

        landscape = getattr(competitive, "landscape", None)
        peers = landscape.peers if landscape else []

        if peers:
            peer_table = VisualEngine.table_peer_comparison(profile.ticker, peers)
            visuals.append(peer_table)

        summary = getattr(competitive, "positioning_summary", "")
        if summary:
            parts.append(summary)
            parts.append("")

        advantages = getattr(competitive, "competitive_advantages", [])
        if advantages:
            parts.append("### Competitive Advantages")
            for a in advantages:
                parts.append(f"- {a}")
            parts.append("")

        disadvantages = getattr(competitive, "competitive_disadvantages", [])
        if disadvantages:
            parts.append("### Competitive Disadvantages")
            for d in disadvantages:
                parts.append(f"- {d}")
            parts.append("")

        moat = getattr(competitive, "competitive_moat_indicators", [])
        if moat:
            parts.append("### Moat Indicators")
            for m in moat:
                parts.append(f"- {m}")

        comp_assumptions = getattr(competitive, "assumptions", [])
        assumptions.extend(comp_assumptions)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=assumptions, data_gaps=gaps), len(visuals)

    def _render_long_term_step4(self, step, ctx):
        """Step 4: Capital Allocation & Shareholder Returns."""
        fundamental = ctx.get("fundamental")
        profile = ctx["profile"]
        parts = []
        visuals = []
        gaps = []

        cap = getattr(fundamental, "capital_allocation", None) if fundamental else None

        if not cap:
            gaps.append("Capital allocation data insufficient.")
            parts.append("**Data Gap:** Capital allocation analysis requires more complete financial data.")
            return ReportSection(step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, data_gaps=gaps), 0

        roic = getattr(cap, "roic", None)
        wacc = getattr(cap, "wacc", None)
        spread = getattr(cap, "roic_minus_wacc", None)
        assessment = getattr(cap, "assessment", "")

        if roic is not None:
            parts.append(f"- ROIC: **{roic:.1%}**")
        if wacc is not None:
            parts.append(f"- WACC: **{wacc:.1%}**")
        if spread is not None:
            label = "above" if spread > 0 else "below"
            parts.append(f"- ROIC vs WACC: **{abs(spread):.1%} {label}** cost of capital")
        if assessment:
            parts.append(f"- {assessment}")
        parts.append("")

        capex_pct = getattr(cap, "capex_pct_of_fcf", None)
        buyback_pct = getattr(cap, "buyback_pct_of_fcf", None)
        div_pct = getattr(cap, "dividend_pct_of_fcf", None)

        mermaid = VisualEngine.mermaid_capital_allocation(profile.ticker, capex_pct, buyback_pct, div_pct)
        visuals.append(mermaid)

        # Dividend & yield (v0.1.1)
        d_parts, d_visuals, d_assumptions, d_gaps = self._build_dividend_block(ctx)
        parts.extend(d_parts)
        visuals.extend(d_visuals)
        gaps.extend(d_gaps)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, assumptions=d_assumptions, data_gaps=gaps), len(visuals)

    def _render_long_term_step5(self, step, ctx):
        """Step 5: Risk Assessment."""
        risk_matrix = ctx.get("risk_matrix")
        parts = []
        visuals = []
        gaps = []

        if not risk_matrix or not risk_matrix.risks:
            gaps.append("Risk matrix not available.")
            parts.append("**Data Gap:** Risk assessment not available.")
            return ReportSection(step_number=step.step_number, title=step.title,
                content="\n".join(parts), visuals=visuals, data_gaps=gaps), 0

        parts.append(f"**Overall Risk Score:** {risk_matrix.overall_risk_score}/10")
        parts.append(f"**Summary:** {risk_matrix.key_risk_summary}")
        parts.append("")

        risk_table = VisualEngine.table_risk_matrix(risk_matrix.risks)
        visuals.append(risk_table)

        risk_heatmap = VisualEngine.plotly_risk_heatmap(risk_matrix)
        if risk_heatmap:
            visuals.append(risk_heatmap)

        # Detail top risks with second-order effects
        for r in risk_matrix.risks[:4]:
            parts.append(f"\n**{r.title}** ({r.category.value.title()})")
            parts.append(f"- Probability: {r.probability} | Impact: {r.impact} | Timing: {r.timing.value.replace('_', ' ').title()} | Nature: {r.nature.value.title()}")
            parts.append(f"- {r.description}")
            if r.second_order_effects:
                parts.append(f"- Second-order: {'; '.join(r.second_order_effects[:2])}")
            if r.mitigants:
                parts.append(f"- Mitigants: {'; '.join(r.mitigants[:2])}")

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, data_gaps=gaps), len(visuals)

    def _render_long_term_step6(self, step, ctx):
        """Step 6: Scenario-Based Valuation Range."""
        # Identical logic to tactical step 6 - both need valuation
        return self._render_tactical_step6(step, ctx)

    def _render_long_term_step7(self, step, ctx):
        """Step 7: Long-Term Thesis & Decision Framework."""
        profile = ctx["profile"]
        fundamental = ctx.get("fundamental")
        competitive = ctx.get("competitive")
        macro = ctx.get("macro")
        valuation = ctx.get("valuation")
        risk_matrix = ctx.get("risk_matrix")
        parts = []
        visuals = []
        gaps = []

        favors = []
        disfavors = []
        catalysts = []

        if fundamental:
            rev_growth = getattr(fundamental, "revenue_growth_yoy", None)
            bs = getattr(fundamental, "balance_sheet_grade", "")
            eq = getattr(fundamental, "earnings_quality_grade", "")
            om_trend = getattr(fundamental, "operating_margin_trend", "")

            if rev_growth and rev_growth > 0.05:
                favors.append(f"Revenue growing at {rev_growth:.1%} YoY.")
            elif rev_growth and rev_growth < -0.05:
                disfavors.append(f"Revenue declining at {rev_growth:.1%} YoY.")
            if bs == "Strong":
                favors.append("Strong balance sheet provides durability.")
            elif bs == "Weak":
                disfavors.append("Weak balance sheet limits strategic flexibility.")
            if eq == "High":
                favors.append("High earnings quality (strong cash conversion).")
            elif eq == "Low":
                disfavors.append("Low earnings quality raises concerns.")
            if om_trend == "expanding":
                favors.append("Operating margins expanding over time.")
            elif om_trend == "contracting":
                disfavors.append("Operating margins contracting.")

        if competitive:
            moat = getattr(competitive, "competitive_moat_indicators", [])
            if moat:
                favors.append(f"Moat indicators: {'; '.join(moat[:2])}")
            disadv = getattr(competitive, "competitive_disadvantages", [])
            if len(disadv) >= 3:
                disfavors.append("Multiple competitive disadvantages vs peers.")

        if macro:
            fav = getattr(macro, "macro_favorability", "")
            if fav == "favorable":
                favors.append("Favorable macro environment.")
            elif fav == "unfavorable":
                disfavors.append("Unfavorable macro environment.")

        catalysts.append("New product cycles or market expansion.")
        catalysts.append("Margin expansion from operating leverage.")
        catalysts.append("Capital return acceleration (buybacks, dividends).")
        catalysts.append("Competitive dynamics shift (M&A, market share).")

        parts.append("### Factors That Favor the Long-Term Thesis")
        for f in (favors or ["No strong favorable factors identified."]):
            parts.append(f"- {f}")
        parts.append("")

        parts.append("### Factors That Disfavor the Long-Term Thesis")
        for d in (disfavors or ["No strong unfavorable factors identified."]):
            parts.append(f"- {d}")
        parts.append("")

        parts.append("### Catalysts")
        for c in catalysts:
            parts.append(f"- {c}")
        parts.append("")

        if risk_matrix:
            parts.append(f"### Risk-Adjusted View")
            parts.append(f"Overall risk score: **{risk_matrix.overall_risk_score}/10**")
            parts.append(f"{risk_matrix.key_risk_summary}")
            parts.append("")

        parts.append("### What to Monitor")
        parts.append("- Multi-year revenue growth trajectory")
        parts.append("- Margin sustainability and expansion")
        parts.append("- Capital allocation decisions (ROIC vs WACC)")
        parts.append("- Competitive moat durability")
        parts.append("- Regulatory environment changes")

        mermaid = VisualEngine.mermaid_decision_framework(
            profile.ticker, favors[:4], disfavors[:4], catalysts[:3]
        )
        visuals.append(mermaid)

        return ReportSection(step_number=step.step_number, title=step.title,
            content="\n".join(parts), visuals=visuals, data_gaps=gaps), len(visuals)


    # ------------------------------------------------------------------
    # Generic fallback renderer (used for long_term and tactical steps
    # that don't have specific renderers yet)
    # ------------------------------------------------------------------

    def _render_generic_step(
        self, step: StepTemplate, ctx: dict[str, Any]
    ) -> tuple[ReportSection, int]:
        """Generic step renderer — used when no type-specific renderer exists.

        Assembles content from available data based on the step's required_data list.
        """
        parts: list[str] = []
        visuals: list[ReportVisual] = []
        gaps: list[str] = []

        parts.append(f"*{step.description}*")
        parts.append("")

        # Key questions as analysis prompts
        parts.append("**Key Questions Addressed:**")
        for q in step.key_questions:
            parts.append(f"- {q}")
        parts.append("")

        # Pull whatever data is available
        for data_key in step.required_data:
            data = ctx.get(data_key)
            if data is None:
                gaps.append(f"Data not available: {data_key}")

        if gaps:
            parts.append("**Data Gaps:**")
            for g in gaps:
                parts.append(f"- {g}")

        return ReportSection(
            step_number=step.step_number,
            title=step.title,
            content="\n".join(parts),
            visuals=visuals,
            data_gaps=gaps,
        ), 0
