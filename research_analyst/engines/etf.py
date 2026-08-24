"""ETF analysis engine for report subjects that are ETFs.

Responsibilities:
  - Fund overview (description, strategy)
  - Expense ratio
  - AUM/net assets
  - Distribution/yield (current and trailing)
  - Tracking index
  - Top holdings/sectors (if available)
  - Gracefully handles missing fields

Engine mirrors ``dividend.py`` pattern:
  - Input: ETF-specific data (metadata + financials)
  - Output: Structured analysis for report rendering
"""
# Module: research_analyst/engines/etf.py | Version: 0.3.0 | Updated: 2026-06-02

from __future__ import annotations

import logging
from typing import Any

from ..models import (
    Assumption,
    CompanyProfile,
    FinancialStatement,
)

logger = logging.getLogger(__name__)


class ETFEngine:
    """Stateless ETF analysis engine."""

    def analyze(
        self,
        profile: CompanyProfile,
        financials: list[FinancialStatement] | None = None,
    ) -> dict[str, Any]:
        """Analyze ETF-specific data for report rendering.
        
        Args:
            profile: Company/ETF profile with security_type=ETF.
            financials: Financial statements (if available).
            
        Returns:
            Analysis dict with ETF data and assumptions.
        """
        result: dict[str, Any] = {
            "profile": profile,
            "assumptions": [],
            "data_gaps": [],
        }
        
        # Fund overview
        if profile.description:
            result["fund_overview"] = profile.description
        else:
            result["data_gaps"].append("No fund description available.")
        
        # Expense ratio (if present in any financial statement)
        if financials:
            for stmt in financials:
                if hasattr(stmt, "expense_ratio") and stmt.expense_ratio is not None:
                    result["expense_ratio"] = stmt.expense_ratio
                    result["assumptions"].append(
                        Assumption(
                            label="Expense Ratio",
                            value=f"{stmt.expense_ratio:.2%}",
                            source="Latest financial statement",
                        )
                    )
                    break
            else:
                result["data_gaps"].append("Expense ratio unavailable.")
        
        # AUM (if available)
        if profile.market_cap:
            result["aum"] = profile.market_cap
            result["assumptions"].append(
                Assumption(
                    label="Assets Under Management",
                    value=profile.market_cap,
                    source="Market capitalization from profile",
                )
            )
        else:
            result["data_gaps"].append("AUM data unavailable.")
            
        return result