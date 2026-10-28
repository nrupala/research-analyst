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

"""Three-factor DuPont decomposition of return on equity.

  ROE = (NI / Revenue) × (Revenue / AvgAssets) × (AvgAssets / AvgEquity)
      =  net margin  ×  asset turnover   ×  equity multiplier (leverage)

(DuPont Corporation, 1920s; this three-factor form is the standard
textbook decomposition.)

AVERAGING CONVENTION: flow/stock ratios use average balance-sheet
values, (current + prior) / 2. The first period has no prior, so it
uses the current value alone.

Nulls in, nulls out: a period with any missing input yields nulls,
never an exception.

Ported from quant/src/dupont.ts.
"""
# Module: research_analyst/quant_engine/dupont.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

import math
from dataclasses import dataclass

from .guards import div
from .series import Series, StatementSeries


def _at(values: Series, i: int) -> float | None:
    """Read index i of a series; out-of-range becomes None."""
    return values[i] if 0 <= i < len(values) else None


def _avg2(a: float | None, b: float | None) -> float | None:
    """Mean of two scalars; None when either side is missing."""
    return None if a is None or b is None else (a + b) / 2


@dataclass
class DupontComponents:
    """One period of DuPont components; any field may be None."""

    net_margin: float | None
    asset_turnover: float | None
    leverage: float | None
    roe: float | None


@dataclass
class DupontPoint:
    """Fully-computed DuPont point: all four components are real numbers."""

    net_margin: float
    asset_turnover: float
    leverage: float
    roe: float


@dataclass
class DupontRow(DupontComponents):
    """One row of dupont_series: the period label plus its components."""

    period: str = ""


@dataclass
class RoeAttribution:
    """Percentage-point contributions of each DuPont factor to a ROE change."""

    margin_pts: float
    turnover_pts: float
    leverage_pts: float


def dupont_point(
    net_income: float | None,
    revenue: float | None,
    avg_assets: float | None,
    avg_equity: float | None,
) -> DupontPoint | None:
    """Three-factor DuPont decomposition for a single period.

    Formulas: netMargin = netIncome / revenue;
    assetTurnover = revenue / avgAssets;
    leverage = avgAssets / avgEquity;
    roe = netIncome / avgEquity (= the product of the three, algebraically).

    Returns the four components, or None when any input is None, when
    revenue is 0, or when avgAssets / avgEquity are not positive (a
    non-positive equity base makes ROE undefined).
    """
    if (
        net_income is None
        or revenue is None
        or avg_assets is None
        or avg_equity is None
    ):
        return None
    if avg_assets <= 0 or avg_equity <= 0:
        return None
    net_margin = div(net_income, revenue)
    asset_turnover = div(revenue, avg_assets)
    leverage = div(avg_assets, avg_equity)
    roe = div(net_income, avg_equity)
    if (
        net_margin is None
        or asset_turnover is None
        or leverage is None
        or roe is None
    ):
        return None
    return DupontPoint(
        net_margin=net_margin,
        asset_turnover=asset_turnover,
        leverage=leverage,
        roe=roe,
    )


def dupont_series(s: StatementSeries) -> list[DupontRow]:
    """Per-period DuPont decomposition over the whole series (oldest → newest).

    Averages are (current + prior) / 2. The FIRST period has no prior
    period, so it uses the current balance-sheet values alone (not a
    two-period average) — its turnover and leverage are therefore
    point-in-time, not averaged.

    Returns one row per period; a row is all-None when that period's
    inputs are incomplete.
    """
    rows: list[DupontRow] = []
    for i in range(len(s.periods)):
        if i == 0:
            avg_assets = _at(s.total_assets, 0)
            avg_equity = _at(s.total_equity, 0)
        else:
            avg_assets = _avg2(_at(s.total_assets, i), _at(s.total_assets, i - 1))
            avg_equity = _avg2(_at(s.total_equity, i), _at(s.total_equity, i - 1))
        p = dupont_point(_at(s.net_income, i), _at(s.revenue, i), avg_assets, avg_equity)
        period = s.periods[i]
        rows.append(
            DupontRow(
                period=period.period if period is not None else f"period-{i}",
                net_margin=None if p is None else p.net_margin,
                asset_turnover=None if p is None else p.asset_turnover,
                leverage=None if p is None else p.leverage,
                roe=None if p is None else p.roe,
            )
        )
    return rows


def roe_attribution(
    first: DupontComponents, last: DupontComponents
) -> RoeAttribution | None:
    """Logarithmic attribution of a ROE change to its three DuPont factors.

    Formula (per factor): contribution_i =
      ln(component_last / component_first) / ln(roe_last / roe_first)
      × (roe_last − roe_first) × 100
    in percentage points. The three contributions sum to the ROE change
    in percentage points. This is the standard log-mean style
    decomposition for a multiplicative identity (ROE = m × t × l);
    it is exact only when roe equals the product of the three
    components in both periods.

    Returns None when any component or ROE is None, non-positive
    (log of a non-positive number is undefined), or when ROE is unchanged
    (the denominator ln(1) would be zero).
    """
    f_m, l_m = first.net_margin, last.net_margin
    f_t, l_t = first.asset_turnover, last.asset_turnover
    f_l, l_l = first.leverage, last.leverage
    f_r, l_r = first.roe, last.roe
    for v in (f_m, l_m, f_t, l_t, f_l, l_l, f_r, l_r):
        if v is None or v <= 0:
            return None
    assert f_r is not None and l_r is not None  # for type narrowing
    if l_r == f_r:
        return None
    d_roe = l_r - f_r  # decimal, e.g. 0.05
    denom = math.log(l_r / f_r)

    def pts(f: float, last: float) -> float:
        return (math.log(last / f) / denom) * d_roe * 100

    assert f_m is not None and l_m is not None
    assert f_t is not None and l_t is not None
    assert f_l is not None and l_l is not None
    return RoeAttribution(
        margin_pts=pts(f_m, l_m),
        turnover_pts=pts(f_t, l_t),
        leverage_pts=pts(f_l, l_l),
    )
