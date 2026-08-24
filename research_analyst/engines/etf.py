"""ETF analysis engine - ETF-as-subject (Slice B, Option A).

Produces the ETF-subject analysis surface from fields the security profile
already carries: fund overview (description) and assets under management
(market_cap as an AUM proxy). Expense ratio, distribution yield, tracking
index and holdings are deferred to Slice B-B, which will add an ETF-metadata
source; this engine records them as explicit data gaps. Pure and stateless,
mirroring the dividend engine contract.
"""
# Module: research_analyst/engines/etf.py | Version: 0.3.0 | Updated: 2026-08-24

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from ..models import Assumption, CompanyProfile

logger = logging.getLogger(__name__)

_DEFERRED_GAP = (
    "Expense ratio, distribution yield, tracking index and top holdings "
    "pending ETF-metadata integration (Slice B-B)."
)


class ETFEngine:
    """Stateless ETF-as-subject analysis engine (Option A)."""

    def analyze(self, profile: CompanyProfile) -> dict[str, Any]:
        """Analyze the ETF-subject data available on the profile.

        Returns a dict with: fund_overview (str|None), aum (Decimal|None),
        assumptions (list[Assumption]) and data_gaps (list[str]).
        """
        result: dict[str, Any] = {
            "fund_overview": None,
            "aum": None,
            "assumptions": [],
            "data_gaps": [],
        }

        if profile.description:
            result["fund_overview"] = profile.description
        else:
            result["data_gaps"].append("ETF strategy description unavailable.")

        aum: Decimal | None = profile.market_cap
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
