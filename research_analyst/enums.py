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

"""Enumerations for report types, risk categories, and analysis domains."""
# Module: research_analyst/enums.py | Version: 0.1.0 | Updated: 2026-05-15

from enum import StrEnum


class ReportType(StrEnum):
    """Supported report modes — exactly three, non-negotiable."""

    LONG_TERM = "long_term"
    TACTICAL = "tactical"
    COMPREHENSIVE = "comprehensive"

    @classmethod
    def from_user_input(cls, raw: str | None) -> list["ReportType"]:
        """Parse user input into report type(s).

        Rules:
          - None / empty → [COMPREHENSIVE]
          - "all" / "full package" / "institutional" / "complete" → all three
          - Explicit name → that single type
        """
        if not raw:
            return [cls.COMPREHENSIVE]
        normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in ("all", "full_package", "institutional", "complete"):
            return [cls.LONG_TERM, cls.TACTICAL, cls.COMPREHENSIVE]
        for member in cls:
            if normalized == member.value or normalized in member.value:
                return [member]
        return [cls.COMPREHENSIVE]


class RiskCategory(StrEnum):
    """Risk classification axis."""

    OPERATIONAL = "operational"
    MACRO = "macro"
    REGULATORY = "regulatory"
    COMPETITIVE = "competitive"
    FINANCIAL = "financial"
    TECHNOLOGICAL = "technological"
    GEOPOLITICAL = "geopolitical"


class RiskDuration(StrEnum):
    """Temporal classification of risk."""

    NEAR_TERM = "near_term"       # < 6 months
    MEDIUM_TERM = "medium_term"   # 6-18 months
    LONG_TERM = "long_term"       # > 18 months


class RiskNature(StrEnum):
    """Structural vs transitory."""

    TRANSITORY = "transitory"
    STRUCTURAL = "structural"


class SecurityType(StrEnum):
    """Supported security types."""

    EQUITY = "equity"
    ETF = "etf"


class AnalysisDomain(StrEnum):
    """Analytical domains covered by the engine."""

    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    MACRO = "macro"
    COMPETITIVE = "competitive"
    VALUATION = "valuation"
    RISK = "risk"
    CAPITAL_ALLOCATION = "capital_allocation"


class ScenarioType(StrEnum):
    """Valuation scenario types — mandatory in every report."""

    BULL = "bull"
    BASE = "base"
    BEAR = "bear"


class Timeframe(StrEnum):
    """Analysis timeframes."""

    ONE_MONTH = "1M"
    THREE_MONTHS = "3M"
    SIX_MONTHS = "6M"
    ONE_YEAR = "1Y"
    THREE_YEARS = "3Y"
    FIVE_YEARS = "5Y"
    TEN_YEARS = "10Y"
