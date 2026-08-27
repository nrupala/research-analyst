"""Ticker-resolution guard tests (bad-ticker handling).

Regression for the launch bug where an unresolvable symbol (e.g. 'ZZZQQXX')
produced an HTTP 200 fabricated report instead of a clean 4xx rejection.

Offline only: yfinance is mocked; no network.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from research_analyst.providers.market_data import MarketDataProvider
from research_analyst.resolver import resolve_subject


def _provider_with_info(info: dict) -> MarketDataProvider:
    p = MarketDataProvider()
    # Bypass the disk cache in tests.
    p._cache = MagicMock()
    p._cache.get.return_value = None
    p._cache.put.return_value = None

    async def _fake_yf_ticker(ticker: str):
        return SimpleNamespace(info=info)

    p._yf_ticker = _fake_yf_ticker  # type: ignore[assignment]
    return p


async def test_unresolvable_ticker_raises():
    # Sparse dict yfinance returns for a bogus symbol: no name, no price.
    p = _provider_with_info({"trailingPegRatio": None, "maxAge": 1})
    with pytest.raises(ValueError, match="Could not resolve ticker"):
        await p.get_company_profile("ZZZQQXX")


async def test_empty_info_raises():
    p = _provider_with_info({})
    with pytest.raises(ValueError):
        await p.get_company_profile("NOPE")


async def test_resolves_with_name_only():
    p = _provider_with_info({"longName": "Apple Inc.", "quoteType": "EQUITY"})
    prof = await p.get_company_profile("AAPL")
    assert prof.name == "Apple Inc."


async def test_resolves_with_price_only():
    # No name, but a real price -> still a valid listing.
    p = _provider_with_info({"regularMarketPrice": 123.45, "quoteType": "EQUITY"})
    prof = await p.get_company_profile("THINLY")
    assert prof.ticker == "THINLY"


async def test_international_ticker_resolves():
    # RY.TO-style international listing: name + price + non-USD currency.
    p = _provider_with_info({
        "longName": "Royal Bank of Canada",
        "quoteType": "EQUITY",
        "currency": "CAD",
        "regularMarketPrice": 178.9,
        "exchange": "TOR",
    })
    prof = await p.get_company_profile("RY.TO")
    assert prof.currency == "CAD"
    assert prof.name == "Royal Bank of Canada"


# ---------------------------------------------------------------------------
# resolve_subject: India alias map + bare -> .NS "did you mean" (Slice C).
# Pure/offline: markets is a deterministic suffix table, no network.
# ---------------------------------------------------------------------------

def test_alias_infy_resolves_to_nse():
    r = resolve_subject("INFY", [])
    assert r.status == "resolved"
    assert r.resolved.symbol == "INFY.NS"
    assert r.resolved.currency == "INR"


def test_alias_icici_maps_to_icicibank_nse():
    r = resolve_subject("icici", [])  # normalized to upper before lookup
    assert r.status == "resolved"
    assert r.resolved.symbol == "ICICIBANK.NS"


def test_bare_symbol_suggests_ns():
    r = resolve_subject("ICICIBANK", [])
    assert r.status == "ambiguous"
    assert r.candidates and r.candidates[0].symbol == "ICICIBANK.NS"
    assert "did you mean" in (r.note or "").lower()


def test_explicit_suffix_still_resolves():
    r = resolve_subject("TECHM.BO", [])
    assert r.status == "resolved"
    assert r.resolved.symbol == "TECHM.BO"


def test_name_query_not_suggested_as_ns():
    r = resolve_subject("some random company", [])
    assert r.status == "not_found"
