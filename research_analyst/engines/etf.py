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

"""ETF analysis engine - ETF-as-subject (Slice B).

Slice B-A surfaced fund overview + AUM from profile fields only. Slice B-B adds
a real ETF-metadata source (ETFMetadata from the market-data provider):
expense ratio, distribution yield, AUM, tracking index / category, fund family,
top holdings and sector weights. Every field degrades to an explicit data gap
when the source does not supply it. Pure and stateless, mirroring the dividend
engine contract; analyze() is backward-compatible — called without metadata it
falls back to the Slice B-A profile-only surface.
"""
# Module: research_analyst/engines/etf.py | Version: 0.3.1 | Updated: 2026-08-24

from __future__ import annotations

import logging
from typing import Any

from ..models import Assumption, CompanyProfile, ETFMetadata

logger = logging.getLogger(__name__)

_DEFERRED_GAP = (
    "Expense ratio, distribution yield, tracking index and top holdings "
    "pending ETF-metadata integration (Slice B-B)."
)


class ETFEngine:
    """Stateless ETF-as-subject analysis engine."""

    def analyze(
        self, profile: CompanyProfile, metadata: ETFMetadata | None = None
    ) -> dict[str, Any]:
        """Analyze ETF-subject data.

        With ``metadata`` (Slice B-B) the engine surfaces real expense ratio,
        distribution yield, AUM, tracking index, fund family, top holdings and
        sector weights. Without it (Slice B-A fallback) it surfaces fund
        overview + an AUM proxy from the profile only.

        Returns a dict with: fund_overview, expense_ratio, distribution_yield,
        aum, tracking_index, fund_family, top_holdings, sector_weights,
        assumptions (list[Assumption]) and data_gaps (list[str]).
        """
        result: dict[str, Any] = {
            "fund_overview": None,
            "expense_ratio": None,
            "distribution_yield": None,
            "aum": None,
            "tracking_index": "",
            "fund_family": "",
            "top_holdings": [],
            "sector_weights": {},
            "assumptions": [],
            "data_gaps": [],
        }

        # Fund overview always comes from the profile description.
        if profile.description:
            result["fund_overview"] = profile.description
        else:
            result["data_gaps"].append("ETF strategy description unavailable.")

        if metadata is None:
            # Slice B-A fallback: profile-only surface.
            aum = profile.market_cap
            if aum is not None:
                result["aum"] = aum
                result["assumptions"].append(
                    Assumption(
                        label="Assets Under Management",
                        value=str(aum),
                        source="market_cap from security profile (AUM proxy)",
                    )
                )
            else:
                result["data_gaps"].append("Assets under management unavailable.")
            result["data_gaps"].append(_DEFERRED_GAP)
            return result

        # Slice B-B: real ETF metadata.
        result["expense_ratio"] = metadata.expense_ratio
        result["distribution_yield"] = metadata.distribution_yield
        result["tracking_index"] = metadata.tracking_index
        result["fund_family"] = metadata.fund_family
        result["top_holdings"] = [
            {"symbol": h.symbol, "name": h.name, "weight": h.weight}
            for h in metadata.top_holdings
        ]
        result["sector_weights"] = dict(metadata.sector_weights)

        # AUM: prefer real net assets, fall back to profile market_cap proxy.
        if metadata.aum is not None:
            result["aum"] = metadata.aum
            result["assumptions"].append(
                Assumption(
                    label="Assets Under Management",
                    value=str(metadata.aum),
                    source="yfinance ETF metadata (totalAssets / netAssets)",
                )
            )
        elif profile.market_cap is not None:
            result["aum"] = profile.market_cap
            result["assumptions"].append(
                Assumption(
                    label="Assets Under Management",
                    value=str(profile.market_cap),
                    source="market_cap from security profile (AUM proxy)",
                )
            )
        else:
            result["data_gaps"].append("Assets under management unavailable.")

        if metadata.expense_ratio is not None:
            result["assumptions"].append(
                Assumption(
                    label="Expense Ratio",
                    value=str(metadata.expense_ratio),
                    source="yfinance ETF metadata",
                )
            )
        if metadata.distribution_yield is not None:
            result["assumptions"].append(
                Assumption(
                    label="Distribution Yield",
                    value=str(metadata.distribution_yield),
                    source="yfinance ETF metadata",
                )
            )

        # Carry forward the provider's explicit per-field data gaps.
        result["data_gaps"].extend(metadata.data_gaps)
        return result
