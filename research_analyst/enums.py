"""Enumerations for report types, risk categories, and analysis domains."""
# Module: research_analyst/enums.py | Version: 0.1.0 | Updated: 2026-05-15

from enum import Enum


class ReportType(str, Enum):
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


class RiskCategory(str, Enum):
    """Risk classification axis."""

    OPERATIONAL = "operational"
    MACRO = "macro"
    REGULATORY = "regulatory"
    COMPETITIVE = "competitive"
    FINANCIAL = "financial"
    TECHNOLOGICAL = "technological"
    GEOPOLITICAL = "geopolitical"


class RiskDuration(str, Enum):
    """Temporal classification of risk."""

    NEAR_TERM = "near_term"       # < 6 months
    MEDIUM_TERM = "medium_term"   # 6-18 months
    LONG_TERM = "long_term"       # > 18 months


class RiskNature(str, Enum):
    """Structural vs transitory."""

    TRANSITORY = "transitory"
    STRUCTURAL = "structural"


class SecurityType(str, Enum):
    """Supported security types."""

    EQUITY = "equity"
    ETF = "etf"


class AnalysisDomain(str, Enum):
    """Analytical domains covered by the engine."""

    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"
    MACRO = "macro"
    COMPETITIVE = "competitive"
    VALUATION = "valuation"
    RISK = "risk"
    CAPITAL_ALLOCATION = "capital_allocation"


class ScenarioType(str, Enum):
    """Valuation scenario types — mandatory in every report."""

    BULL = "bull"
    BASE = "base"
    BEAR = "bear"


class Timeframe(str, Enum):
    """Analysis timeframes."""

    ONE_MONTH = "1M"
    THREE_MONTHS = "3M"
    SIX_MONTHS = "6M"
    ONE_YEAR = "1Y"
    THREE_YEARS = "3Y"
    FIVE_YEARS = "5Y"
    TEN_YEARS = "10Y"
