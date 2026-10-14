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

"""Dividend & yield analysis engine (v0.1.1).

Responsibilities:
  - Current (forward) and trailing dividend yield
  - Dividend growth: 1Y, 3Y CAGR, 5Y CAGR from per-share history
  - Payout ratios: dividends / EPS (net income) and dividends / FCF
  - Coverage: EPS coverage and FCF coverage
  - Consistency: consecutive annual increases, cut detection
  - Dividend safety score (0-100) + grade
  - Yield context: vs 10Y Treasury and vs peer median
  - Yield attractiveness rating in the current rate environment
  - Non-payers: explicit "no dividend" with policy context

Design:
  - Input: DividendData (provider) + financials + macro + peers + fundamental
  - Output: DividendAnalysis (pydantic; attached to ReportOutput + rendered)
  - The headline yield is computed here (dividend_rate / price). yfinance info
    yields are inconsistent (fraction vs percent) and used only as a fallback.
  - O(n) over dividend history; never divides by zero; every figure traceable.
"""
# Module: research_analyst/engines/dividend.py | Version: 0.1.1 | Updated: 2026-06-02

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date
from typing import Any

from ..models import (
    Assumption,
    Competitor,
    DividendAnalysis,
    DividendData,
    DividendPayment,
    FinancialStatement,
    MacroSnapshot,
)
from ..quant import fmt_bps

logger = logging.getLogger(__name__)

_GRADE_ORDER = ["Unsafe", "At Risk", "Borderline", "Safe", "Very Safe"]


class DividendEngine:
    """Stateless dividend & yield analysis engine.

    Usage:
        engine = DividendEngine()
        analysis = engine.analyze(
            dividend_data, financials,
            macro=macro_snapshot, peers=peers,
            fundamental=fundamental_analysis,
            current_price=prices.current_price,
        )
    """

    def analyze(
        self,
        dividend_data: DividendData,
        financials: list[FinancialStatement],
        *,
        macro: MacroSnapshot | None = None,
        peers: list[Competitor] | None = None,
        fundamental: Any = None,
        current_price: float | None = None,
    ) -> DividendAnalysis:
        dd = dividend_data
        result = DividendAnalysis(
            ticker=dd.ticker,
            is_etf=dd.is_etf,
            income_label="Distribution" if dd.is_etf else "Dividend",
        )
        result.ex_dividend_date = dd.ex_dividend_date

        price = current_price or dd.current_price
        if not price or price <= 0:
            result.data_gaps.append(
                "Current price unavailable; yields fall back to yfinance info fields."
            )

        # ---- Yields (computed; stored as fractions) ----
        if price and price > 0:
            if dd.dividend_rate:
                result.annual_dividend_rate = dd.dividend_rate
                result.current_yield = dd.dividend_rate / price
            if dd.trailing_dividend_rate:
                result.trailing_yield = dd.trailing_dividend_rate / price

        # ETF distribution yield is already a fraction
        if dd.is_etf and dd.etf_ttm_yield:
            result.current_yield = result.current_yield or dd.etf_ttm_yield
            result.trailing_yield = result.trailing_yield or dd.etf_ttm_yield

        # Fallback to normalized info yield when nothing else is available.
        # The computed trailing yield anchors the scale: yfinance ships the
        # info yield as a fraction for some tickers and as a percent for
        # others, and magnitude alone cannot tell 0.28%-as-percent from
        # 28%-as-fraction (live META regression: current_yield read 0.28,
        # a 100x error that poisoned the Treasury spread and the Dalio lens).
        if result.current_yield is None and dd.info_dividend_yield is not None:
            result.current_yield = self._normalize_info_yield(
                dd.info_dividend_yield, reference=result.trailing_yield
            )
        if result.trailing_yield is None and result.current_yield is not None:
            result.trailing_yield = result.current_yield

        # 5Y average yield — yfinance reports this one as a percent
        if dd.five_year_avg_yield is not None:
            result.five_year_avg_yield = dd.five_year_avg_yield / 100.0

        # ---- Annual DPS series ----
        annual = self._annual_dividends(dd.history)
        result.annual_dividends = {str(y): round(v, 6) for y, v in annual.items()}
        result.paying_years = sum(1 for v in annual.values() if v > 0)

        # ---- Does it pay? ----
        result.pays_dividend = bool(
            dd.dividend_rate
            or dd.trailing_dividend_rate
            or result.current_yield
            or dd.etf_ttm_yield
            or annual
        )

        if not result.pays_dividend:
            result.no_dividend_context = self._no_dividend_context(financials, fundamental)
            result.attractiveness_rating = "No Income"
            result.assumptions.append(
                Assumption(
                    label="Dividend Policy",
                    value="No dividend currently paid",
                    source="yfinance dividend history / info",
                )
            )
            return result

        self._compute_growth(annual, result)
        self._compute_payout_coverage(financials, result)
        self._compute_consistency(annual, result)
        self._compute_safety(result, fundamental)
        self._compute_yield_context(result, macro, peers)
        self._compute_attractiveness(result)
        self._add_assumptions(dd, price, result)

        return result

    # ------------------------------------------------------------------
    # Yield helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_info_yield(v: float, reference: float | None = None) -> float:
        """yfinance dividendYield ships as a fraction (0.025) or percent (2.5).

        Magnitude alone cannot disambiguate small yields: 0.28 may be a
        0.28% yield shipped as a percent, or a 28% yield shipped as a
        fraction. When a computed trailing yield is available it anchors
        the scale — choose the reading (v or v/100) closer to it in ratio
        terms. The trailing yield is computed from actual payments and
        price, so it is the trustworthy scale reference. Without a
        reference, values > 1 are treated as percent and divided by 100.
        """
        if reference is not None and reference > 0 and v > 0:
            as_fraction = v
            as_percent = v / 100.0
            dist_fraction = abs(math.log(as_fraction / reference))
            dist_percent = abs(math.log(as_percent / reference))
            return as_percent if dist_percent < dist_fraction else as_fraction
        return v / 100.0 if v > 1.0 else v

    @staticmethod
    def _annual_dividends(history: list[DividendPayment]) -> dict[int, float]:
        """Sum per-share dividends by calendar year (chronological)."""
        annual: dict[int, float] = defaultdict(float)
        for p in history:
            annual[p.ex_date.year] += p.amount
        return dict(sorted(annual.items()))

    @staticmethod
    def _complete_years(annual: dict[int, float]) -> list[tuple[int, float]]:
        """Annual series excluding the in-progress current year (partial)."""
        items = sorted(annual.items())
        if not items:
            return []
        current_year = date.today().year
        if items[-1][0] >= current_year and len(items) > 1:
            items = [it for it in items if it[0] < current_year]
        return items

    # ------------------------------------------------------------------
    # Growth
    # ------------------------------------------------------------------

    def _compute_growth(self, annual: dict[int, float], result: DividendAnalysis) -> None:
        items = self._complete_years(annual)
        if len(items) < 2:
            result.data_gaps.append("Insufficient complete dividend years for growth rates.")
            return
        vals = {y: v for y, v in items}
        latest_year = items[-1][0]
        latest = vals[latest_year]

        prev = vals.get(latest_year - 1)
        if prev and prev > 0:
            result.dividend_growth_1y = (latest - prev) / prev

        base3 = vals.get(latest_year - 3)
        if base3 and base3 > 0 and latest > 0:
            result.dividend_growth_3y_cagr = (latest / base3) ** (1 / 3) - 1

        base5 = vals.get(latest_year - 5)
        if base5 and base5 > 0 and latest > 0:
            result.dividend_growth_5y_cagr = (latest / base5) ** (1 / 5) - 1

    # ------------------------------------------------------------------
    # Payout & coverage
    # ------------------------------------------------------------------

    def _compute_payout_coverage(
        self, financials: list[FinancialStatement], result: DividendAnalysis
    ) -> None:
        """Payout & coverage over a trailing window (up to 3 fiscal years).

        Summing dividends and earnings/FCF across recent years smooths one-off
        FCF dips (a single year of heavy working-capital swing or a legal/tax
        payment) that would otherwise mislabel a durable payer as unsafe.
        """
        stmts = self._recent_dividend_statements(financials, max_years=3)
        if not stmts:
            result.data_gaps.append(
                "No financials with dividends paid; payout/coverage unavailable."
            )
            return

        div_e = ni_sum = 0.0
        div_f = fcf_sum = 0.0
        n_e = n_f = 0
        for s in stmts:
            if s.dividends_paid is None:
                continue
            d = abs(float(s.dividends_paid))
            if d <= 0:
                continue
            if s.net_income is not None:
                div_e += d
                ni_sum += float(s.net_income)
                n_e += 1
            if s.free_cash_flow is not None:
                div_f += d
                fcf_sum += float(s.free_cash_flow)
                n_f += 1

        if n_e and ni_sum > 0:
            result.payout_ratio_eps = div_e / ni_sum
            result.eps_coverage = ni_sum / div_e
        elif n_e and ni_sum <= 0:
            result.data_gaps.append(
                "Net income non-positive over window; EPS payout not meaningful."
            )

        if n_f and fcf_sum > 0:
            result.payout_ratio_fcf = div_f / fcf_sum
            result.fcf_coverage = fcf_sum / div_f
        elif n_f and fcf_sum <= 0:
            result.data_gaps.append(
                "Free cash flow non-positive over window; FCF payout/coverage not meaningful."
            )

        if not n_e and not n_f:
            result.data_gaps.append(
                "Dividends paid present but no matching earnings/FCF; payout/coverage unavailable."
            )

    @staticmethod
    def _recent_dividend_statements(
        financials: list[FinancialStatement], max_years: int = 3
    ) -> list[FinancialStatement]:
        if not financials:
            return []
        ordered = sorted(financials, key=lambda f: f.period_end_date or date.min, reverse=True)
        paying = [f for f in ordered if f.dividends_paid]
        return paying[:max_years] if paying else ordered[:1]

    # ------------------------------------------------------------------
    # Consistency
    # ------------------------------------------------------------------

    def _compute_consistency(self, annual: dict[int, float], result: DividendAnalysis) -> None:
        items = self._complete_years(annual)
        if len(items) < 2:
            return
        years = [y for y, _ in items]
        vals = [v for _, v in items]

        # Consecutive YoY increases ending at the most recent complete year
        streak = 0
        for i in range(len(vals) - 1, 0, -1):
            if vals[i] > vals[i - 1] * 1.001:  # 0.1% tolerance
                streak += 1
            else:
                break
        result.consecutive_increase_years = streak

        # Cut detection within a recent lookback window — keeps ancient
        # split-adjustment noise from flagging long-standing dividend raisers.
        latest_year = years[-1]
        lookback_start = latest_year - 15
        last_cut_idx = None
        for i in range(1, len(vals)):
            if years[i] < lookback_start:
                continue
            if vals[i] < vals[i - 1] * 0.999:
                last_cut_idx = i
        if last_cut_idx is not None:
            result.had_cut = True
            result.years_since_cut = latest_year - years[last_cut_idx]

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    def _compute_safety(self, result: DividendAnalysis, fundamental: Any) -> None:
        earned = 0.0
        possible = 0.0

        fc = result.fcf_coverage
        if fc is not None:
            possible += 40
            if fc >= 3:
                earned += 40
            elif fc >= 2:
                earned += 32
            elif fc >= 1.5:
                earned += 24
            elif fc >= 1:
                earned += 14
            else:
                earned += 4

        pe = result.payout_ratio_eps
        if pe is not None and not result.is_etf:
            possible += 30
            if pe <= 0.4:
                earned += 30
            elif pe <= 0.6:
                earned += 24
            elif pe <= 0.75:
                earned += 16
            elif pe <= 1.0:
                earned += 8
            else:
                earned += 2

        # Consistency always contributes
        possible += 20
        if result.had_cut and result.years_since_cut is not None and result.years_since_cut <= 2:
            earned += 2
        elif result.consecutive_increase_years >= 10:
            earned += 20
        elif result.consecutive_increase_years >= 5:
            earned += 15
        elif result.consecutive_increase_years >= 1:
            earned += 10
        elif not result.had_cut:
            earned += 8  # flat but uninterrupted
        else:
            earned += 5

        grade = getattr(fundamental, "balance_sheet_grade", "") if fundamental else ""
        if grade:
            possible += 10
            earned += {"Strong": 10, "Adequate": 6, "Weak": 2}.get(grade, 5)

        if possible <= 0:
            result.data_gaps.append("Insufficient data to compute a dividend safety score.")
            return

        score = round(earned / possible * 100, 1)
        result.safety_score = score
        grade_label = self._safety_grade(score)

        # Hard overrides — coverage/cut realities cap the grade
        if result.fcf_coverage is not None and result.fcf_coverage < 1:
            grade_label = self._cap_grade(grade_label, "At Risk")
        if (
            result.payout_ratio_eps is not None
            and result.payout_ratio_eps > 1
            and not result.is_etf
        ):
            grade_label = self._cap_grade(grade_label, "At Risk")
        if result.had_cut and result.years_since_cut is not None and result.years_since_cut <= 1:
            grade_label = self._cap_grade(grade_label, "Borderline")
        result.safety_grade = grade_label

    @staticmethod
    def _safety_grade(score: float) -> str:
        if score >= 80:
            return "Very Safe"
        if score >= 65:
            return "Safe"
        if score >= 50:
            return "Borderline"
        if score >= 35:
            return "At Risk"
        return "Unsafe"

    @staticmethod
    def _cap_grade(current: str, ceiling: str) -> str:
        if current not in _GRADE_ORDER or ceiling not in _GRADE_ORDER:
            return current
        return ceiling if _GRADE_ORDER.index(current) > _GRADE_ORDER.index(ceiling) else current

    # ------------------------------------------------------------------
    # Yield context (Treasury + peers)
    # ------------------------------------------------------------------

    def _compute_yield_context(
        self,
        result: DividendAnalysis,
        macro: MacroSnapshot | None,
        peers: list[Competitor] | None,
    ) -> None:
        ten_y = getattr(macro, "us_10y_yield", None) if macro else None
        if ten_y is not None:
            result.us_10y_yield = ten_y
            if result.current_yield is not None:
                result.yield_vs_treasury_spread = result.current_yield - ten_y

        if peers:
            peer_yields = sorted(
                p.dividend_yield
                for p in peers
                if p.dividend_yield is not None and p.dividend_yield > 0
            )
            if peer_yields:
                n = len(peer_yields)
                mid = n // 2
                median = (
                    peer_yields[mid] if n % 2 else (peer_yields[mid - 1] + peer_yields[mid]) / 2
                )
                result.peer_median_yield = median
                if result.current_yield is not None:
                    diff = result.current_yield - median
                    if abs(diff) <= 0.005:
                        result.yield_vs_peers = "in line"
                    else:
                        result.yield_vs_peers = "above" if diff > 0 else "below"

    # ------------------------------------------------------------------
    # Attractiveness
    # ------------------------------------------------------------------

    def _compute_attractiveness(self, result: DividendAnalysis) -> None:
        cy = result.current_yield
        if cy is None:
            result.attractiveness_rating = "Unrated"
            result.attractiveness_rationale = "Current yield could not be computed."
            return

        spread = result.yield_vs_treasury_spread
        weak_safety = result.safety_grade in ("At Risk", "Unsafe")
        strong_safety = result.safety_grade in ("Safe", "Very Safe")
        above_own_avg = (
            result.five_year_avg_yield is not None and cy > result.five_year_avg_yield * 1.1
        )

        # Yield-trap screen: elevated yield + weak coverage
        if weak_safety and (above_own_avg or (spread is not None and spread > 0.01)):
            result.attractiveness_rating = "Yield-Trap Risk"
            avg_txt = (
                f" (vs 5Y avg {result.five_year_avg_yield:.2%})"
                if result.five_year_avg_yield is not None
                else ""
            )
            result.attractiveness_rationale = (
                f"Yield of {cy:.2%} screens high{avg_txt} but dividend safety is "
                f"{result.safety_grade or 'weak'} — an elevated yield may reflect risk, not value."
            )
            return

        if spread is not None:
            if spread <= 0:
                tnote = f" ({result.us_10y_yield:.2%})" if result.us_10y_yield is not None else ""
                result.attractiveness_rating = "Unattractive (income)"
                result.attractiveness_rationale = (
                    f"Yield of {cy:.2%} is below the 10Y Treasury{tnote}; income investors "
                    "are not compensated above the risk-free rate."
                )
                return
            if spread >= 0.015 and strong_safety:
                tnote = f" ({result.us_10y_yield:.2%})" if result.us_10y_yield is not None else ""
                result.attractiveness_rating = "Attractive"
                result.attractiveness_rationale = (
                    f"Yield of {cy:.2%} exceeds the 10Y Treasury{tnote} by {fmt_bps(spread)} "
                    f"with {result.safety_grade} coverage."
                )
                return

        result.attractiveness_rating = "Fairly Valued"
        bits = [f"yield {cy:.2%}"]
        if result.us_10y_yield is not None:
            bits.append(f"10Y {result.us_10y_yield:.2%}")
        if result.five_year_avg_yield is not None:
            bits.append(f"5Y avg {result.five_year_avg_yield:.2%}")
        result.attractiveness_rationale = (
            "; ".join(bits) + f"; safety {result.safety_grade or 'n/a'}."
        )

    # ------------------------------------------------------------------
    # Non-payers
    # ------------------------------------------------------------------

    @staticmethod
    def _no_dividend_context(financials: list[FinancialStatement], fundamental: Any) -> str:
        latest = None
        if financials:
            latest = sorted(financials, key=lambda f: f.period_end_date or date.min, reverse=True)[
                0
            ]
        buybacks = bool(latest and latest.share_buybacks and abs(float(latest.share_buybacks)) > 0)
        rev_growth = getattr(fundamental, "revenue_growth_yoy", None) if fundamental else None

        if buybacks:
            return (
                "Capital is returned via share buybacks rather than dividends; shareholder "
                "yield comes from repurchases."
            )
        if rev_growth is not None and rev_growth > 0.12:
            return (
                f"Earnings are reinvested for growth (revenue +{rev_growth:.0%} YoY) rather "
                "than distributed."
            )
        return (
            "No dividend is currently paid; earnings are retained/reinvested. Total return "
            "depends on capital appreciation."
        )

    # ------------------------------------------------------------------
    # Traceability
    # ------------------------------------------------------------------

    def _add_assumptions(
        self, dd: DividendData, price: float | None, result: DividendAnalysis
    ) -> None:
        if result.current_yield is not None and price:
            basis = "forward dividend rate / price" if dd.dividend_rate else "trailing rate / price"
            result.assumptions.append(
                Assumption(
                    label="Dividend Yield",
                    value=f"{result.current_yield:.2%}",
                    source=f"Computed: {basis} (price ${price:.2f})",
                    confidence="High",
                )
            )
        if result.payout_ratio_fcf is not None:
            result.assumptions.append(
                Assumption(
                    label="FCF Payout Ratio",
                    value=f"{result.payout_ratio_fcf:.0%}",
                    source="Dividends paid / free cash flow, trailing up to 3 fiscal years",
                )
            )
        if result.safety_score is not None:
            result.assumptions.append(
                Assumption(
                    label="Dividend Safety Score",
                    value=f"{result.safety_score:.0f}/100 ({result.safety_grade})",
                    source=(
                        "Blend of FCF coverage, EPS payout, increase streak, balance-sheet "
                        "grade"
                    ),
                    note="Heuristic, scaled to available inputs.",
                )
            )
        if dd.history:
            result.assumptions.append(
                Assumption(
                    label="Dividend History",
                    value=f"{len(dd.history)} payments across {result.paying_years} years",
                    source="yfinance dividend history",
                    note="Special/one-time dividends may distort single-year growth.",
                )
            )
