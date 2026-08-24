"""International market registry for Research Analyst.

Maps a ticker's exchange suffix (yfinance convention) to its market: currency,
default risk-free rate, equity-risk-premium, timezone, peer-discovery sector ETF,
and a jurisdiction key for the disclaimer system.

v0.3.0 Slice A foundation. ADDITIVE -- importing this module changes no existing
behavior; the US single-market path is unchanged until consumers opt in.

Rates/ERPs are indicative 2026 defaults and are meant to be overridable
(per-request or via RA_MARKET_* env in config). They are NOT investment advice.
"""
# Module: research_analyst/providers/markets.py | Version: 0.3.0 | Slice A
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    code: str                    # short market code, e.g. "US", "UK", "IN"
    name: str                    # human-readable market name
    suffix: str                  # yfinance ticker suffix, e.g. ".L" ("" for US)
    currency: str                # ISO 4217, e.g. "USD", "GBP"
    risk_free_rate: float        # indicative local 10Y sovereign yield (decimal)
    equity_risk_premium: float   # indicative country ERP (decimal)
    timezone: str                # IANA timezone of the exchange
    sector_etf: str              # ETF used for peer discovery
    disclaimer_key: str          # jurisdiction key for the disclaimer system (Slice C)


# US carries the empty suffix. Keyed by the lowercased yfinance suffix (incl. dot).
_BY_SUFFIX: dict[str, Market] = {
    "":    Market("US", "United States", "", "USD", 0.043, 0.055, "America/New_York", "SPY", "US"),
    ".to": Market("CA", "Canada (TSX)", ".TO", "CAD", 0.034, 0.055, "America/Toronto", "EWC", "CA"),
    ".v":  Market("CA", "Canada (TSX-V)", ".V", "CAD", 0.034, 0.060, "America/Toronto", "EWC", "CA"),
    ".l":  Market("UK", "United Kingdom (LSE)", ".L", "GBP", 0.041, 0.058, "Europe/London", "EWU", "UK"),
    ".de": Market("DE", "Germany (XETRA)", ".DE", "EUR", 0.026, 0.056, "Europe/Berlin", "EWG", "EU"),
    ".pa": Market("FR", "France (Euronext Paris)", ".PA", "EUR", 0.031, 0.058, "Europe/Paris", "EWQ", "EU"),
    ".as": Market("NL", "Netherlands (Euronext Amsterdam)", ".AS", "EUR", 0.028, 0.057, "Europe/Amsterdam", "EWN", "EU"),
    ".mi": Market("IT", "Italy (Borsa Italiana)", ".MI", "EUR", 0.038, 0.060, "Europe/Rome", "EWI", "EU"),
    ".t":  Market("JP", "Japan (TSE)", ".T", "JPY", 0.010, 0.060, "Asia/Tokyo", "EWJ", "JP"),
    ".ax": Market("AU", "Australia (ASX)", ".AX", "AUD", 0.043, 0.060, "Australia/Sydney", "EWA", "AU"),
    ".ns": Market("IN", "India (NSE)", ".NS", "INR", 0.070, 0.075, "Asia/Kolkata", "INDA", "IN"),
    ".bo": Market("IN", "India (BSE)", ".BO", "INR", 0.070, 0.075, "Asia/Kolkata", "INDA", "IN"),
    ".hk": Market("HK", "Hong Kong (HKEX)", ".HK", "HKD", 0.035, 0.065, "Asia/Hong_Kong", "EWH", "HK"),
}

US = _BY_SUFFIX[""]

# Known suffix keys (without the leading dot) for fast membership tests.
_KNOWN = {s.lstrip(".") for s in _BY_SUFFIX if s}


def normalize_ticker(ticker: str) -> str:
    """Trim and upper-case a ticker."""
    return (ticker or "").strip().upper()


def suffix_of(ticker: str) -> str:
    """Return the yfinance exchange suffix (e.g. '.NS') for a ticker, or '' for US.

    Only the segment after the final dot is treated as a suffix, and only when it
    matches a known exchange -- so US class shares like 'BRK.B' resolve to US.
    """
    t = normalize_ticker(ticker)
    if "." not in t:
        return ""
    tail = t.rsplit(".", 1)[1]
    return f".{tail}" if tail.lower() in _KNOWN else ""


def resolve(ticker: str) -> Market:
    """Resolve a ticker to its Market. Unknown/undotted -> US (default)."""
    return _BY_SUFFIX.get(suffix_of(ticker).lower(), US)


def is_us(ticker: str) -> bool:
    """True when the ticker belongs to the US market (SEC EDGAR applies)."""
    return resolve(ticker).code == "US"


def should_query_sec(ticker: str) -> bool:
    """Whether SEC EDGAR should be queried for a ticker (US listings only).

    SEC EDGAR is a US-filing database; querying it for a non-US listing wastes a
    rate-limited request and never matches. Non-US fundamentals come from the
    market-data provider (yfinance) instead.
    """
    return is_us(ticker)


def fx_pair(currency: str, base: str = "USD") -> "str | None":
    """yfinance FX symbol to convert `currency` -> `base` (e.g. 'INRUSD=X').

    Returns None when currency == base (no conversion needed).
    """
    c = (currency or "").strip().upper()
    b = (base or "").strip().upper()
    if not c or c == b:
        return None
    return f"{c}{b}=X"


def all_markets() -> "list[Market]":
    """All distinct markets in the registry (deduplicated by market code)."""
    seen: dict[str, Market] = {}
    for m in _BY_SUFFIX.values():
        seen.setdefault(m.code, m)
    return list(seen.values())
