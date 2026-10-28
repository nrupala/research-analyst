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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""Price cascade tests (owner directive, 2026-10-15).

The cascade serves in declared order — market-direct (Nasdaq) -> key
services (Tiingo, Alpha Vantage) -> Stooq -> yfinance last — and the
serving step is stamped on the series so renderers can label the
price with its true source. Payloads are recorded-shape fixtures
modeled on the live responses probed from the production host on
2026-10-15 (Nasdaq: AAPL history incl. the split-adjusted 2020-01-02
close of $75.0875). Offline only: transports are mocked.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

import research_analyst.providers.alphavantage as av_module
import research_analyst.providers.nasdaq as nasdaq_module
import research_analyst.providers.stooq as stooq_module
import research_analyst.providers.tiingo as tiingo_module
from research_analyst.config import settings
from research_analyst.models import price_source_label
from research_analyst.providers.alphavantage import parse_time_series
from research_analyst.providers.market_data import MarketDataProvider, _DiskCache
from research_analyst.providers.nasdaq import NasdaqProvider, parse_trades_table
from research_analyst.providers.tiingo import parse_daily_prices

NASDAQ_AAPL = {
    "data": {
        "symbol": "AAPL",
        "totalRecords": 3,
        "tradesTable": {
            "headers": {
                "date": "Date",
                "close": "Close/Last",
                "volume": "Volume",
                "open": "Open",
                "high": "High",
                "low": "Low",
            },
            "rows": [
                {
                    "date": "10/15/2026",
                    "close": "$342.00",
                    "volume": "39,767,260",
                    "open": "$346.95",
                    "high": "$347.85",
                    "low": "$341.60",
                },
                {
                    "date": "10/14/2026",
                    "close": "$341.18",
                    "volume": "38,000,000",
                    "open": "$340.00",
                    "high": "$343.00",
                    "low": "$339.50",
                },
                {
                    "date": "01/02/2020",
                    "close": "$75.0875",
                    "volume": "135,647,440",
                    "open": "$74.06",
                    "high": "$75.15",
                    "low": "$73.7975",
                },
            ],
        },
    }
}


def _provider(tmp_path: Path) -> MarketDataProvider:
    provider = MarketDataProvider()
    provider._cache = _DiskCache(tmp_path, ttl_seconds=3600)
    return provider


def _frame() -> pd.DataFrame:
    idx = pd.to_datetime(["2026-10-12", "2026-10-13"])
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Adj Close": [101.0, 102.0],
            "Volume": [1_000_000, 1_100_000],
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# Nasdaq parsing — recorded shape, split-adjusted basis, newest-first input
# ---------------------------------------------------------------------------


def test_nasdaq_parse_reverses_and_parses_money():
    bars = parse_trades_table(NASDAQ_AAPL)
    assert [b.date for b in bars] == [
        date(2020, 1, 2),
        date(2026, 10, 14),
        date(2026, 10, 15),
    ]
    # Split-adjusted basis, verified live: $300.35 actual / 4 = $75.0875.
    assert bars[0].close == pytest.approx(75.0875)
    assert bars[-1].close == pytest.approx(342.00)
    assert bars[-1].volume == 39_767_260


def test_nasdaq_parse_skips_na_rows():
    payload = {
        "data": {
            "tradesTable": {
                "rows": [
                    {"date": "10/15/2026", "close": "N/A", "volume": "0"},
                    {
                        "date": "10/14/2026",
                        "close": "$10.00",
                        "volume": "5",
                        "open": "$9.00",
                        "high": "$10.50",
                        "low": "$8.50",
                    },
                ]
            }
        }
    }
    bars = parse_trades_table(payload)
    assert len(bars) == 1
    assert bars[0].close == pytest.approx(10.0)


async def test_nasdaq_provider_skips_foreign_suffix():
    provider = NasdaqProvider()
    assert await provider.get_daily_history("SHOP.TO") is None


# ---------------------------------------------------------------------------
# Cascade order — the highest serving step wins and is stamped
# ---------------------------------------------------------------------------


async def test_cascade_nasdaq_serves_first(tmp_path):
    provider = _provider(tmp_path)
    stooq_dl = AsyncMock(side_effect=AssertionError("stooq must not run"))
    with (
        patch.object(nasdaq_module, "_fetch_history_json", return_value=NASDAQ_AAPL),
        patch.object(MarketDataProvider, "_stooq_download", stooq_dl),
    ):
        series = await provider.get_price_series("AAPL", period="max")
    assert series.data_source == "nasdaq"
    assert series.current_price == pytest.approx(342.00)
    assert series.period_start == date(2020, 1, 2)


async def test_cascade_falls_through_to_yfinance_labeled(tmp_path):
    provider = _provider(tmp_path)
    with (
        patch.object(nasdaq_module, "_fetch_history_json", return_value=None),
        patch.object(
            stooq_module, "_download_csv_text", return_value="Access denied"
        ),
        patch.object(
            MarketDataProvider, "_yf_download", new=AsyncMock(return_value=_frame())
        ),
    ):
        series = await provider.get_price_series("AAPL", period="1y")
    # yfinance served — and the series SAYS so (the label is the point).
    assert series.data_source == "yfinance"
    assert len(series.data) == 2
    assert series.current_price == pytest.approx(102.0)


async def test_cascade_all_steps_empty_surfaces_missing(tmp_path):
    provider = _provider(tmp_path)
    with (
        patch.object(nasdaq_module, "_fetch_history_json", return_value=None),
        patch.object(
            stooq_module, "_download_csv_text", return_value="Access denied"
        ),
        patch.object(
            MarketDataProvider,
            "_yf_download",
            new=AsyncMock(return_value=pd.DataFrame()),
        ),
    ):
        series = await provider.get_price_series("AAPL", period="1y")
    assert series.data == []
    assert series.data_source == ""


async def test_cascade_canada_falls_to_yfinance(tmp_path):
    # Nasdaq skips .TO by scope; Stooq's map is US-only; the Canada
    # rule serves from the secondaries, labeled (owner, 2026-10-15).
    provider = _provider(tmp_path)
    with patch.object(
        MarketDataProvider, "_yf_download", new=AsyncMock(return_value=_frame())
    ) as yf:
        series = await provider.get_price_series("SHOP.TO", period="1y")
    assert series.data_source == "yfinance"
    assert yf.await_count == 1


# ---------------------------------------------------------------------------
# Key services — parsing + dormancy without a key
# ---------------------------------------------------------------------------


def test_tiingo_parse_uses_adjusted_basis():
    payload = [
        {
            "date": "2026-10-14T00:00:00.000Z",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.5,
            "adjOpen": 99.0,
            "adjHigh": 101.0,
            "adjLow": 98.0,
            "adjClose": 100.5,
            "volume": 1000,
            "adjVolume": 1000,
        },
        {"date": "2026-10-15T00:00:00.000Z", "adjClose": 102.25},
    ]
    bars = parse_daily_prices(payload)
    assert len(bars) == 2
    assert bars[0].close == pytest.approx(100.5)  # adjClose, not close
    assert bars[1].close == pytest.approx(102.25)
    assert bars[1].open == pytest.approx(102.25)  # missing fields fill from close


def test_alphavantage_parse_and_rate_limit_body():
    payload = {
        "Time Series (Daily)": {
            "2026-10-15": {
                "1. open": "101.0",
                "2. high": "103.0",
                "3. low": "100.0",
                "4. close": "102.0",
                "5. volume": "12345",
            },
            "2026-10-14": {
                "1. open": "100.0",
                "2. high": "102.0",
                "3. low": "99.0",
                "4. close": "101.0",
                "5. volume": "11000",
            },
        }
    }
    bars = parse_time_series(payload)
    assert [b.date for b in bars] == [date(2026, 10, 14), date(2026, 10, 15)]
    assert bars[-1].close == pytest.approx(102.0)
    # Quota/premium notice bodies are no-data, not errors.
    assert parse_time_series({"Note": "rate limit"}) == []
    assert parse_time_series({"Information": "premium endpoint"}) == []


async def test_key_services_dormant_without_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.market, "tiingo_api_key", "")
    monkeypatch.setattr(settings.market, "alpha_vantage_key", "")
    tiingo_fetch = AsyncMock(
        side_effect=AssertionError("tiingo fetch must not run without a key")
    )
    av_fetch = AsyncMock(
        side_effect=AssertionError("alpha vantage fetch must not run without a key")
    )
    with (
        patch.object(nasdaq_module, "_fetch_history_json", return_value=None),
        patch.object(tiingo_module, "_fetch_daily_json", tiingo_fetch),
        patch.object(av_module, "_fetch_series_json", av_fetch),
        patch.object(
            stooq_module, "_download_csv_text", return_value="Access denied"
        ),
        patch.object(
            MarketDataProvider,
            "_yf_download",
            new=AsyncMock(return_value=pd.DataFrame()),
        ),
    ):
        provider = _provider(tmp_path)
        df, source = await provider._cascade_download("AAPL", period="1y", interval="1d")
    assert df.empty
    assert source == ""
    tiingo_fetch.assert_not_called()
    av_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Labels — the small print next to the price
# ---------------------------------------------------------------------------


def test_price_source_label_mapping():
    assert price_source_label("nasdaq") == " (source: Nasdaq)"
    assert price_source_label("tiingo") == " (source: Tiingo)"
    assert price_source_label("alphavantage") == " (source: Alpha Vantage)"
    assert price_source_label("stooq") == " (source: Stooq)"
    assert price_source_label("yfinance") == " (source: Yahoo Finance)"
    assert price_source_label("") == ""
    assert price_source_label("legacy-unknown") == ""


def test_price_declaration_name_matches_price_line_label():
    """Release-gate Low (2026-10-15): one canonical name per cascade
    step. The Data Sources declaration name must equal the name the
    price lines print — both come from PRICE_SOURCE_LABELS."""
    from research_analyst.models import PRICE_SOURCE_LABELS
    from research_analyst.orchestrator import _price_declaration

    for key, name in PRICE_SOURCE_LABELS.items():
        assert _price_declaration(key).startswith(f"{name} ("), key
    # The gate's exact case: the last step never declares as "yfinance".
    assert _price_declaration("yfinance") == "Yahoo Finance (price data)"
    assert _price_declaration("nasdaq") == (
        "Nasdaq (price data — exchange-published, end-of-day)"
    )
    # Unknown/legacy stamps keep the yfinance-era name, never invent.
    assert _price_declaration("").startswith("Yahoo Finance (")
    assert _price_declaration("legacy-cache").startswith("Yahoo Finance (")
