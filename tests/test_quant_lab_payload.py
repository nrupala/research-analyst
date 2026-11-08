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

"""Quant Lab Phase 1 payload completions (spec §4 / §8.3).

P1-B1: per-period margin / YoY series in ``trends`` — aligned
element-for-element with ``periods[]`` and with the scalar latest values.
P1-B2: DCF sensitivity grid in ``valuation`` — base cell equals the direct
engine model evaluation at the same inputs; unevaluable cells stay null.
Both additions are additive: every pre-existing payload key is unchanged.
"""
# Module: tests/test_quant_lab_payload.py | Version: 0.1.0 | Updated: 2026-11-03

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from research_analyst.api_models import QuantTrendsPayload, QuantValuationPayload
from research_analyst.models import FinancialStatement
from research_analyst.quant_engine import trends as trends_engine
from research_analyst.quant_engine import valuation as valuation_engine
from research_analyst.quant_engine.adapter import from_financial_statements
from research_analyst.quant_engine.guards import last_value
from research_analyst.reports.quant_section import compute_quant_results


def _stmt(year: int, **kw) -> FinancialStatement:
    base = dict(
        period=f"FY{year}",
        period_end_date=date(year, 12, 31),
        revenue=Decimal("1000"),
        gross_profit=Decimal("400"),
        net_income=Decimal("100"),
        total_assets=Decimal("2000"),
        total_equity=Decimal("1200"),
        operating_cash_flow=Decimal("150"),
        free_cash_flow=Decimal("90"),
        eps_diluted=2.0,
        shares_outstanding=500,
    )
    base.update(kw)
    return FinancialStatement(**base)


def _series():
    """Four periods, rising revenue/margins; FY2022 gross profit missing."""
    stmts = [
        _stmt(2021, revenue=Decimal("800"), gross_profit=Decimal("280"), net_income=Decimal("64")),
        _stmt(2022, revenue=Decimal("900"), gross_profit=None, net_income=Decimal("81")),
        _stmt(
            2023, revenue=Decimal("1000"), gross_profit=Decimal("400"), net_income=Decimal("100")
        ),
        _stmt(
            2024, revenue=Decimal("1200"), gross_profit=Decimal("540"), net_income=Decimal("156")
        ),
    ]
    return from_financial_statements(stmts, "TST")


_MARKET = {
    "enterprise_value": 20000.0,
    "discount_rate": 0.09,
    "net_debt": 1000.0,
    "currency": "USD",
}


# ---------------------------------------------------------------------------
# P1-B1 — per-period series
# ---------------------------------------------------------------------------


def test_p1b1_series_align_with_periods_and_engine():
    s = _series()
    r = compute_quant_results(s, {})
    n = len(s.periods)
    t = r["trends"]
    assert len(t["margin_series"]["gross"]) == n
    assert len(t["margin_series"]["net"]) == n
    assert len(t["yoy_series"]["revenue"]) == n
    # Element-for-element the engine's own output — no re-computation drift.
    assert t["margin_series"]["gross"] == trends_engine.margin_series(s.gross_profit, s.revenue)
    assert t["margin_series"]["net"] == trends_engine.margin_series(s.net_income, s.revenue)
    assert t["yoy_series"]["revenue"] == trends_engine.yoy_growth(s.revenue)


def test_p1b1_series_agree_with_scalar_latest_values():
    s = _series()
    t = compute_quant_results(s, {})["trends"]
    assert last_value(t["margin_series"]["gross"]) == t["gross_margin_latest"]
    assert last_value(t["margin_series"]["net"]) == t["net_margin_latest"]
    assert last_value(t["yoy_series"]["revenue"]) == t["yoy_revenue_growth_latest"]
    # Hand-checked values for the fixture's final period.
    assert t["gross_margin_latest"] == pytest.approx(540 / 1200)
    assert t["yoy_series"]["revenue"][-1] == pytest.approx(1200 / 1000 - 1)


def test_p1b1_nulls_preserved_never_zero_filled():
    s = _series()
    t = compute_quant_results(s, {})["trends"]
    # FY2022 gross profit is missing: the margin is null there, real elsewhere.
    assert t["margin_series"]["gross"][1] is None
    assert t["margin_series"]["gross"][0] == pytest.approx(280 / 800)
    assert t["margin_series"]["gross"][2] == pytest.approx(400 / 1000)
    # YoY element 0 is null by engine construction.
    assert t["yoy_series"]["revenue"][0] is None
    assert all(v is None or isinstance(v, float) for v in t["margin_series"]["net"])


# ---------------------------------------------------------------------------
# P1-B2 — sensitivity grid
# ---------------------------------------------------------------------------


def test_p1b2_grid_shape_labels_and_base():
    s = _series()
    v = compute_quant_results(s, dict(_MARKET))["valuation"]
    grid = v["sensitivity"]
    assert grid is not None
    assert grid["rows"]["label"] == "discount_rate"
    assert grid["cols"]["label"] == "perpetual_growth"
    assert grid["base"]["discount_rate"] == 0.09
    assert grid["base"]["perpetual_growth"] == 0.025
    assert grid["base"]["explicit_growth"] == v["implied_explicit_stage_growth"]
    assert len(grid["values"]) == len(grid["rows"]["values"]) == 9
    assert all(len(row) == len(grid["cols"]["values"]) == 5 for row in grid["values"])
    assert 0.09 in grid["rows"]["values"]
    assert 0.025 in grid["cols"]["values"]


def test_p1b2_base_cell_equals_direct_model_evaluation():
    s = _series()
    v = compute_quant_results(s, dict(_MARKET))["valuation"]
    grid = v["sensitivity"]
    i = grid["rows"]["values"].index(grid["base"]["discount_rate"])
    j = grid["cols"]["values"].index(grid["base"]["perpetual_growth"])
    fcf_last = last_value(s.free_cash_flow)
    direct = valuation_engine.dcf(
        fcf_last, [grid["base"]["explicit_growth"]] * 5, 0.09, 0.025
    )
    assert direct is not None
    expected = (direct.enterprise_value - _MARKET["net_debt"]) / 500
    assert grid["values"][i][j] == pytest.approx(expected)


def test_p1b2_unevaluable_cells_stay_null():
    # A low base discount rate pushes some grid rows at/below the highest
    # perpetual-growth column — the Gordon series diverges there, so those
    # cells must be null, never interpolated or clamped.
    s = _series()
    market = dict(_MARKET, discount_rate=0.04)
    grid = compute_quant_results(s, market)["valuation"]["sensitivity"]
    assert grid is not None
    flat = [c for row in grid["values"] for c in row]
    assert any(c is None for c in flat)
    assert any(c is not None for c in flat)
    # The nulls are exactly the r <= g corner.
    for rv, row in zip(grid["rows"]["values"], grid["values"], strict=True):
        for gv, cell in zip(grid["cols"]["values"], row, strict=True):
            assert (cell is None) == (rv <= gv)


def test_p1b2_absent_without_discount_rate_and_named_when_inputs_missing():
    s = _series()
    v = compute_quant_results(s, {})["valuation"]
    assert v["sensitivity"] is None
    # Discount rate present but no net debt in the market snapshot: the grid
    # is absent and the gap is named in missing_inputs, not silently dropped.
    market = {"enterprise_value": 20000.0, "discount_rate": 0.09, "currency": "USD"}
    r = compute_quant_results(s, market)
    assert r["valuation"]["sensitivity"] is None
    assert any(m.startswith("sensitivity_grid") for m in r["missing_inputs"])


# ---------------------------------------------------------------------------
# Additivity — pre-existing keys unchanged; API models stay compatible
# ---------------------------------------------------------------------------


def test_additions_leave_preexisting_keys_unchanged():
    s = _series()
    r = compute_quant_results(s, dict(_MARKET))
    assert set(r["trends"]) == {
        "revenue_cagr",
        "eps_cagr",
        "fcf_cagr",
        "yoy_revenue_growth_latest",
        "gross_margin_latest",
        "net_margin_latest",
        "margin_series",
        "yoy_series",
    }
    assert set(r["valuation"]) == {
        "graham_number",
        "lynch_fair_value",
        "implied_explicit_stage_growth",
        "implied_perpetual_growth",
        "discount_rate_used",
        "sensitivity",
    }
    # Scalars carry the same values the engine computes directly.
    assert r["trends"]["revenue_cagr"] == trends_engine.series_cagr(s.revenue)
    assert r["trends"]["gross_margin_latest"] == pytest.approx(0.45)


def test_api_models_carry_new_fields_and_default_for_old_payloads():
    t = QuantTrendsPayload(
        revenue_cagr=0.1,
        margin_series={"gross": [0.35, None], "net": [0.08, 0.09]},
        yoy_series={"revenue": [None, 0.125]},
    )
    assert t.margin_series.gross == [0.35, None]
    assert t.yoy_series.revenue == [None, 0.125]
    # An old payload (no series keys) still validates, with empty series.
    old = QuantTrendsPayload(revenue_cagr=0.1)
    assert old.margin_series.gross == [] and old.yoy_series.revenue == []

    v = QuantValuationPayload(
        discount_rate_used=0.09,
        sensitivity={
            "rows": {"label": "discount_rate", "values": [0.09]},
            "cols": {"label": "perpetual_growth", "values": [0.025]},
            "values": [[123.45]],
            "base": {"discount_rate": 0.09, "perpetual_growth": 0.025, "explicit_growth": 0.05},
        },
    )
    assert v.sensitivity is not None
    assert v.sensitivity.values == [[123.45]]
    assert QuantValuationPayload().sensitivity is None
