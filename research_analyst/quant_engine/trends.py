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

"""Module M1: growth, trajectory and per-share analysis.

Pure functions over aligned oldest→newest series. Nulls in, nulls out:
missing data propagates as None, never 0, never NaN. Zero dependencies.

Ported from quant/src/trends.ts.
"""
# Module: research_analyst/quant_engine/trends.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .series import Series

#: Trend direction derived from a log-linear regression slope.
TrendDirection = Literal["up", "down", "flat"]


@dataclass
class LogLinearTrend:
    """Result of a log-linear (exponential) trend fit."""

    #: Continuously-compounded per-period growth rate. For small slopes this
    #: is ≈ the plain growth rate (a slope of 0.095 means ≈10% per period).
    slope: float
    #: Goodness of fit on the log scale, in [0, 1]. 1 for a constant series.
    r_squared: float
    #: "flat" when |slope| < 0.005, else "up"/"down" by sign.
    direction: TrendDirection


@dataclass
class FlatteryResult:
    """Buyback-flattery gap between total and per-share growth."""

    #: (perShareGrowth − totalGrowth) × 100, in percentage points.
    gap_pts: float
    #: Plain-language reading of the gap (see :func:`flattery`).
    interpretation: str


def cagr(first: float | None, last: float | None, periods: float) -> float | None:
    """Compound per-period growth rate: CAGR = (last / first)^(1 / periods) − 1.

    Returns None when either endpoint is missing (None) or non-finite, when
    ``first <= 0`` (a growth rate is undefined off a non-positive base), when
    ``periods <= 0``, or when the result is not a finite real number (e.g. a
    negative ``last`` makes the ratio negative and its fractional power
    undefined on the reals).

    This is the standard geometric-mean growth rate used across investment
    analysis (CFA Institute curriculum; "compound annual growth rate").
    """
    if first is None or last is None:
        return None
    if not math.isfinite(first) or not math.isfinite(last):
        return None
    if not math.isfinite(periods) or periods <= 0:
        return None
    if first <= 0:
        return None
    ratio = last / first
    if ratio < 0:
        # Fractional power of a negative ratio is undefined on the reals
        # (TS Math.pow yields NaN here → null).
        return None
    result = ratio ** (1 / periods) - 1
    return result if math.isfinite(result) else None


def series_cagr(values: Series) -> float | None:
    """CAGR between the first and last non-null values of a series.

    Uses the index distance between those two points as ``periods``, so gaps
    in the middle do not shorten the horizon — a null period is treated as
    missing data, not as zero. Non-finite values are treated as missing.

    Returns None when fewer than two non-null points exist.
    """
    first_idx = -1
    last_idx = -1
    first: float | None = None
    last: float | None = None
    for i, v in enumerate(values):
        if v is not None and math.isfinite(v):
            if first_idx < 0:
                first_idx = i
                first = v
            last_idx = i
            last = v
    if first_idx < 0 or last_idx <= first_idx:
        return None
    return cagr(first, last, last_idx - first_idx)


def yoy_growth(values: Series) -> Series:
    """Period-over-period growth: g[i] = values[i] / values[i-1] − 1.

    Element i is None when either endpoint is missing or non-finite, or when
    the base values[i-1] <= 0. Element 0 is always None. The returned series
    has the same length as the input.
    """
    out: Series = [None] * len(values)
    for i in range(1, len(values)):
        prev = values[i - 1]
        cur = values[i]
        if (
            prev is None
            or cur is None
            or not math.isfinite(prev)
            or not math.isfinite(cur)
            or prev <= 0
        ):
            continue
        g = cur / prev - 1
        out[i] = g if math.isfinite(g) else None
    return out


def log_linear_trend(values: Series) -> LogLinearTrend | None:
    """Exponential trend fit: OLS regression of ln(value) on t = 0..n−1.

    Uses only positive, finite, non-null values; each keeps its original
    series index so gaps do not compress the time axis.

    Formulae (standard OLS, y = ln(value)):
      slope     = (n·Σty − Σt·Σy) / (n·Σt² − (Σt)²)
      intercept = ȳ − slope·t̄
      R²        = 1 − Σ(y − ŷ)² / Σ(y − ȳ)²

    Returns None when fewer than 3 usable points exist. For a constant
    series the R² denominator is 0; by convention it reports 1. R² is
    clamped to [0, 1] against floating-point dust.
    """
    pts: list[tuple[int, float]] = []
    for t, v in enumerate(values):
        if v is not None and math.isfinite(v) and v > 0:
            pts.append((t, math.log(v)))
    n = len(pts)
    if n < 3:
        return None

    sum_t = sum(t for t, _ in pts)
    sum_y = sum(y for _, y in pts)
    sum_tt = sum(t * t for t, _ in pts)
    sum_ty = sum(t * y for t, y in pts)

    denom = n * sum_tt - sum_t * sum_t
    if denom == 0 or not math.isfinite(denom):
        return None

    slope = (n * sum_ty - sum_t * sum_y) / denom
    mean_y = sum_y / n
    intercept = mean_y - slope * (sum_t / n)
    if not math.isfinite(slope) or not math.isfinite(intercept):
        return None

    ss_res = sum((y - (slope * t + intercept)) ** 2 for t, y in pts)
    ss_tot = sum((y - mean_y) ** 2 for _, y in pts)
    r_squared = 1.0 if ss_tot == 0 else 1 - ss_res / ss_tot
    r_squared = min(1.0, max(0.0, r_squared))

    direction: TrendDirection = (
        "flat" if abs(slope) < 0.005 else ("up" if slope > 0 else "down")
    )
    return LogLinearTrend(slope=slope, r_squared=r_squared, direction=direction)


def per_share_series(values: Series, shares: Series) -> Series:
    """Element-wise per-share series: values[i] / shares[i].

    None-safe: None wherever either side is missing or non-finite, or
    shares[i] <= 0. Output length is the longer of the two inputs.
    """
    n = max(len(values), len(shares))
    out: Series = [None] * n
    for i in range(n):
        v = values[i] if i < len(values) else None
        s = shares[i] if i < len(shares) else None
        if (
            v is None
            or s is None
            or not math.isfinite(v)
            or not math.isfinite(s)
            or s <= 0
        ):
            continue
        q = v / s
        out[i] = q if math.isfinite(q) else None
    return out


def margin_series(numerator: Series, revenue: Series) -> Series:
    """Element-wise margin: numerator[i] / revenue[i].

    None-safe: None wherever either side is missing or non-finite, or
    revenue[i] <= 0. Output length is the longer of the two inputs. Keep
    margins as fractions (0.3 = 30%) inside the engine; format at the
    boundary.
    """
    n = max(len(numerator), len(revenue))
    out: Series = [None] * n
    for i in range(n):
        num = numerator[i] if i < len(numerator) else None
        rev = revenue[i] if i < len(revenue) else None
        if (
            num is None
            or rev is None
            or not math.isfinite(num)
            or not math.isfinite(rev)
            or rev <= 0
        ):
            continue
        m = num / rev
        out[i] = m if math.isfinite(m) else None
    return out


def flattery(
    total_growth: float | None, per_share_growth: float | None
) -> FlatteryResult | None:
    """Buyback-flattery gap between total and per-share growth.

    gap_pts = (perShareGrowth − totalGrowth) × 100, in percentage points.

    Interpretation:
    - gap >  1 → per-share growth exceeds total growth — buybacks are
      flattering the per-share number;
    - gap < −1 → per-share growth lags — dilution or share issuance;
    - otherwise → per-share and total growth are aligned.

    Returns None when either input is missing or non-finite.
    """
    if total_growth is None or per_share_growth is None:
        return None
    if not math.isfinite(total_growth) or not math.isfinite(per_share_growth):
        return None
    gap_pts = (per_share_growth - total_growth) * 100
    if not math.isfinite(gap_pts):
        return None
    if gap_pts > 1:
        interpretation = (
            "per-share growth exceeds total growth — buybacks are flattering "
            "the per-share number"
        )
    elif gap_pts < -1:
        interpretation = "per-share growth lags — dilution or share issuance"
    else:
        interpretation = "per-share and total growth are aligned"
    return FlatteryResult(gap_pts=gap_pts, interpretation=interpretation)