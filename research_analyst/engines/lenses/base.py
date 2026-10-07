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

"""Lens framework — typed base for the mental-model filtration matrices.

Every lens takes the same typed ``LensInput`` (drawn from existing research
data) and returns a typed ``LensResult``. Lenses are pure computations over
public-domain methodologies, implemented from first principles. Phrasing is
strictly educational and attribution-safe: "based on principles popularized by
X" — never "endorsed by" or trademarked-as-product.
"""
# Module: research_analyst/engines/lenses/base.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

# Attribution phrase every lens carries — the safe-phrasing contract.
ATTRIBUTION = (
    "Calculation model based on principles popularized by {name} "
    "(public-domain methodology); not affiliated with or endorsed by the "
    "originator."
)


class LensSignal(BaseModel):
    """A single lens observation with a directional read."""

    label: str
    value: str
    read: str = Field(..., description='"favor" | "caution" | "neutral"')
    note: str = ""


class LensResult(BaseModel):
    """Typed output of one lens engine."""

    lens: str
    name: str
    summary: str
    signals: list[LensSignal] = Field(default_factory=list)
    raw_values: dict[str, Any] = Field(default_factory=dict)
    # Issue #70: every required input that was missing, named explicitly so the
    # report can say *what* is missing instead of rendering a generic "n/a".
    missing_inputs: list[str] = Field(default_factory=list)
    attribution: str = ""
    educational_only: bool = True


@dataclass
class LensInput:
    """Typed inputs a lens can compute over (all optional, gracefully gapped)."""

    ticker: str
    current_price: float | None = None
    latest: Any = None                 # latest FinancialStatement
    prior: Any = None                  # prior FinancialStatement (trend)
    shares_outstanding: int | None = None
    currency: str | None = None
    analyst: Any = None                # AnalystEstimates
    fundamental: Any = None            # FundamentalData (for competitor context)
    valuation: Any = None              # ValuationRange (scenario context)
    raw: dict[str, Any] = field(default_factory=dict)


def bvps(statement: Any) -> float | None:
    """Book value per share from a financial statement."""
    if not statement or not statement.total_equity or not statement.shares_outstanding:
        return None
    return float(statement.total_equity) / float(statement.shares_outstanding)


def ncav(statement: Any) -> float | None:
    """Net current asset value per share (Graham net-net)."""
    if not statement or not statement.current_assets or not statement.current_liabilities:
        return None
    if not statement.shares_outstanding:
        return None
    return (
        float(statement.current_assets) - float(statement.current_liabilities)
    ) / float(statement.shares_outstanding)


def pct_change(current: float | None, prior: float | None) -> float | None:
    """Year-over-year % change, None when either side is missing."""
    if current is None or prior is None or prior == 0:
        return None
    return (current - prior) / abs(prior)


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1%}"


def _x(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}x"
