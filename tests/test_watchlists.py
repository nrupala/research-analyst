"""F1.7 watchlists — store units + HTTP behavior.

Mirrors the F1.5 scenarios contract: keyed ownership (KeyStore keys
are RA's only identities), dormant 503 without a key store, uniform
401 without a valid key, per-key isolation, and a quotes view whose
prices carry their cascade source label — null when unserved, never
fabricated.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from research_analyst.entitlements import API_ACCESS, KeyStore
from research_analyst.models import PriceSeries
from research_analyst.server import _IPRateLimiter, create_app
from research_analyst.watchlists import MAX_WATCHLIST_TICKERS_PER_KEY, WatchlistStore


def _client(store=None, watchlists=None, metering=None):
    app = create_app(
        rate_limiter=_IPRateLimiter(rate=1000, burst=1000),
        key_store=store,
        metering=metering,
        watchlist_store=watchlists,
    )
    return TestClient(app, raise_server_exceptions=False)


def _key(store: KeyStore) -> str:
    _, raw = store.create("api", {API_ACCESS}, plan="api_pro")
    return raw


# ---------------------------------------------------------------------------
# Store units
# ---------------------------------------------------------------------------


def test_store_add_list_remove_and_isolation(tmp_path):
    store = WatchlistStore(path=tmp_path / "watchlists.json")
    entry, created = store.add("k1", "AAPL")
    assert created is True
    again, created2 = store.add("k1", "AAPL")
    assert created2 is False and again is entry  # idempotent
    store.add("k1", "MSFT")
    store.add("k2", "AAPL")
    assert [e.ticker for e in store.list_for_key("k1")] == ["AAPL", "MSFT"]
    assert [e.ticker for e in store.list_for_key("k2")] == ["AAPL"]
    assert store.remove("k1", "NVDA") is False
    assert store.remove("k2", "MSFT") is False  # not k2's entry
    assert store.remove("k1", "AAPL") is True
    assert [e.ticker for e in store.list_for_key("k1")] == ["MSFT"]


def test_store_persistence_round_trip(tmp_path):
    path = tmp_path / "watchlists.json"
    WatchlistStore(path=path).add("k1", "PETR4.SA")
    store2 = WatchlistStore(path=path)
    assert [e.ticker for e in store2.list_for_key("k1")] == ["PETR4.SA"]


def test_store_per_key_cap(tmp_path):
    store = WatchlistStore(path=tmp_path / "watchlists.json")
    for i in range(MAX_WATCHLIST_TICKERS_PER_KEY):
        assert store.add("k1", f"T{i}") is not None
    assert store.add("k1", "OVER") is None
    # Another key is unaffected by k1's cap.
    assert store.add("k2", "OVER") is not None


# ---------------------------------------------------------------------------
# HTTP behavior
# ---------------------------------------------------------------------------


def test_dormant_without_key_store():
    client = _client(store=None)
    assert client.get("/api/watchlist").status_code == 503
    assert client.post("/api/watchlist", json={"ticker": "AAPL"}).status_code == 503
    assert client.get("/api/watchlist/quotes").status_code == 503


def test_key_required():
    store = KeyStore()
    _key(store)
    client = _client(store=store, watchlists=WatchlistStore())
    assert client.get("/api/watchlist").status_code == 401
    bad = client.get("/api/watchlist", headers={"x-ra-key": "ra_live_bogus"})
    assert bad.status_code == 401


def test_add_list_delete_flow_and_isolation():
    store = KeyStore()
    raw_a = _key(store)
    raw_b = _key(store)
    client = _client(store=store, watchlists=WatchlistStore())
    ha, hb = {"x-ra-key": raw_a}, {"x-ra-key": raw_b}

    r = client.post("/api/watchlist", json={"ticker": "petr4.sa"}, headers=ha)
    assert r.status_code == 201 and r.json()["ticker"] == "PETR4.SA"
    r = client.post("/api/watchlist", json={"ticker": "PETR4.SA"}, headers=ha)
    assert r.status_code == 200  # idempotent re-add
    r = client.post("/api/watchlist", json={"ticker": "A" * 21}, headers=ha)
    assert r.status_code == 400  # invalid ticker shape

    assert [t["ticker"] for t in client.get("/api/watchlist", headers=ha).json()["tickers"]] == [
        "PETR4.SA"
    ]
    assert client.get("/api/watchlist", headers=hb).json()["tickers"] == []

    r = client.delete("/api/watchlist/PETR4.SA", headers=hb)
    assert r.status_code == 404  # not B's to delete
    r = client.delete("/api/watchlist/PETR4.SA", headers=ha)
    assert r.status_code == 200
    assert client.get("/api/watchlist", headers=ha).json()["tickers"] == []


def test_quotes_carry_source_labels_and_nulls():
    store = KeyStore()
    raw = _key(store)

    prices = PriceSeries(
        ticker="META",
        data=[],
        period_start=date(2026, 1, 1),
        period_end=date(2026, 10, 15),
        current_price=736.72,
        data_source="nasdaq",
    )
    mp = AsyncMock()

    async def _series(ticker, period="1y"):
        if ticker == "META":
            return prices
        raise RuntimeError("no data")

    mp.get_price_series = AsyncMock(side_effect=_series)
    with patch("research_analyst.server.MarketDataProvider", return_value=mp):
        client = _client(store=store, watchlists=WatchlistStore())
        h = {"x-ra-key": raw}
        client.post("/api/watchlist", json={"ticker": "META"}, headers=h)
        client.post("/api/watchlist", json={"ticker": "ZZZZ"}, headers=h)
        r = client.get("/api/watchlist/quotes", headers=h)
    assert r.status_code == 200
    quotes = {q["ticker"]: q for q in r.json()["quotes"]}
    assert quotes["META"]["price"] == 736.72
    assert quotes["META"]["source"] == "Nasdaq"
    assert quotes["META"]["as_of"] == "2026-10-15"
    assert quotes["ZZZZ"]["price"] is None and quotes["ZZZZ"]["source"] is None
