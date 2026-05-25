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
# Module: research_analyst/reports/renderer.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..enums import ReportType
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
    # Comprehensive report step renderers
    # ------------------------------------------------------------------

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

        # Price context
        parts.append(f"**Current Price:** ${prices.current_price:.2f}")
        if prices.price_52w_high > 0:
            parts.append(
                f"**52-Week Range:** ${prices.price_52w_low:.2f} - ${prices.price_52w_high:.2f}"
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
                parts.append(f"- Nearest support: **${support:.2f}** ({dist:.1%} below)")
            if resistance:
                dist = getattr(technical, "resistance_distance_pct", 0)
                parts.append(f"- Nearest resistance: **${resistance:.2f}** ({dist:.1%} above)")
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
            parts.append(f"**Current Price:** ${valuation.current_price:.2f}")
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
                parts.append(f"\n**{s.label}:** ${s.implied_price_low:.0f} - ${s.implied_price_high:.0f}")
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
