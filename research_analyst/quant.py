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

"""Centralized basis-point, percentage-point and ratio arithmetic.

Issue #68: basis-point / percentage-point math was computed ad hoc at call
sites (e.g. a yield spread stored as a fraction was rendered with ``* 100``
while being labelled "bps" — a 100x unit error). Every conversion between
fractions, percents, percentage points and basis points now goes through
this module so the unit of every number is explicit and unit-tested.

Conventions:
- A *fraction* is a number like 0.0123 (= 1.23%).
- A *percent* is a number like 1.23 (= 1.23%).
- A *percentage-point* spread is the difference of two percents (e.g. 1.50%
  minus 1.25% = 0.25 percentage points).
- A *basis point* is 1/100th of a percentage point (0.25 pp = 25 bps).
"""
# Module: research_analyst/quant.py | Version: 0.1.0 | Updated: 2026-09-25

from __future__ import annotations


def to_bps(fraction: float) -> float:
    """Convert a fraction (e.g. 0.0025) to basis points (25.0)."""
    return fraction * 10_000.0


def from_bps(bps: float) -> float:
    """Convert basis points (e.g. 25.0) to a fraction (0.0025)."""
    return bps / 10_000.0


def to_percent(fraction: float) -> float:
    """Convert a fraction (e.g. 0.0123) to a percent number (1.23)."""
    return fraction * 100.0


def from_percent(percent: float) -> float:
    """Convert a percent number (e.g. 1.23) to a fraction (0.0123)."""
    return percent / 100.0


def pp_spread(a_fraction: float, b_fraction: float) -> float:
    """Percentage-point spread between two fractions: (a - b) in pp.

    Example: pp_spread(0.0150, 0.0125) == 0.25 (i.e. 25 bps).
    """
    return (a_fraction - b_fraction) * 100.0


def spread_bps(a_fraction: float, b_fraction: float) -> float:
    """Spread between two fractions expressed in basis points.

    Example: spread_bps(0.0150, 0.0125) == 25.0.
    """
    return (a_fraction - b_fraction) * 10_000.0


def fmt_bps(fraction: float, decimals: int = 0) -> str:
    """Render a fraction as a basis-point string, e.g. '25 bps'."""
    return f"{to_bps(fraction):.{decimals}f} bps"


def fmt_pct(fraction: float, decimals: int = 2) -> str:
    """Render a fraction as a percent string, e.g. '1.23%'."""
    return f"{to_percent(fraction):.{decimals}f}%"


def fmt_pp(fraction: float, decimals: int = 2) -> str:
    """Render a fraction as percentage points, e.g. '0.25 pp'."""
    return f"{to_percent(fraction):.{decimals}f} pp"
