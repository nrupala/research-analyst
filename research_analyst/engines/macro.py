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

"""Macro context engine — interprets macro environment for sector/security impact.

Responsibilities:
  - Map macro regime to sector sensitivity
  - Rate environment impact assessment
  - Inflation regime classification
  - Credit cycle positioning
  - Second-order effects identification

Design:
  - Input: MacroSnapshot + CompanyProfile (sector/industry context)
  - Output: MacroAnalysis with sector-specific implications
  - Deterministic rules-based interpretation — no ML, no black boxes
  - Every interpretation carries an explicit assumption
"""
# Module: research_analyst/engines/macro.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..models import Assumption, CompanyProfile, MacroSnapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sector sensitivity mappings — empirical, documented
# ---------------------------------------------------------------------------

# How each sector responds to macro factors.
# Scale: -2 (strong headwind) to +2 (strong tailwind)
SECTOR_RATE_SENSITIVITY: dict[str, float] = {
    "Technology": -1.5,          # Growth stocks hurt by higher rates (higher discount rate)
    "Healthcare": -0.5,          # Moderate sensitivity
    "Financial Services": 1.5,   # Banks benefit from higher NIM
    "Financials": 1.5,
    "Consumer Cyclical": -1.0,   # Consumer spending pressured
    "Consumer Defensive": 0.5,   # Stable, slight benefit from pricing power
    "Communication Services": -1.0,
    "Industrials": -0.5,         # Mixed — capex sensitive but economic growth driven
    "Energy": 0.0,               # Driven by commodity prices, not rates directly
    "Utilities": -1.5,           # Bond proxies hurt by rate rises
    "Real Estate": -2.0,         # Most rate-sensitive sector
    "Basic Materials": -0.5,
}

SECTOR_INFLATION_SENSITIVITY: dict[str, float] = {
    "Technology": -1.0,
    "Healthcare": 0.5,           # Pricing power
    "Financial Services": 0.5,
    "Financials": 0.5,
    "Consumer Cyclical": -1.5,   # Margin squeeze
    "Consumer Defensive": 1.0,   # Can pass through costs
    "Communication Services": -0.5,
    "Industrials": -1.0,         # Input cost pressure
    "Energy": 2.0,               # Direct beneficiary
    "Utilities": -0.5,           # Regulated pricing lag
    "Real Estate": 0.5,          # Rent escalators
    "Basic Materials": 1.5,      # Commodity producers benefit
}

SECTOR_RECESSION_SENSITIVITY: dict[str, float] = {
    "Technology": -1.5,
    "Healthcare": 0.5,           # Defensive
    "Financial Services": -1.5,  # Credit losses
    "Financials": -1.5,
    "Consumer Cyclical": -2.0,   # Most cyclical
    "Consumer Defensive": 1.0,   # Counter-cyclical
    "Communication Services": -1.0,
    "Industrials": -1.5,
    "Energy": -1.0,
    "Utilities": 1.0,            # Defensive
    "Real Estate": -1.5,
    "Basic Materials": -1.5,
}


@dataclass
class MacroImplication:
    """Single macro factor's implication for the security."""

    factor: str
    current_value: str
    regime: str
    sector_sensitivity: float
    implication: str       # "tailwind" / "headwind" / "neutral"
    magnitude: str         # "strong" / "moderate" / "mild"
    description: str
    second_order_effects: list[str] = field(default_factory=list)


@dataclass
class MacroAnalysis:
    """Structured macro context analysis."""

    ticker: str = ""
    sector: str = ""

    # Regime classification
    rate_regime: str = ""       # "rising" / "falling" / "stable" / "peak" / "trough"
    inflation_regime: str = ""  # "elevated" / "moderating" / "low" / "deflation"
    growth_regime: str = ""     # "expansion" / "slowdown" / "contraction" / "recovery"
    credit_regime: str = ""     # "tightening" / "easing" / "neutral"
    volatility_regime: str = "" # "low" / "moderate" / "elevated" / "crisis"

    # Overall assessment
    macro_favorability: str = ""  # "favorable" / "neutral" / "unfavorable"
    macro_score: float = 50.0     # 0=very unfavorable, 100=very favorable

    # Individual implications
    implications: list[MacroImplication] = field(default_factory=list)

    # Cycle positioning
    cycle_phase: str = ""
    cycle_description: str = ""

    # Traceability
    assumptions: list[Assumption] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)


class MacroEngine:
    """Interprets macro environment in context of a specific security/sector.

    Usage:
        engine = MacroEngine()
        analysis = engine.analyze(macro_snapshot, company_profile)
    """

    def analyze(
        self,
        macro: MacroSnapshot,
        profile: CompanyProfile,
    ) -> MacroAnalysis:
        """Analyze macro environment impact on a specific security.

        Steps:
          1. Classify macro regimes (rates, inflation, growth, credit, vol)
          2. Map sector sensitivity to each regime
          3. Identify second-order effects
          4. Compute composite macro score
          5. Determine overall favorability
        """
        result = MacroAnalysis(
            ticker=profile.ticker,
            sector=profile.sector,
        )

        # ---- 1. Regime Classification ----
        result.rate_regime = self._classify_rate_regime(macro)
        result.inflation_regime = self._classify_inflation_regime(macro)
        result.growth_regime = self._classify_growth_regime(macro)
        result.credit_regime = self._classify_credit_regime(macro)
        result.volatility_regime = self._classify_volatility_regime(macro)

        # ---- 2. Sector-Specific Implications ----
        sector = profile.sector or "Technology"  # Default if unknown

        # Rate impact
        rate_sens = SECTOR_RATE_SENSITIVITY.get(sector, 0.0)
        rate_impl = self._build_implication(
            factor="Interest Rates",
            current_value=f"{macro.us_10y_yield:.2%}" if macro.us_10y_yield else "N/A",
            regime=result.rate_regime,
            sensitivity=rate_sens,
            sector=sector,
        )
        if macro.us_10y_yield is None:
            result.data_gaps.append("10Y Treasury yield unavailable.")
        else:
            # Second-order effects for rates
            if result.rate_regime in ("rising", "peak"):
                rate_impl.second_order_effects = [
                    "Higher discount rates compress growth stock valuations.",
                    "Increased borrowing costs may defer capex plans.",
                    "Consumer credit tightening reduces discretionary spending.",
                ]
            elif result.rate_regime in ("falling", "trough"):
                rate_impl.second_order_effects = [
                    "Lower discount rates expand growth multiples.",
                    "Cheaper debt may accelerate M&A activity.",
                    "Mortgage rate declines support housing-linked sectors.",
                ]
        result.implications.append(rate_impl)

        # Inflation impact
        inf_sens = SECTOR_INFLATION_SENSITIVITY.get(sector, 0.0)
        inf_impl = self._build_implication(
            factor="Inflation",
            current_value=f"{macro.cpi_yoy:.1%}" if macro.cpi_yoy else "N/A",
            regime=result.inflation_regime,
            sensitivity=inf_sens,
            sector=sector,
        )
        if macro.cpi_yoy is None:
            result.data_gaps.append("CPI data unavailable.")
        else:
            if result.inflation_regime == "elevated":
                inf_impl.second_order_effects = [
                    "Input cost pressure may compress margins unless pricing power exists.",
                    "Consumer real income erosion reduces volume demand.",
                    "Wage inflation increases operating costs for labor-intensive sectors.",
                ]
        result.implications.append(inf_impl)

        # Recession / growth impact
        rec_sens = SECTOR_RECESSION_SENSITIVITY.get(sector, 0.0)
        growth_impl = self._build_implication(
            factor="Economic Growth",
            current_value=f"{macro.gdp_growth_latest:.1%}" if macro.gdp_growth_latest else "N/A",
            regime=result.growth_regime,
            sensitivity=rec_sens if result.growth_regime in ("contraction", "slowdown") else -rec_sens,
            sector=sector,
        )
        if macro.gdp_growth_latest is None:
            result.data_gaps.append("GDP growth data unavailable.")
        result.implications.append(growth_impl)

        # Volatility impact
        vol_impl = MacroImplication(
            factor="Market Volatility (VIX)",
            current_value=f"{macro.vix:.1f}" if macro.vix else "N/A",
            regime=result.volatility_regime,
            sector_sensitivity=0.0,
            implication="neutral",
            magnitude="mild",
            description="",
        )
        if macro.vix is not None:
            if macro.vix > 30:
                vol_impl.implication = "headwind"
                vol_impl.magnitude = "strong"
                vol_impl.description = (
                    f"VIX at {macro.vix:.1f} indicates elevated fear. "
                    "Risk premiums expand; multiple compression likely."
                )
            elif macro.vix > 20:
                vol_impl.implication = "headwind"
                vol_impl.magnitude = "moderate"
                vol_impl.description = f"VIX at {macro.vix:.1f} — above average uncertainty."
            else:
                vol_impl.implication = "tailwind"
                vol_impl.magnitude = "mild"
                vol_impl.description = f"VIX at {macro.vix:.1f} — calm conditions favor risk assets."
        result.implications.append(vol_impl)

        # ---- 3. Cycle Positioning ----
        result.cycle_phase = macro.cycle_phase or self._infer_cycle(macro)
        result.cycle_description = self._describe_cycle(result.cycle_phase, sector)

        # ---- 4. Composite Score ----
        score_components: list[float] = []
        for impl in result.implications:
            if impl.implication == "tailwind":
                base = 70.0
            elif impl.implication == "headwind":
                base = 30.0
            else:
                base = 50.0

            magnitude_adj = {"strong": 15.0, "moderate": 8.0, "mild": 3.0}.get(impl.magnitude, 0.0)
            if impl.implication == "tailwind":
                score_components.append(base + magnitude_adj)
            elif impl.implication == "headwind":
                score_components.append(base - magnitude_adj)
            else:
                score_components.append(base)

        result.macro_score = sum(score_components) / len(score_components) if score_components else 50.0

        # ---- 5. Overall Favorability ----
        if result.macro_score >= 60:
            result.macro_favorability = "favorable"
        elif result.macro_score >= 40:
            result.macro_favorability = "neutral"
        else:
            result.macro_favorability = "unfavorable"

        # ---- Assumptions ----
        result.assumptions.append(Assumption(
            label="Macro Data Source",
            value="Market proxies via yfinance (^TNX, ^VIX). Official FRED data preferred when available.",
            source="MarketDataProvider",
            confidence="Medium",
        ))
        result.assumptions.append(Assumption(
            label="Sector Sensitivity Model",
            value=f"Empirical sensitivity mappings for '{sector}'. "
                  "Based on historical sector-factor relationships; directional, not precise.",
            source="Engine heuristics",
            confidence="Medium",
        ))

        return result

    # ------------------------------------------------------------------
    # Regime classifiers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_rate_regime(macro: MacroSnapshot) -> str:
        if macro.us_10y_yield is None:
            return "unknown"
        if macro.us_10y_yield > 0.045:
            return "peak"
        elif macro.us_10y_yield > 0.035:
            return "rising"
        elif macro.us_10y_yield > 0.02:
            return "stable"
        else:
            return "trough"

    @staticmethod
    def _classify_inflation_regime(macro: MacroSnapshot) -> str:
        if macro.cpi_yoy is None:
            return "unknown"
        if macro.cpi_yoy > 0.04:
            return "elevated"
        elif macro.cpi_yoy > 0.025:
            return "moderating"
        elif macro.cpi_yoy > 0.005:
            return "low"
        else:
            return "deflation"

    @staticmethod
    def _classify_growth_regime(macro: MacroSnapshot) -> str:
        if macro.gdp_growth_latest is None:
            return "unknown"
        if macro.gdp_growth_latest > 0.03:
            return "expansion"
        elif macro.gdp_growth_latest > 0.01:
            return "slowdown"
        elif macro.gdp_growth_latest > -0.005:
            return "stagnation"
        else:
            return "contraction"

    @staticmethod
    def _classify_credit_regime(macro: MacroSnapshot) -> str:
        if macro.credit_spread_hy is None:
            return "unknown"
        if macro.credit_spread_hy > 0.06:
            return "tightening"
        elif macro.credit_spread_hy > 0.04:
            return "neutral"
        else:
            return "easing"

    @staticmethod
    def _classify_volatility_regime(macro: MacroSnapshot) -> str:
        if macro.vix is None:
            return "unknown"
        if macro.vix > 35:
            return "crisis"
        elif macro.vix > 25:
            return "elevated"
        elif macro.vix > 15:
            return "moderate"
        else:
            return "low"

    @staticmethod
    def _infer_cycle(macro: MacroSnapshot) -> str:
        """Infer business cycle phase from available data."""
        if macro.gdp_growth_latest is not None:
            if macro.gdp_growth_latest > 0.025:
                return "expansion"
            elif macro.gdp_growth_latest > 0:
                return "late_cycle"
            else:
                return "contraction"
        return "unknown"

    @staticmethod
    def _describe_cycle(phase: str, sector: str) -> str:
        descriptions: dict[str, str] = {
            "expansion": (
                f"Economy in expansion phase. {sector} sector typically benefits from "
                "rising earnings expectations and risk appetite."
            ),
            "late_cycle": (
                f"Late-cycle environment. {sector} may face margin pressure as costs rise "
                "faster than revenue. Selectivity favored over broad exposure."
            ),
            "contraction": (
                f"Economic contraction. {sector} faces demand headwinds. "
                "Quality balance sheets and defensive positioning matter most."
            ),
            "recovery": (
                f"Early recovery phase. {sector} positioned to benefit from "
                "re-acceleration in demand and easing financial conditions."
            ),
        }
        return descriptions.get(phase, f"Cycle phase '{phase}' — limited macro data for assessment.")

    @staticmethod
    def _build_implication(
        factor: str,
        current_value: str,
        regime: str,
        sensitivity: float,
        sector: str,
    ) -> MacroImplication:
        """Build a MacroImplication from sensitivity score."""
        if sensitivity > 0.5:
            implication = "tailwind"
        elif sensitivity < -0.5:
            implication = "headwind"
        else:
            implication = "neutral"

        abs_sens = abs(sensitivity)
        if abs_sens > 1.5:
            magnitude = "strong"
        elif abs_sens > 0.8:
            magnitude = "moderate"
        else:
            magnitude = "mild"

        direction = "positive" if sensitivity > 0 else "negative" if sensitivity < 0 else "neutral"

        return MacroImplication(
            factor=factor,
            current_value=current_value,
            regime=regime,
            sector_sensitivity=sensitivity,
            implication=implication,
            magnitude=magnitude,
            description=(
                f"{factor} regime is '{regime}' (current: {current_value}). "
                f"{sector} sector has {direction} sensitivity ({sensitivity:+.1f}). "
                f"Net impact: {magnitude} {implication}."
            ),
        )
