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

"""Fundamental analysis engine — financial statement analysis, growth, profitability.

Responsibilities:
  - Compute growth rates (revenue, earnings, FCF) across periods
  - Assess margin trajectories and quality of earnings
  - Capital efficiency analysis (ROIC, ROE, asset turnover)
  - Balance sheet health scoring
  - Earnings quality assessment
  - All computations traced to explicit assumptions

Design:
  - Input: FundamentalData (from providers)
  - Output: FundamentalAnalysis (structured findings + assumptions)
  - O(n) in number of financial periods — no nested loops over periods
  - Every computed metric carries its source assumption
"""
# Module: research_analyst/engines/fundamental.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..models import (
    Assumption,
    CapitalAllocation,
    FinancialStatement,
    FundamentalData,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

@dataclass
class FundamentalAnalysis:
    """Structured output of fundamental analysis."""

    ticker: str = ""

    # Growth metrics (most recent period vs prior)
    revenue_growth_yoy: float | None = None
    revenue_cagr_3y: float | None = None
    revenue_cagr_5y: float | None = None
    earnings_growth_yoy: float | None = None
    eps_growth_yoy: float | None = None
    fcf_growth_yoy: float | None = None

    # Profitability
    gross_margin_latest: float | None = None
    gross_margin_trend: str = ""  # "expanding" / "contracting" / "stable"
    operating_margin_latest: float | None = None
    operating_margin_trend: str = ""
    net_margin_latest: float | None = None
    ebitda_margin_latest: float | None = None
    fcf_margin_latest: float | None = None

    # Efficiency
    roe_latest: float | None = None
    roa_latest: float | None = None
    roic_latest: float | None = None
    asset_turnover: float | None = None

    # Balance sheet
    debt_to_equity: float | None = None
    net_debt_to_ebitda: float | None = None
    current_ratio: float | None = None
    interest_coverage: float | None = None
    cash_as_pct_of_market_cap: float | None = None
    balance_sheet_grade: str = ""  # "Strong" / "Adequate" / "Weak" / "Critical"

    # Earnings quality
    accrual_ratio: float | None = None  # (Net Income - OCF) / Total Assets
    earnings_quality_grade: str = ""  # "High" / "Moderate" / "Low"
    fcf_to_net_income: float | None = None  # >1.0 is high quality

    # Capital allocation
    capital_allocation: CapitalAllocation | None = None

    # Traceability
    assumptions: list[Assumption] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)
    periods_analyzed: int = 0

    # Raw financials for report rendering
    financials: list[FinancialStatement] = field(default_factory=list)


class FundamentalEngine:
    """Stateless fundamental analysis engine.

    Usage:
        engine = FundamentalEngine()
        analysis = engine.analyze(fundamental_data)
    """

    def analyze(self, data: FundamentalData) -> FundamentalAnalysis:
        """Run complete fundamental analysis.

        Single-pass through financial periods (most recent first):
          1. Extract latest period metrics
          2. Compute YoY growth rates
          3. Compute CAGRs
          4. Assess margin trends
          5. Score balance sheet
          6. Assess earnings quality
          7. Analyze capital allocation

        Args:
            data: FundamentalData containing profile + financial statements.

        Returns:
            FundamentalAnalysis with all computed metrics and assumptions.
        """
        result = FundamentalAnalysis(
            ticker=data.profile.ticker,
            financials=data.financials,
            periods_analyzed=len(data.financials),
        )

        if not data.financials:
            result.data_gaps.append("No financial statements available.")
            return result

        # Sort: most recent first (should already be, but enforce)
        periods = sorted(
            data.financials,
            key=lambda f: f.period_end_date or date.min,
            reverse=True,
        )
        latest = periods[0]
        prior = periods[1] if len(periods) >= 2 else None

        # ---- Latest period metrics ----
        result.gross_margin_latest = latest.gross_margin
        result.operating_margin_latest = latest.operating_margin
        result.net_margin_latest = latest.net_margin
        result.ebitda_margin_latest = latest.ebitda_margin
        result.roe_latest = latest.roe
        result.roa_latest = latest.roa
        result.roic_latest = latest.roic
        result.debt_to_equity = latest.debt_to_equity
        result.current_ratio = latest.current_ratio
        result.interest_coverage = latest.interest_coverage

        # FCF margin
        if latest.free_cash_flow is not None and latest.revenue and latest.revenue != 0:
            result.fcf_margin_latest = float(latest.free_cash_flow / latest.revenue)

        # Asset turnover = Revenue / Total Assets
        if latest.revenue and latest.total_assets and latest.total_assets != 0:
            result.asset_turnover = float(latest.revenue / latest.total_assets)

        # ---- YoY Growth Rates ----
        if prior:
            result.revenue_growth_yoy = self._growth_rate(latest.revenue, prior.revenue)
            result.earnings_growth_yoy = self._growth_rate(latest.net_income, prior.net_income)
            result.fcf_growth_yoy = self._growth_rate(
                latest.free_cash_flow, prior.free_cash_flow
            )
            if latest.eps_diluted is not None and prior.eps_diluted and prior.eps_diluted != 0:
                result.eps_growth_yoy = (latest.eps_diluted - prior.eps_diluted) / abs(prior.eps_diluted)
        else:
            result.data_gaps.append("Only one period available; cannot compute YoY growth.")

        # ---- CAGRs ----
        if len(periods) >= 4:
            result.revenue_cagr_3y = self._cagr(
                periods[-3].revenue if len(periods) >= 4 else periods[-1].revenue,
                latest.revenue,
                3,
            )
        if len(periods) >= 6:
            result.revenue_cagr_5y = self._cagr(
                periods[-5].revenue if len(periods) >= 6 else periods[-1].revenue,
                latest.revenue,
                5,
            )

        # ---- Margin Trends ----
        if len(periods) >= 3:
            gm_series = [p.gross_margin for p in periods[:3] if p.gross_margin is not None]
            result.gross_margin_trend = self._trend(gm_series)

            om_series = [p.operating_margin for p in periods[:3] if p.operating_margin is not None]
            result.operating_margin_trend = self._trend(om_series)

        # ---- Balance Sheet Grade ----
        result.balance_sheet_grade = self._grade_balance_sheet(latest)

        # ---- Net Debt / EBITDA ----
        if latest.net_debt is not None and latest.ebitda and latest.ebitda != 0:
            result.net_debt_to_ebitda = float(latest.net_debt / latest.ebitda)

        # ---- Earnings Quality ----
        result = self._assess_earnings_quality(latest, result)

        # ---- Capital Allocation ----
        result.capital_allocation = self._analyze_capital_allocation(latest)

        # ---- Assumptions ----
        result.assumptions.append(Assumption(
            label="Analysis Period",
            value=f"{result.periods_analyzed} annual periods, most recent: {latest.period}",
            source="SEC/yfinance financial statements",
        ))
        if result.revenue_growth_yoy is not None:
            result.assumptions.append(Assumption(
                label="Revenue Growth (YoY)",
                value=f"{result.revenue_growth_yoy:.1%}",
                source=f"{latest.period} vs {prior.period}" if prior else "N/A",
            ))

        return result

    # ------------------------------------------------------------------
    # Computation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _growth_rate(current: Decimal | None, prior: Decimal | None) -> float | None:
        """Compute growth rate: (current - prior) / |prior|.

        Returns None if either value is missing or prior is zero.
        Handles negative base values correctly using absolute value.
        """
        if current is None or prior is None or prior == 0:
            return None
        return float((current - prior) / abs(prior))

    @staticmethod
    def _cagr(start: Decimal | None, end: Decimal | None, years: int) -> float | None:
        """Compound Annual Growth Rate.

        CAGR = (end/start)^(1/years) - 1
        Returns None if inputs are invalid or start is non-positive.
        """
        if start is None or end is None or start <= 0 or end <= 0 or years <= 0:
            return None
        return float((float(end) / float(start)) ** (1.0 / years) - 1.0)

    @staticmethod
    def _trend(values: list[float]) -> str:
        """Assess trend direction from a series (most recent first).

        Uses simple linear regression slope sign.
        Returns: "expanding" / "contracting" / "stable"
        """
        if len(values) < 2:
            return "insufficient_data"

        # Values are most-recent-first; reverse for chronological order
        chron = list(reversed(values))
        n = len(chron)
        x_mean = (n - 1) / 2.0
        y_mean = sum(chron) / n

        numerator = sum((i - x_mean) * (chron[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return "stable"

        slope = numerator / denominator

        # Threshold: slope > 0.5% of mean per period is meaningful
        if y_mean != 0 and abs(slope / y_mean) < 0.005:
            return "stable"

        return "expanding" if slope > 0 else "contracting"

    @staticmethod
    def _grade_balance_sheet(stmt: FinancialStatement) -> str:
        """Score balance sheet health.

        Criteria (weighted heuristic):
          - Debt/Equity < 0.5 → strong, 0.5-1.5 → adequate, >1.5 → weak
          - Current ratio > 2.0 → strong, 1.0-2.0 → adequate, <1.0 → weak
          - Interest coverage > 10 → strong, 3-10 → adequate, <3 → weak
          - Cash position relative to debt
        """
        score = 0
        checks = 0

        if stmt.debt_to_equity is not None:
            checks += 1
            if stmt.debt_to_equity < 0.5:
                score += 3
            elif stmt.debt_to_equity < 1.5:
                score += 2
            else:
                score += 1

        if stmt.current_ratio is not None:
            checks += 1
            if stmt.current_ratio > 2.0:
                score += 3
            elif stmt.current_ratio > 1.0:
                score += 2
            else:
                score += 1

        if stmt.interest_coverage is not None:
            checks += 1
            if stmt.interest_coverage > 10:
                score += 3
            elif stmt.interest_coverage > 3:
                score += 2
            else:
                score += 1

        if stmt.net_debt is not None and stmt.ebitda and stmt.ebitda > 0:
            checks += 1
            ratio = float(stmt.net_debt / stmt.ebitda)
            if ratio < 1:
                score += 3
            elif ratio < 3:
                score += 2
            else:
                score += 1

        if checks == 0:
            return "Insufficient Data"

        avg = score / checks
        if avg >= 2.5:
            return "Strong"
        elif avg >= 1.5:
            return "Adequate"
        else:
            return "Weak"

    @staticmethod
    def _assess_earnings_quality(
        stmt: FinancialStatement, result: FundamentalAnalysis
    ) -> FundamentalAnalysis:
        """Assess earnings quality using accrual ratio and FCF/NI ratio.

        High quality: FCF > Net Income (cash > reported earnings)
        Low quality: Large accruals, FCF << Net Income
        """
        # FCF / Net Income
        if stmt.free_cash_flow is not None and stmt.net_income and stmt.net_income != 0:
            result.fcf_to_net_income = float(stmt.free_cash_flow / stmt.net_income)

        # Accrual ratio = (Net Income - Operating CF) / Total Assets
        if (
            stmt.net_income is not None
            and stmt.operating_cash_flow is not None
            and stmt.total_assets
            and stmt.total_assets != 0
        ):
            result.accrual_ratio = float(
                (stmt.net_income - stmt.operating_cash_flow) / stmt.total_assets
            )

        # Grade
        if result.fcf_to_net_income is not None:
            if result.fcf_to_net_income >= 0.8:
                result.earnings_quality_grade = "High"
            elif result.fcf_to_net_income >= 0.4:
                result.earnings_quality_grade = "Moderate"
            else:
                result.earnings_quality_grade = "Low"
        elif result.accrual_ratio is not None:
            if result.accrual_ratio < 0.05:
                result.earnings_quality_grade = "High"
            elif result.accrual_ratio < 0.15:
                result.earnings_quality_grade = "Moderate"
            else:
                result.earnings_quality_grade = "Low"
        else:
            result.earnings_quality_grade = "Insufficient Data"

        return result

    @staticmethod
    def _analyze_capital_allocation(stmt: FinancialStatement) -> CapitalAllocation:
        """Analyze how the company allocates capital.

        Decomposes FCF usage: capex, buybacks, dividends, debt repayment.
        Computes shareholder yield = (buybacks + dividends) / market cap (if available).
        """
        fcf = stmt.free_cash_flow

        # Calculate as % of total capital deployed (not FCF)
        # This ensures percentages sum to ~100% on the allocation diagram
        capex_abs = float(abs(stmt.capex)) if stmt.capex is not None else 0.0
        buyback_abs = float(abs(stmt.share_buybacks)) if stmt.share_buybacks is not None else 0.0
        div_abs = float(abs(stmt.dividends_paid)) if stmt.dividends_paid is not None else 0.0
        total_deployed = capex_abs + buyback_abs + div_abs

        capex_pct = None
        buyback_pct = None
        div_pct = None

        if total_deployed > 0:
            if stmt.capex is not None and capex_abs > 0:
                capex_pct = capex_abs / total_deployed
            if stmt.share_buybacks is not None and buyback_abs > 0:
                buyback_pct = buyback_abs / total_deployed
            if stmt.dividends_paid is not None and div_abs > 0:
                div_pct = div_abs / total_deployed

        # ROIC - WACC spread (WACC from config default if not available)
        roic_wacc = None
        if stmt.roic is not None:
            from ..config import settings
            roic_wacc = stmt.roic - settings.analysis.default_wacc

        # Assessment
        assessment_parts: list[str] = []
        if stmt.roic is not None:
            if stmt.roic > 0.15:
                assessment_parts.append("High ROIC indicates strong capital efficiency.")
            elif stmt.roic > 0.08:
                assessment_parts.append("Moderate ROIC; capital efficiency is adequate.")
            else:
                assessment_parts.append("Low ROIC raises questions about reinvestment returns.")

        if roic_wacc is not None:
            if roic_wacc > 0:
                assessment_parts.append(
                    f"ROIC exceeds WACC by {roic_wacc:.1%} — value creation."
                )
            else:
                assessment_parts.append(
                    f"ROIC trails WACC by {abs(roic_wacc):.1%} — value destruction."
                )

        return CapitalAllocation(
            ticker=stmt.period,
            period=stmt.period,
            capex=stmt.capex,
            capex_pct_of_fcf=capex_pct,
            share_buybacks=stmt.share_buybacks,
            buyback_pct_of_fcf=buyback_pct,
            dividends=stmt.dividends_paid,
            dividend_pct_of_fcf=div_pct,
            roic=stmt.roic,
            wacc=settings.analysis.default_wacc if stmt.roic is not None else None,
            roic_minus_wacc=roic_wacc,
            assessment=" ".join(assessment_parts) if assessment_parts else "Insufficient data for assessment.",
        )
