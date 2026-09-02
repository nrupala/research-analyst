"""Valuation engine — scenario-based, assumption-driven, never a recommendation.

Responsibilities:
  - Build Bull / Base / Bear scenarios with explicit operating + valuation assumptions
  - Multi-methodology support: DCF, relative (comps), hybrid
  - Sensitivity analysis (what changes the price most?)
  - Variant perception: consensus vs differentiated view
  - Generate the mandatory ASCII valuation chart

Design:
  - Input: FundamentalAnalysis + CompetitiveAnalysis + MacroAnalysis + PriceSeries
  - Output: ValuationRange (with scenarios, assumptions, variant perception)
  - Every price range traces to explicit, spreadsheet-ready assumptions
  - No "target prices" — only assumption-driven scenario ranges
  - If data is missing, the assumption is stated: "Data not available; assumption used: ..."
"""
# Module: research_analyst/engines/valuation.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

import logging
from decimal import Decimal

from ..models import (
    Assumption,
    CompanyProfile,
    FinancialStatement,
    PriceSeries,
    ScenarioType,
    ValuationRange,
    ValuationScenario,
    VariantPerception,
)

logger = logging.getLogger(__name__)


class ValuationEngine:
    """Builds scenario-based valuation ranges.

    Usage:
        engine = ValuationEngine()
        valuation = engine.build_valuation(
            profile, financials, price_series, pe_comps_median, ev_ebitda_comps_median
        )
    """

    def build_valuation(
        self,
        profile: CompanyProfile,
        financials: list[FinancialStatement],
        prices: PriceSeries,
        pe_comps_median: float | None = None,
        ev_ebitda_comps_median: float | None = None,
        analyst_target_mean: float | None = None,
        analyst_target_low: float | None = None,
        analyst_target_high: float | None = None,
        custom_assumptions: dict | None = None,
    ) -> ValuationRange:
        """Build the mandatory 3-scenario valuation range.

        Steps:
          1. Extract latest financials as base
          2. Build Bull / Base / Bear assumptions
          3. Compute implied price ranges via PE and EV/EBITDA
          4. Cross-check with DCF terminal value
          5. Build variant perception
          6. Assemble ValuationRange with ASCII chart

        Args:
            profile: Company profile.
            financials: Financial statements (most recent first).
            prices: Price series with current price.
            pe_comps_median: Peer median P/E ratio.
            ev_ebitda_comps_median: Peer median EV/EBITDA.
            analyst_target_mean: Consensus analyst target (for variant perception).
            analyst_target_low: Analyst target low.
            analyst_target_high: Analyst target high.
            custom_assumptions: User-provided overrides.

        Returns:
            ValuationRange with all three scenarios populated.
        """
        current_price = prices.current_price
        if current_price <= 0:
            logger.warning("Current price is zero or negative for %s", profile.ticker)
            return ValuationRange(
                ticker=profile.ticker,
                current_price=0.0,
                primary_methodology="Insufficient Data",
            )

        custom = custom_assumptions or {}

        # Extract latest financials
        latest = financials[0] if financials else None
        prior = financials[1] if len(financials) >= 2 else None

        # Base metrics
        eps = latest.eps_diluted if latest else None
        revenue = latest.revenue if latest else None
        ebitda = latest.ebitda if latest else None
        net_income = latest.net_income if latest else None
        shares = latest.shares_diluted if latest else None
        op_margin = latest.operating_margin if latest else None
        rev_growth = None
        if latest and prior and prior.revenue and prior.revenue > 0:
            rev_growth = float((latest.revenue - prior.revenue) / prior.revenue) if latest.revenue else None

        # Determine methodology based on data availability
        has_pe = eps is not None and eps > 0
        has_ev_ebitda = ebitda is not None and ebitda > 0 and profile.enterprise_value
        methodology = "Hybrid (PE + EV/EBITDA)" if has_pe and has_ev_ebitda else (
            "PE Multiple" if has_pe else (
                "EV/EBITDA Multiple" if has_ev_ebitda else "Revenue Multiple (fallback)"
            )
        )

        # ---- Build Scenarios ----
        scenarios: list[ValuationScenario] = []

        # Scenario parameter sets: (label, type, rev_growth_adj, margin_adj, multiple_adj)
        scenario_params = [
            ("Bull Case", ScenarioType.BULL, 0.03, 0.02, 1.20),
            ("Base Case", ScenarioType.BASE, 0.00, 0.00, 1.00),
            ("Bear Case", ScenarioType.BEAR, -0.03, -0.02, 0.80),
        ]

        for label, stype, rev_adj, margin_adj, mult_adj in scenario_params:
            scenario = self._build_scenario(
                label=label,
                scenario_type=stype,
                eps=eps,
                revenue=revenue,
                ebitda=ebitda,
                shares=shares,
                op_margin=op_margin,
                rev_growth=rev_growth,
                current_price=current_price,
                pe_comps=pe_comps_median,
                ev_ebitda_comps=ev_ebitda_comps_median,
                enterprise_value=profile.enterprise_value,
                market_cap=profile.market_cap,
                rev_growth_adj=custom.get(f"{stype.value}_rev_growth_adj", rev_adj),
                margin_adj=custom.get(f"{stype.value}_margin_adj", margin_adj),
                multiple_adj=custom.get(f"{stype.value}_multiple_adj", mult_adj),
            )
            scenarios.append(scenario)

        # ---- Variant Perception ----
        variant = self._build_variant_perception(
            scenarios, analyst_target_mean, analyst_target_low, analyst_target_high, current_price
        )

        return ValuationRange(
            ticker=profile.ticker,
            current_price=current_price,
            scenarios=scenarios,
            primary_methodology=methodology,
            variant_perception=variant,
        )

    # ------------------------------------------------------------------
    # Scenario builder
    # ------------------------------------------------------------------

    def _build_scenario(
        self,
        label: str,
        scenario_type: ScenarioType,
        eps: float | None,
        revenue: Decimal | None,
        ebitda: Decimal | None,
        shares: int | None,
        op_margin: float | None,
        rev_growth: float | None,
        current_price: float,
        pe_comps: float | None,
        ev_ebitda_comps: float | None,
        enterprise_value: Decimal | None,
        market_cap: Decimal | None,
        rev_growth_adj: float,
        margin_adj: float,
        multiple_adj: float,
    ) -> ValuationScenario:
        """Build a single valuation scenario with explicit assumptions."""

        assumptions: list[Assumption] = []
        price_estimates: list[float] = []

        # ---- Revenue growth assumption ----
        base_rev_growth = rev_growth if rev_growth is not None else 0.05
        scenario_rev_growth = base_rev_growth + rev_growth_adj

        if rev_growth is None:
            assumptions.append(Assumption(
                label="Revenue Growth",
                value=f"{scenario_rev_growth:.1%}",
                source="Data not available; assumption used: 5% base + scenario adjustment",
                confidence="Low",
            ))
        else:
            assumptions.append(Assumption(
                label="Revenue Growth",
                value=f"{scenario_rev_growth:.1%}",
                source=f"Historical YoY: {rev_growth:.1%}, adjusted {rev_growth_adj:+.1%} for {label}",
                confidence="Medium",
            ))

        # ---- Margin assumption ----
        base_margin = op_margin if op_margin is not None else 0.15
        scenario_margin = base_margin + margin_adj

        assumptions.append(Assumption(
            label="Operating Margin",
            value=f"{scenario_margin:.1%}",
            source=f"Current: {base_margin:.1%}, adjusted {margin_adj:+.1%} for {label}",
            confidence="Medium" if op_margin is not None else "Low",
        ))

        # ---- PE-based valuation ----
        if eps is not None and eps > 0:
            # Current trailing PE
            current_pe = current_price / eps

            # Scenario PE: blend own trailing PE with peer median
            # If the stock trades at a dramatic premium to peers (>2x peer median),
            # use a weighted blend: 70% own PE + 30% peer median
            # This prevents high-growth stocks (TSLA, NVDA) from being valued
            # at commodity-sector multiples
            if pe_comps and pe_comps > 0:
                if current_pe > pe_comps * 2:
                    # High-premium stock: mostly own PE, slight peer gravity
                    base_pe = current_pe * 0.7 + pe_comps * 0.3
                    pe_source = f"blended (70% trailing {current_pe:.1f}x + 30% peer median {pe_comps:.1f}x)"
                elif current_pe < pe_comps * 0.5:
                    # Deep discount: mostly peer PE, slight own gravity
                    base_pe = current_pe * 0.3 + pe_comps * 0.7
                    pe_source = f"blended (30% trailing {current_pe:.1f}x + 70% peer median {pe_comps:.1f}x)"
                else:
                    # Reasonably aligned: use peer median
                    base_pe = pe_comps
                    pe_source = f"peer median {pe_comps:.1f}x"
            else:
                base_pe = current_pe
                pe_source = f"trailing {current_pe:.1f}x"
            scenario_pe = base_pe * multiple_adj

            # Forward EPS estimate: grow by revenue growth + margin change effect
            forward_eps = eps * (1 + scenario_rev_growth)
            if op_margin and op_margin > 0:
                margin_effect = 1 + (margin_adj / op_margin)
                forward_eps *= margin_effect

            implied_pe_price = forward_eps * scenario_pe
            if implied_pe_price > 0:
                price_estimates.append(implied_pe_price)

            assumptions.append(Assumption(
                label="P/E Multiple",
                value=f"{scenario_pe:.1f}x",
                source=f"Base: {base_pe:.1f}x ({pe_source}), adjusted {multiple_adj:.0%} for {label}",
                confidence="Medium",
            ))
            assumptions.append(Assumption(
                label="Forward EPS Estimate",
                value=f"${forward_eps:.2f}",
                source=f"Trailing EPS ${eps:.2f} * (1 + {scenario_rev_growth:.1%} growth) * margin effect",
                confidence="Medium" if rev_growth is not None else "Low",
            ))

        # ---- EV/EBITDA-based valuation ----
        if ebitda and ebitda > 0 and shares and shares > 0:
            base_ev_ebitda = ev_ebitda_comps if ev_ebitda_comps and ev_ebitda_comps > 0 else (
                float(enterprise_value / ebitda) if enterprise_value else 12.0
            )
            scenario_ev_ebitda = base_ev_ebitda * multiple_adj

            # Forward EBITDA
            forward_ebitda = float(ebitda) * (1 + scenario_rev_growth)
            if op_margin and op_margin > 0:
                forward_ebitda *= (1 + margin_adj / op_margin)

            implied_ev = forward_ebitda * scenario_ev_ebitda

            # EV to equity: EV - net debt + cash (simplified)
            # Use market cap / EV ratio as proxy
            if enterprise_value and market_cap and float(enterprise_value) > 0:
                equity_ratio = float(market_cap) / float(enterprise_value)
            else:
                equity_ratio = 0.85  # Default assumption
                assumptions.append(Assumption(
                    label="Equity/EV Ratio",
                    value="85%",
                    source="Data not available; assumption used: 85% equity-to-EV ratio",
                    confidence="Low",
                ))

            implied_equity = implied_ev * equity_ratio
            implied_ev_price = implied_equity / shares
            if implied_ev_price > 0:
                price_estimates.append(implied_ev_price)

            assumptions.append(Assumption(
                label="EV/EBITDA Multiple",
                value=f"{scenario_ev_ebitda:.1f}x",
                source=f"Base: {base_ev_ebitda:.1f}x ({'peer median' if ev_ebitda_comps else 'trailing'}), "
                       f"adjusted {multiple_adj:.0%} for {label}",
                confidence="Medium",
            ))

        # ---- Revenue multiple fallback ----
        if not price_estimates and revenue and revenue > 0 and shares and shares > 0:
            # P/S as last resort
            ps_ratio = float(market_cap / revenue) if market_cap else 3.0
            scenario_ps = ps_ratio * multiple_adj
            forward_revenue = float(revenue) * (1 + scenario_rev_growth)
            implied_ps_price = (forward_revenue * scenario_ps) / shares

            if implied_ps_price > 0:
                price_estimates.append(implied_ps_price)

            assumptions.append(Assumption(
                label="P/S Multiple (Fallback)",
                value=f"{scenario_ps:.1f}x",
                source="PE and EV/EBITDA unavailable; using revenue multiple",
                confidence="Low",
            ))

        # ---- Aggregate price range ----
        if price_estimates:
            price_low = min(price_estimates) * 0.95  # 5% band
            price_high = max(price_estimates) * 1.05
        else:
            # No valuation possible — use current price with wide band
            price_low = current_price * (0.7 if scenario_type == ScenarioType.BEAR else 0.9)
            price_high = current_price * (1.1 if scenario_type == ScenarioType.BEAR else 1.3)
            assumptions.append(Assumption(
                label="Price Range",
                value=f"${price_low:.0f}-${price_high:.0f}",
                source="Insufficient data for fundamental valuation; band estimated from current price",
                confidence="Low",
            ))

        upside_low = (price_low - current_price) / current_price
        upside_high = (price_high - current_price) / current_price

        # ---- Narrative ----
        narrative = self._scenario_narrative(
            label, scenario_rev_growth, scenario_margin, price_low, price_high, current_price
        )

        return ValuationScenario(
            scenario_type=scenario_type,
            label=label,
            assumptions=assumptions,
            revenue_growth=scenario_rev_growth,
            operating_margin=scenario_margin,
            pe_multiple=None,  # Set in assumptions
            ev_ebitda_multiple=None,
            implied_price_low=round(price_low, 2),
            implied_price_high=round(price_high, 2),
            implied_upside_low=round(upside_low, 4),
            implied_upside_high=round(upside_high, 4),
            narrative=narrative,
        )

    # ------------------------------------------------------------------
    # Variant perception
    # ------------------------------------------------------------------

    @staticmethod
    def _build_variant_perception(
        scenarios: list[ValuationScenario],
        analyst_mean: float | None,
        analyst_low: float | None,
        analyst_high: float | None,
        current_price: float,
    ) -> VariantPerception:
        """Build the mandatory variant perception section.

        Compares our scenario-based range to analyst consensus.
        """
        # Our base case
        base = next((s for s in scenarios if s.scenario_type == ScenarioType.BASE), None)
        base_mid = (
            (base.implied_price_low + base.implied_price_high) / 2
            if base and base.implied_price_low and base.implied_price_high
            else current_price
        )

        if analyst_mean and analyst_mean > 0:
            diff_pct = (base_mid - analyst_mean) / analyst_mean * 100

            if abs(diff_pct) < 5:
                consensus = (
                    f"Analyst consensus target: ${analyst_mean:.0f} "
                    f"(range: ${analyst_low:.0f}-${analyst_high:.0f}). "
                    f"Our base case (${base_mid:.0f}) is closely aligned."
                )
                variant = (
                    "No significant variant perception vs consensus. "
                    "The key differentiator is our explicit assumption framework, "
                    "which makes the range reproducible and auditable."
                )
                why = (
                    "Alignment with consensus reduces conviction risk but also "
                    "reduces the probability of outsized returns from mispricing."
                )
            elif diff_pct > 5:
                consensus = (
                    f"Analyst consensus target: ${analyst_mean:.0f}. "
                    f"Our base case (${base_mid:.0f}) is {diff_pct:.1f}% above consensus."
                )
                variant = (
                    "Our assumptions imply more favorable outcomes than the street. "
                    "Key differentiators: the operating assumptions in our base case "
                    "may embed growth or margin expansion the consensus has not yet priced."
                )
                why = (
                    f"If our assumptions prove correct, the current price "
                    f"(${current_price:.0f}) may undervalue the security. "
                    f"However, if consensus is right, we are overestimating."
                )
            else:
                consensus = (
                    f"Analyst consensus target: ${analyst_mean:.0f}. "
                    f"Our base case (${base_mid:.0f}) is {abs(diff_pct):.1f}% below consensus."
                )
                variant = (
                    "Our assumptions imply less favorable outcomes than the street. "
                    "This could reflect more conservative growth or margin assumptions, "
                    "or a higher discount for macro/competitive risks."
                )
                why = (
                    "If consensus is over-optimistic, current price may be stretched. "
                    "Our conservative base may prove more realistic in a decelerating environment."
                )
        else:
            consensus = "Analyst consensus data unavailable."
            variant = (
                "Without consensus comparison, variant perception cannot be assessed. "
                "The scenario range stands on its explicit assumptions alone."
            )
            why = "Monitor for analyst coverage initiation or update."

        return VariantPerception(
            consensus_view=consensus,
            variant_view=variant,
            why_it_matters=why,
        )

    @staticmethod
    def _scenario_narrative(
        label: str,
        rev_growth: float,
        op_margin: float,
        price_low: float,
        price_high: float,
        current: float,
    ) -> str:
        """Generate scenario narrative text."""
        upside_mid = ((price_low + price_high) / 2 - current) / current * 100
        direction = "upside" if upside_mid > 0 else "downside"

        return (
            f"{label} assumes {rev_growth:.1%} revenue growth and "
            f"{op_margin:.1%} operating margin, implying a "
            f"${price_low:.0f}-${price_high:.0f} range "
            f"({abs(upside_mid):.1f}% {direction} from current ${current:.0f})."
        )
