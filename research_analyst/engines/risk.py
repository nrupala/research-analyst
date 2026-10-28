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

"""Risk engine — structured risk assessment by Probability x Impact x Timing.

Responsibilities:
  - Identify risks from fundamental, technical, macro, and competitive data
  - Structure each risk by: probability, impact, timing, nature, category
  - Second-order effects for each risk
  - Mitigants and monitoring triggers
  - Overall risk score (composite)
  - Risk matrix generation (for visual rendering)

Design:
  - Input: All analysis outputs (fundamental, technical, macro, competitive)
  - Output: RiskMatrix with StructuredRisk entries
  - Rule-based risk identification — deterministic, auditable
  - Every risk traced to data; no generic/boilerplate risks
  - "Not listing" — structured by Prob x Impact x Timing as spec demands
"""
# Module: research_analyst/engines/risk.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

import logging
from typing import Any

from ..enums import RiskCategory, RiskDuration, RiskNature
from ..models import (
    CompanyProfile,
    RiskMatrix,
    RiskScoreComponent,
    StructuredRisk,
)

logger = logging.getLogger(__name__)


# Forward references for engine output types (avoid circular imports)
# These are imported at call time, not module level.


class RiskEngine:
    """Identifies and structures risks from analysis data.

    Usage:
        engine = RiskEngine()
        risk_matrix = engine.assess(profile, fundamental, technical, macro, competitive)
    """

    def assess(
        self,
        profile: CompanyProfile,
        fundamental: object | None = None,
        technical: object | None = None,
        macro: object | None = None,
        competitive: object | None = None,
    ) -> RiskMatrix:
        """Run comprehensive risk assessment.

        Scans each analysis domain for risk signals, structures them,
        and computes a composite risk score.

        Returns:
            RiskMatrix with all identified risks, sorted by severity.
        """
        risks: list[StructuredRisk] = []

        # ---- Fundamental Risks ----
        if fundamental is not None:
            risks.extend(self._fundamental_risks(profile, fundamental))

        # ---- Technical Risks ----
        if technical is not None:
            risks.extend(self._technical_risks(profile, technical))

        # ---- Macro Risks ----
        if macro is not None:
            risks.extend(self._macro_risks(profile, macro))

        # ---- Competitive Risks ----
        if competitive is not None:
            risks.extend(self._competitive_risks(profile, competitive))

        # ---- Always-present generic risks (sector-specific) ----
        risks.extend(self._regulatory_risks(profile))

        # Sort by severity: High prob + High impact first
        # Severity score: probability_score * impact_score (higher = more severe)
        prob_scores = {"Low (<20%)": 1, "Medium (20-50%)": 2, "High (>50%)": 3}
        impact_scores = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
        risks.sort(
            key=lambda r: prob_scores.get(r.probability, 0) * impact_scores.get(r.impact, 0),
            reverse=True,
        )

        # Composite risk score (1-10)
        # Issue #71: the score is never published without its derivation —
        # build the per-risk breakdown the reader can re-compute.
        breakdown: list[RiskScoreComponent] = []
        baseline_note = ""
        if risks:
            severities: list[int] = []
            for r in risks:
                ps = prob_scores.get(r.probability, 1)
                im = impact_scores.get(r.impact, 1)
                severities.append(ps * im)
            total_severity = sum(severities)
            max_severity = len(risks) * 12  # 3 * 4 max per risk
            for r, sev in zip(risks, severities):
                breakdown.append(
                    RiskScoreComponent(
                        title=r.title,
                        probability_score=prob_scores.get(r.probability, 1),
                        impact_score=impact_scores.get(r.impact, 1),
                        severity=sev,
                        weight_share=(sev / total_severity) if total_severity else 0.0,
                    )
                )
            score = min(10.0, (total_severity / max_severity) * 10) if max_severity > 0 else 5.0
        else:
            # Issue #71: no unsupported score — when no risks were flagged there
            # is nothing to derive a score from, so publish None ("unrated")
            # instead of an invented number.
            score = None
            baseline_note = (
                "No material risks were flagged by any domain scan, so no composite "
                "score could be computed. The risk rating is **unrated** — no score "
                "is published rather than inventing one. Treat this as 'no evidence "
                "of elevated risk', not as a precise measurement."
            )

        # Key risk summary
        top_risks = risks[:3]
        summary_parts = [f"({r.probability}, {r.impact}) {r.title}" for r in top_risks]
        summary = "; ".join(summary_parts) if summary_parts else "No significant risks identified."

        return RiskMatrix(
            ticker=profile.ticker,
            risks=risks,
            overall_risk_score=round(score, 1) if score is not None else None,
            key_risk_summary=f"Top risks: {summary}",
            score_breakdown=breakdown,
            score_baseline_note=baseline_note,
        )

    # ------------------------------------------------------------------
    # Fundamental risk identification
    # ------------------------------------------------------------------

    def _fundamental_risks(self, profile: CompanyProfile, fund: object) -> list[StructuredRisk]:
        """Identify risks from fundamental analysis."""
        risks: list[StructuredRisk] = []

        # Access attributes safely via getattr
        balance_grade = getattr(fund, "balance_sheet_grade", "")
        earnings_quality = getattr(fund, "earnings_quality_grade", "")
        debt_to_equity = getattr(fund, "debt_to_equity", None)
        rev_growth = getattr(fund, "revenue_growth_yoy", None)
        op_margin_trend = getattr(fund, "operating_margin_trend", "")

        # High leverage
        if debt_to_equity is not None and debt_to_equity > 1.5:
            risks.append(
                StructuredRisk(
                    title="Elevated Financial Leverage",
                    description=(
                        f"Debt/Equity at {debt_to_equity:.2f}x exceeds 1.5x threshold. "
                        "Increases sensitivity to rate changes and earnings volatility."
                    ),
                    category=RiskCategory.FINANCIAL,
                    probability="Medium (20-50%)" if debt_to_equity < 2.5 else "High (>50%)",
                    probability_pct=35.0 if debt_to_equity < 2.5 else 55.0,
                    impact="High" if debt_to_equity > 2.5 else "Medium",
                    impact_description="Covenant breach risk, rating downgrade, dividend cut.",
                    timing=RiskDuration.NEAR_TERM
                    if debt_to_equity > 3
                    else RiskDuration.MEDIUM_TERM,
                    nature=RiskNature.STRUCTURAL,
                    mitigants=[
                        "Strong free cash flow generation for de-leveraging.",
                        "Fixed-rate debt structure limits near-term rate exposure.",
                        "Diversified maturity profile avoids refinancing wall.",
                    ],
                    monitoring_triggers=[
                        "Net Debt/EBITDA exceeds 4.0x.",
                        "Interest coverage falls below 3.0x.",
                        "Credit rating placed on negative watch.",
                    ],
                    second_order_effects=[
                        "Higher cost of debt constrains future capex or M&A.",
                        "Equity dilution risk if forced to raise capital.",
                        "Reduced financial flexibility limits competitive responses.",
                    ],
                )
            )

        # Revenue decline
        if rev_growth is not None and rev_growth < -0.05:
            risks.append(
                StructuredRisk(
                    title="Revenue Decline",
                    description=(
                        f"Revenue declined {rev_growth:.1%} YoY. Sustained decline "
                        "erodes operating leverage and may trigger cost restructuring."
                    ),
                    category=RiskCategory.OPERATIONAL,
                    probability="Medium (20-50%)" if rev_growth > -0.15 else "High (>50%)",
                    probability_pct=40.0 if rev_growth > -0.15 else 60.0,
                    impact="High",
                    impact_description=(
                        "Margin compression, potential headcount reduction, strategic pivot "
                        "risk."
                    ),
                    timing=RiskDuration.NEAR_TERM,
                    nature=RiskNature.TRANSITORY if rev_growth > -0.10 else RiskNature.STRUCTURAL,
                    mitigants=[
                        "New product pipeline or market expansion.",
                        "Cost restructuring to protect margins.",
                        "Recurring revenue base provides floor.",
                    ],
                    monitoring_triggers=[
                        "Two consecutive quarters of revenue decline.",
                        "Customer churn rate exceeding 10%.",
                        "Management revises guidance downward.",
                    ],
                    second_order_effects=[
                        "Fixed cost deleverage accelerates margin decline.",
                        "Key talent attrition as growth narrative weakens.",
                        "Competitive share loss becomes self-reinforcing.",
                    ],
                )
            )

        # Margin compression
        if op_margin_trend == "contracting":
            risks.append(
                StructuredRisk(
                    title="Operating Margin Contraction",
                    description=(
                        "Operating margins contracting over recent periods. "
                        "May indicate pricing pressure, input cost inflation, or mix shift."
                    ),
                    category=RiskCategory.OPERATIONAL,
                    probability="Medium (20-50%)",
                    probability_pct=40.0,
                    impact="Medium",
                    impact_description="Earnings compression, potential multiple de-rating.",
                    timing=RiskDuration.MEDIUM_TERM,
                    nature=RiskNature.STRUCTURAL
                    if op_margin_trend == "contracting"
                    else RiskNature.TRANSITORY,
                    mitigants=[
                        "Pricing actions or mix improvement initiatives.",
                        "Operational efficiency programs.",
                        "Scale benefits from revenue growth.",
                    ],
                    monitoring_triggers=[
                        "Gross margin declines for 3+ consecutive quarters.",
                        "SG&A as % of revenue rising above peer median.",
                    ],
                    second_order_effects=[
                        "Lower margins reduce reinvestment capacity.",
                        "Valuation multiple compression if market perceives structural shift.",
                    ],
                )
            )

        # Weak balance sheet
        if balance_grade == "Weak":
            risks.append(
                StructuredRisk(
                    title="Weak Balance Sheet",
                    description=(
                        f"Balance sheet graded '{balance_grade}'. "
                        "Multiple metrics (leverage, liquidity, coverage) below healthy thresholds."
                    ),
                    category=RiskCategory.FINANCIAL,
                    probability="Medium (20-50%)",
                    probability_pct=35.0,
                    impact="High",
                    impact_description="Limited financial flexibility, potential capital raise.",
                    timing=RiskDuration.MEDIUM_TERM,
                    nature=RiskNature.STRUCTURAL,
                    mitigants=["Asset sales or divestitures possible.", "Covenant renegotiation."],
                    monitoring_triggers=[
                        "Current ratio falls below 1.0x.",
                        "Negative free cash flow for 2+ quarters.",
                    ],
                    second_order_effects=[
                        "Supplier terms may tighten.",
                        "Talent retention suffers as equity comp devalues.",
                    ],
                )
            )

        # Low earnings quality
        if earnings_quality == "Low":
            risks.append(
                StructuredRisk(
                    title="Low Earnings Quality",
                    description=(
                        f"Earnings quality graded '{earnings_quality}'. "
                        "Large gap between reported earnings and cash flow suggests "
                        "high accruals or accounting aggressiveness."
                    ),
                    category=RiskCategory.FINANCIAL,
                    probability="Medium (20-50%)",
                    probability_pct=30.0,
                    impact="High",
                    impact_description="Earnings restatement risk, surprise write-downs.",
                    timing=RiskDuration.NEAR_TERM,
                    nature=RiskNature.STRUCTURAL,
                    mitigants=[
                        "Auditor review and internal controls.",
                        "Management commentary on accrual items.",
                    ],
                    monitoring_triggers=[
                        "FCF/Net Income ratio falls below 0.3x.",
                        "Auditor change or qualified opinion.",
                        "Receivables growing faster than revenue.",
                    ],
                    second_order_effects=[
                        "Institutional holders may reduce positions on quality concerns.",
                        "Short interest may increase.",
                    ],
                )
            )

        return risks

    # ------------------------------------------------------------------
    # Technical risk identification
    # ------------------------------------------------------------------

    def _technical_risks(self, profile: CompanyProfile, tech: object) -> list[StructuredRisk]:
        """Identify risks from technical analysis."""
        risks: list[StructuredRisk] = []

        regime = getattr(tech, "regime", "")
        volatility_score = getattr(tech, "volatility_score", 50.0)
        patterns = getattr(tech, "patterns", [])

        # Bearish technical regime
        if regime == "bearish":
            risks.append(
                StructuredRisk(
                    title="Bearish Technical Regime",
                    description=(
                        "Composite technical score indicates bearish regime. "
                        "Price below key moving averages with negative momentum."
                    ),
                    category=RiskCategory.OPERATIONAL,
                    probability="Medium (20-50%)",
                    impact="Medium",
                    impact_description=(
                        "Continued price weakness may trigger stop-losses and forced "
                        "selling."
                    ),
                    timing=RiskDuration.NEAR_TERM,
                    nature=RiskNature.TRANSITORY,
                    mitigants=[
                        "Oversold conditions may precede mean reversion.",
                        "Fundamental support at key valuation levels.",
                    ],
                    monitoring_triggers=[
                        "Death cross (50-day SMA crosses below 200-day).",
                        "RSI sustained below 30 for 5+ sessions.",
                        "Volume expansion on down days.",
                    ],
                    second_order_effects=[
                        "Algorithmic selling amplifies technical breakdowns.",
                        "Options market makers delta-hedging accelerates moves.",
                    ],
                )
            )

        # High volatility
        if volatility_score > 75:
            risks.append(
                StructuredRisk(
                    title="Elevated Price Volatility",
                    description=(
                        f"Volatility score at {volatility_score:.0f}/100 — above-average "
                        "price swings increase position sizing risk."
                    ),
                    category=RiskCategory.OPERATIONAL,
                    probability="High (>50%)",
                    impact="Medium",
                    impact_description=(
                        "Wider bid-ask spreads, stop-loss triggers, emotional decision "
                        "risk."
                    ),
                    timing=RiskDuration.NEAR_TERM,
                    nature=RiskNature.TRANSITORY,
                    mitigants=["Reduced position sizing.", "Wider stop-loss bands."],
                    monitoring_triggers=["ATR exceeds 5% of price.", "VIX spike above 30."],
                    second_order_effects=["Options premiums inflate, increasing hedging costs."],
                )
            )

        # Bearish patterns
        bearish_patterns = [p for p in patterns if "bearish" in p.lower()]
        if bearish_patterns:
            risks.append(
                StructuredRisk(
                    title="Bearish Chart Pattern Detected",
                    description=f"Pattern(s): {', '.join(bearish_patterns)}.",
                    category=RiskCategory.OPERATIONAL,
                    probability="Low (<20%)",
                    probability_pct=15.0,
                    impact="Medium",
                    impact_description="Pattern completion would confirm trend reversal.",
                    timing=RiskDuration.NEAR_TERM,
                    nature=RiskNature.TRANSITORY,
                    mitigants=[
                        "Pattern may fail (not all patterns complete).",
                        "Volume must confirm.",
                    ],
                    monitoring_triggers=["Neckline break on above-average volume."],
                    second_order_effects=[
                        "Technical traders pile in, creating self-fulfilling momentum."
                    ],
                )
            )

        return risks

    # ------------------------------------------------------------------
    # Macro risk identification
    # ------------------------------------------------------------------

    def _macro_risks(self, profile: CompanyProfile, macro: object) -> list[StructuredRisk]:
        """Identify risks from macro analysis."""
        risks: list[StructuredRisk] = []

        favorability = getattr(macro, "macro_favorability", "")
        implications = getattr(macro, "implications", [])

        # Unfavorable macro environment
        if favorability == "unfavorable":
            headwinds = [
                impl for impl in implications if getattr(impl, "implication", "") == "headwind"
            ]
            headwind_desc = "; ".join(getattr(h, "factor", "") for h in headwinds[:3])
            risks.append(
                StructuredRisk(
                    title="Unfavorable Macro Environment",
                    description=(
                        f"Macro environment assessed as unfavorable for {profile.sector}. "
                        f"Key headwinds: {headwind_desc}."
                    ),
                    category=RiskCategory.MACRO,
                    probability="Medium (20-50%)",
                    probability_pct=40.0,
                    impact="High",
                    impact_description="Multiple compression, demand destruction, earnings miss.",
                    timing=RiskDuration.MEDIUM_TERM,
                    nature=RiskNature.TRANSITORY,
                    mitigants=[
                        "Counter-cyclical positioning within portfolio.",
                        "Company-specific growth drivers may offset macro drag.",
                    ],
                    monitoring_triggers=[
                        "Yield curve inversion deepening.",
                        "ISM Manufacturing below 48.",
                        "Credit spreads widening above 500bps (HY).",
                    ],
                    second_order_effects=[
                        "Sector rotation away from cyclicals toward defensives.",
                        "Capital markets activity slows, affecting revenue for financial sector.",
                        "Consumer confidence decline reduces discretionary spending.",
                    ],
                )
            )

        return risks

    # ------------------------------------------------------------------
    # Competitive risk identification
    # ------------------------------------------------------------------

    def _competitive_risks(self, profile: CompanyProfile, comp: object) -> list[StructuredRisk]:
        """Identify risks from competitive analysis."""
        risks: list[StructuredRisk] = []

        disadvantages = getattr(comp, "competitive_disadvantages", [])
        positioning = getattr(comp, "positioning_summary", "")

        if len(disadvantages) >= 3:
            risks.append(
                StructuredRisk(
                    title="Weak Competitive Position",
                    description=(
                        f"Company ranks below peers on {len(disadvantages)} key metrics. "
                        f"Positioning: {positioning}"
                    ),
                    category=RiskCategory.COMPETITIVE,
                    probability="Medium (20-50%)",
                    probability_pct=35.0,
                    impact="Medium",
                    impact_description=(
                        "Market share erosion, pricing pressure, talent loss to "
                        "competitors."
                    ),
                    timing=RiskDuration.LONG_TERM,
                    nature=RiskNature.STRUCTURAL,
                    mitigants=[
                        "Strategic initiatives to close competitive gaps.",
                        "M&A to acquire missing capabilities.",
                        "Niche positioning where company has advantage.",
                    ],
                    monitoring_triggers=[
                        "Market share data showing sustained losses.",
                        "Win-rate declining in competitive bids.",
                        "Key customer defections.",
                    ],
                    second_order_effects=[
                        "Weaker position reduces pricing power, compressing margins further.",
                        "R&D investment may need to accelerate, pressuring near-term earnings.",
                    ],
                )
            )

        return risks

    # ------------------------------------------------------------------
    # Regulatory risks (sector-specific)
    # ------------------------------------------------------------------

    def _regulatory_risks(self, profile: CompanyProfile) -> list[StructuredRisk]:
        """Identify sector-specific regulatory risks."""
        risks: list[StructuredRisk] = []

        sector = profile.sector or ""

        # Sector-specific regulatory exposure
        sector_reg: dict[str, dict[str, Any]] = {
            "Technology": {
                "title": "Technology Regulation Risk",
                "description": (
                    "Increasing antitrust scrutiny, data privacy regulation (GDPR, CCPA "
                    "successors), "
                    "and AI governance frameworks may constrain business models or increase "
                    "compliance "
                    "costs."
                ),
                "probability": "Medium (20-50%)",
                "impact": "Medium",
                "timing": RiskDuration.LONG_TERM,
            },
            "Healthcare": {
                "title": "Healthcare Regulatory Risk",
                "description": (
                    "Drug pricing reform, FDA approval timelines, and evolving reimbursement "
                    "policies create ongoing regulatory uncertainty."
                ),
                "probability": "Medium (20-50%)",
                "impact": "High",
                "timing": RiskDuration.MEDIUM_TERM,
            },
            "Financial Services": {
                "title": "Financial Regulation Risk",
                "description": (
                    "Capital requirements, consumer protection rules, and stress testing "
                    "frameworks evolve continuously, impacting capital allocation flexibility."
                ),
                "probability": "Medium (20-50%)",
                "impact": "Medium",
                "timing": RiskDuration.LONG_TERM,
            },
            "Energy": {
                "title": "Energy Transition Regulatory Risk",
                "description": (
                    "Carbon pricing, emissions regulations, and ESG disclosure requirements "
                    "may accelerate transition costs or strand assets."
                ),
                "probability": "Medium (20-50%)",
                "impact": "High",
                "timing": RiskDuration.LONG_TERM,
            },
        }

        if sector in sector_reg:
            reg = sector_reg[sector]
            risks.append(
                StructuredRisk(
                    title=reg["title"],
                    description=reg["description"],
                    category=RiskCategory.REGULATORY,
                    probability=reg["probability"],
                    impact=reg["impact"],
                    timing=reg["timing"],
                    nature=RiskNature.STRUCTURAL,
                    mitigants=[
                        "Compliance infrastructure investment.",
                        "Regulatory lobbying and engagement.",
                    ],
                    monitoring_triggers=[
                        "New legislation introduced.",
                        "Regulatory enforcement actions in sector.",
                    ],
                    second_order_effects=[
                        "Compliance costs create barriers to entry (potential moat for incumbents)."
                    ],
                )
            )

        return risks
