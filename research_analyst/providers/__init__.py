"""Data providers — SEC/EDGAR, market data, technical indicators.

Each provider:
  - Returns typed Pydantic models (never raw dicts)
  - Handles its own retries and rate limiting
  - Logs data gaps explicitly (no silent failures)
  - Sanitizes all external input before use
"""
# Module: research_analyst/providers/__init__.py | Version: 0.1.0 | Updated: 2026-05-15

from .market_data import MarketDataProvider
from .sec_edgar import SECEdgarProvider
from .technical import TechnicalProvider

__all__ = ["MarketDataProvider", "SECEdgarProvider", "TechnicalProvider"]
