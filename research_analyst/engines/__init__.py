"""Analysis engines — the analytical brain of Research Analyst.

Each engine:
  - Takes typed Pydantic models as input (from providers)
  - Returns typed Pydantic models as output (fed to report renderer)
  - Documents every assumption explicitly
  - Logs data gaps — never silently invents data
  - Is stateless and thread-safe
"""
# Module: research_analyst/engines/__init__.py | Version: 0.1.1 | Updated: 2026-06-02

from .competitor import CompetitorEngine
from .dividend import DividendEngine
from .fundamental import FundamentalEngine
from .macro import MacroEngine
from .risk import RiskEngine
from .technical import TechnicalEngine
from .valuation import ValuationEngine

__all__ = [
    "CompetitorEngine",
    "DividendEngine",
    "FundamentalEngine",
    "MacroEngine",
    "RiskEngine",
    "TechnicalEngine",
    "ValuationEngine",
]
