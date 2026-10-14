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

"""Tests for the dividend & yield engine (v0.1.1).

Offline, deterministic. Synthetic fixtures only — no network, no yfinance.
Fixtures use geometric dividend growth so growth/streak assertions are robust
regardless of whether the engine treats the latest calendar year as partial.
"""
# Module: tests/test_dividend.py | Version: 0.1.1 | Updated: 2026-06-02

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from research_analyst.engines.dividend import DividendEngine
from research_analyst.models import (
    Competitor,
    DividendAnalysis,
    DividendData,
    DividendPayment,
    FinancialStatement,
    MacroSnapshot,
)


def _history(per_year: dict[int, float]) -> list[DividendPayment]:
    return [DividendPayment(ex_date=date(y, 6, 15), amount=a) for y, a in sorted(per_year.items())]


def _stmt(**kw) -> FinancialStatement:
    base = dict(period="FY2025", period_end_date=date(2025, 12, 31), is_annual=True)
    base.update(kw)
    return FinancialStatement(**base)


# Geometric +8%/yr — growth is exactly 0.08 for every adjacent pair and CAGR window
PAYER_HISTORY = {y: round(1.08 ** (y - 2018), 4) for y in range(2018, 2026)}


def test_payer_full_analysis():
    engine = DividendEngine()
    dd = DividendData(
        ticker="KO",
        current_price=28.0,
        dividend_rate=1.80,
        trailing_dividend_rate=PAYER_HISTORY[2025],
        five_year_avg_yield=2.8,  # yfinance ships this as a percent
        history=_history(PAYER_HISTORY),
        ex_dividend_date=date(2026, 6, 14),
    )
    fin = [
        _stmt(
            net_income=Decimal("10000000000"),
            free_cash_flow=Decimal("12000000000"),
            dividends_paid=Decimal("-3000000000"),
        )
    ]
    macro = MacroSnapshot(as_of_date=date(2026, 6, 1), us_10y_yield=0.043)
    peers = [
        Competitor(ticker="PEP", name="PepsiCo", dividend_yield=0.025),
        Competitor(ticker="MDLZ", name="Mondelez", dividend_yield=0.020),
        Competitor(ticker="KHC", name="Kraft Heinz", dividend_yield=0.030),
    ]
    fundamental = SimpleNamespace(balance_sheet_grade="Strong", revenue_growth_yoy=0.05)

    r = engine.analyze(
        dd, fin, macro=macro, peers=peers, fundamental=fundamental, current_price=28.0
    )

    assert r.pays_dividend is True
    assert r.income_label == "Dividend"
    assert r.current_yield == pytest.approx(1.80 / 28.0, rel=1e-3)
    assert r.trailing_yield == pytest.approx(PAYER_HISTORY[2025] / 28.0, rel=1e-3)
    assert r.five_year_avg_yield == pytest.approx(0.028, rel=1e-3)

    assert r.payout_ratio_eps == pytest.approx(0.30, rel=1e-3)
    assert r.payout_ratio_fcf == pytest.approx(0.25, rel=1e-3)
    assert r.fcf_coverage == pytest.approx(4.0, rel=1e-3)
    assert r.eps_coverage == pytest.approx(10.0 / 3.0, rel=1e-3)

    assert r.dividend_growth_1y == pytest.approx(0.08, rel=2e-2)
    assert r.dividend_growth_3y_cagr == pytest.approx(0.08, rel=2e-2)
    assert r.dividend_growth_5y_cagr == pytest.approx(0.08, rel=2e-2)

    assert r.consecutive_increase_years >= 5  # robust to partial-year handling
    assert r.had_cut is False

    assert r.safety_grade == "Very Safe"
    assert r.safety_score is not None and r.safety_score >= 90

    assert r.peer_median_yield == pytest.approx(0.025, rel=1e-3)
    assert r.yield_vs_peers == "above"
    assert r.us_10y_yield == 0.043
    assert r.yield_vs_treasury_spread == pytest.approx(1.80 / 28.0 - 0.043, rel=1e-3)
    assert r.attractiveness_rating == "Attractive"
    # #68: the spread is stated unambiguously in BOTH percentage points
    # and basis points (spread = 0.0212857 -> 2.13 pp / 213 bps).
    assert "2.13 pp" in r.attractiveness_rationale
    assert "213 bps" in r.attractiveness_rationale
    assert r.ex_dividend_date == date(2026, 6, 14)

    # Round-trips through JSON (API + cache safety)
    assert DividendAnalysis.model_validate(r.model_dump())


def test_low_yield_below_treasury_is_unattractive():
    engine = DividendEngine()
    dd = DividendData(
        ticker="LOWY",
        current_price=100.0,
        dividend_rate=2.00,
        trailing_dividend_rate=2.00,
        history=_history(PAYER_HISTORY),
    )
    fin = [
        _stmt(
            net_income=Decimal("5000000000"),
            free_cash_flow=Decimal("6000000000"),
            dividends_paid=Decimal("-1000000000"),
        )
    ]
    macro = MacroSnapshot(as_of_date=date(2026, 6, 1), us_10y_yield=0.043)
    r = engine.analyze(dd, fin, macro=macro, current_price=100.0)
    # 2.0% yield vs 4.3% risk-free
    assert r.current_yield == pytest.approx(0.02, rel=1e-3)
    assert r.yield_vs_treasury_spread < 0
    assert r.attractiveness_rating == "Unattractive (income)"


def test_yield_trap_screen():
    engine = DividendEngine()
    # High yield but thin coverage + recent cut → should screen as a trap
    hist = {2021: 2.0, 2022: 2.0, 2023: 2.0, 2024: 1.2, 2025: 1.2}  # cut in 2024
    dd = DividendData(
        ticker="TRAP",
        current_price=15.0,
        dividend_rate=1.20,
        trailing_dividend_rate=1.20,
        five_year_avg_yield=4.0,
        history=_history(hist),
    )
    fin = [
        _stmt(
            net_income=Decimal("500000000"),
            free_cash_flow=Decimal("900000000"),
            dividends_paid=Decimal("-1000000000"),
        )
    ]  # FCF coverage 0.9x
    macro = MacroSnapshot(as_of_date=date(2026, 6, 1), us_10y_yield=0.043)
    fundamental = SimpleNamespace(balance_sheet_grade="Weak", revenue_growth_yoy=-0.05)
    r = engine.analyze(dd, fin, macro=macro, fundamental=fundamental, current_price=15.0)
    assert r.pays_dividend is True
    assert r.fcf_coverage is not None and r.fcf_coverage < 1
    assert r.had_cut is True
    assert r.safety_grade in ("At Risk", "Unsafe", "Borderline")
    assert r.attractiveness_rating == "Yield-Trap Risk"


def test_non_payer_buyback_focused():
    engine = DividendEngine()
    dd = DividendData(ticker="GOOGL", current_price=170.0)
    fin = [
        _stmt(
            net_income=Decimal("80000000000"),
            free_cash_flow=Decimal("60000000000"),
            share_buybacks=Decimal("-50000000000"),
        )
    ]
    fundamental = SimpleNamespace(balance_sheet_grade="Strong", revenue_growth_yoy=0.15)
    r = engine.analyze(dd, fin, fundamental=fundamental, current_price=170.0)
    assert r.pays_dividend is False
    assert r.attractiveness_rating == "No Income"
    assert "buyback" in r.no_dividend_context.lower()
    assert r.current_yield is None
    assert DividendAnalysis.model_validate(r.model_dump())


def test_etf_distribution_yield():
    engine = DividendEngine()
    dd = DividendData(ticker="SPY", is_etf=True, current_price=500.0, etf_ttm_yield=0.013)
    r = engine.analyze(dd, [], current_price=500.0)
    assert r.pays_dividend is True
    assert r.is_etf is True
    assert r.income_label == "Distribution"
    assert r.current_yield == pytest.approx(0.013, rel=1e-6)
    assert r.payout_ratio_eps is None  # EPS payout skipped for funds


def test_info_yield_normalization():
    engine = DividendEngine()
    assert engine._normalize_info_yield(2.5) == pytest.approx(0.025)
    assert engine._normalize_info_yield(0.025) == pytest.approx(0.025)
    # Fallback path: percent-form info yield, no rate, no price
    dd = DividendData(
        ticker="XYZ",
        info_dividend_yield=3.0,
        history=_history({2023: 1.0, 2024: 1.0, 2025: 1.0}),
    )
    r = engine.analyze(dd, [], current_price=None)
    assert r.current_yield == pytest.approx(0.03, rel=1e-3)


def test_info_yield_scale_anchored_to_trailing():
    """Percent-vs-fraction disambiguation uses the computed trailing yield.

    Regression (live META, 2026-10-14): yfinance shipped dividendYield as
    0.28 (a percent) while the trailing rate/price gave 0.00275. The old
    magnitude-only heuristic kept 0.28, so the report showed a 28.00%
    yield, a +2278 bps Treasury spread, and an "Attractive" rating.
    """
    engine = DividendEngine()
    # 0.28 as percent (0.28%) sits next to the trailing anchor; as a
    # fraction (28%) it is ~100x away.
    assert engine._normalize_info_yield(0.28, reference=0.00275) == pytest.approx(0.0028)
    # A genuine high yield keeps its scale under the same rule.
    assert engine._normalize_info_yield(0.08, reference=0.08) == pytest.approx(0.08)
    assert engine._normalize_info_yield(8.0, reference=0.08) == pytest.approx(0.08)
    # No reference: legacy magnitude heuristic is unchanged.
    assert engine._normalize_info_yield(0.28) == pytest.approx(0.28)
    assert engine._normalize_info_yield(2.8) == pytest.approx(0.028)


def test_info_yield_fallback_meta_shaped():
    """Engine-level regression for the META live case: dividend_rate
    missing from the provider payload, trailing rate present, info yield
    shipped as a percent. Current yield must land on the trailing scale,
    and the Treasury spread must come out negative (yield below 10Y)."""
    engine = DividendEngine()
    dd = DividendData(
        ticker="META",
        current_price=762.50,
        dividend_rate=None,
        trailing_dividend_rate=2.10,
        info_dividend_yield=0.28,
        history=_history({2024: 2.00, 2025: 2.10}),
    )
    macro = MacroSnapshot(as_of_date=date(2026, 10, 13), us_10y_yield=0.0522)
    r = engine.analyze(dd, [], macro=macro, current_price=762.50)
    assert r.trailing_yield == pytest.approx(2.10 / 762.50, rel=1e-3)
    assert r.current_yield == pytest.approx(0.0028, rel=1e-2)
    assert r.yield_vs_treasury_spread == pytest.approx(0.0028 - 0.0522, abs=1e-3)
    assert r.yield_vs_treasury_spread < 0
    assert r.attractiveness_rating == "Unattractive (income)"


def test_coverage_edge_cases_no_crash():
    engine = DividendEngine()
    dd = DividendData(
        ticker="ZZZ",
        current_price=10.0,
        dividend_rate=0.40,
        trailing_dividend_rate=0.40,
        history=_history({2024: 0.40, 2025: 0.40}),
    )
    fin = [
        _stmt(
            net_income=Decimal("-1000000000"),  # negative earnings
            free_cash_flow=Decimal("0"),  # zero FCF
            dividends_paid=Decimal("-2000000000"),
        )
    ]
    r = engine.analyze(dd, fin, current_price=10.0)
    assert r.pays_dividend is True
    assert r.payout_ratio_eps is None
    assert r.payout_ratio_fcf is None
    assert r.fcf_coverage is None
    assert r.safety_score is not None  # still computed from consistency, no crash


def test_dividend_models_serialize():
    dd = DividendData(
        ticker="KO",
        current_price=60.0,
        dividend_rate=1.80,
        history=[DividendPayment(ex_date=date(2025, 6, 15), amount=0.45)],
    )
    blob = dd.model_dump(mode="json")
    assert DividendData.model_validate(blob).history[0].amount == 0.45
