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

"""Minor-unit quote currencies (GBp/ZAc/ILA) — normalization at ingestion.

Live-probed defect (2026-10-16): HSBA.L quotes in pence (GBp) while
its statements and per-share figures are in pounds. Unscaled, the
report showed price £1422.60 and P/E 1185.5x (1422.60 / £1.20 EPS);
the true figures are £14.23 and ~11.9x. yfinance units, verified on
the live ticker: prices, analyst targets, info currentPrice and the
dividend history are quote-unit; info rate/value fields
(trailingAnnualDividendRate 0.75, lastDividendValue 0.074134) are
already major-unit and must NOT be scaled.
"""
# Module: tests/test_minor_unit_currency.py

import asyncio

import pandas as pd
import pytest

from research_analyst.providers.market_data import (
    MarketDataProvider,
    _major_currency,
    _minor_unit_factor,
    _scale,
)


def test_unit_helpers():
    assert _minor_unit_factor("GBp") == 100
    assert _minor_unit_factor("ZAc") == 100
    assert _minor_unit_factor("ILA") == 100
    assert _minor_unit_factor("GBP") == 1
    assert _minor_unit_factor("USD") == 1
    assert _minor_unit_factor(None) == 1
    assert _major_currency("GBp") == "GBP"
    assert _major_currency("USD") == "USD"
    assert _major_currency(None) == "USD"
    assert _scale(1422.60, 100) == pytest.approx(14.226)
    assert _scale(1422.60, 1) == 1422.60
    assert _scale(None, 100) is None


class _NullCache:
    def get(self, key):
        return None

    def put(self, key, value):
        return None


def _provider(monkeypatch, factor=100):
    provider = MarketDataProvider()
    provider._cache = _NullCache()

    async def _factor(ticker):
        return factor

    monkeypatch.setattr(provider, "_quote_factor", _factor)
    return provider


def test_price_series_scaled(monkeypatch):
    provider = _provider(monkeypatch)
    idx = pd.to_datetime(["2026-10-12", "2026-10-13", "2026-10-14"])
    frame = pd.DataFrame(
        {
            "Open": [1400.0, 1410.0, 1420.0],
            "High": [1410.0, 1425.0, 1430.0],
            "Low": [1395.0, 1405.0, 1415.0],
            "Close": [1405.0, 1415.0, 1422.6],
            "Adj Close": [1405.0, 1415.0, 1422.6],
            "Volume": [1_000_000, 1_100_000, 1_200_000],
        },
        index=idx,
    )

    async def _cascade(ticker, period="1y", interval="1d"):
        return frame, "yfinance"

    monkeypatch.setattr(provider, "_cascade_download", _cascade)
    series = asyncio.run(provider.get_price_series("HSBA.L", period="5d"))
    assert series.current_price == pytest.approx(14.226)
    assert series.data[-1].close == pytest.approx(14.226)
    assert series.data[-1].open == pytest.approx(14.20)
    assert series.data[-1].volume == 1_200_000  # volumes are not money


def test_estimates_targets_scaled_eps_untouched(monkeypatch):
    provider = _provider(monkeypatch)

    class _Stub:
        info = {
            "targetMeanPrice": 1524.9651,
            "targetMedianPrice": 1500.0,
            "targetHighPrice": 1850.844,
            "targetLowPrice": 802.6046,
            "numberOfAnalystOpinions": 12,
            "epsCurrentYear": 1.30,
        }

    async def _ticker(ticker):
        return _Stub()

    monkeypatch.setattr(MarketDataProvider, "_yf_ticker", staticmethod(_ticker))
    estimates = asyncio.run(provider.get_analyst_estimates("HSBA.L"))
    assert estimates.target_price_mean == pytest.approx(15.249651)
    assert estimates.target_price_low == pytest.approx(8.026046)
    # Analyst EPS estimates are per-share in the major unit already.
    assert estimates.eps_estimate_current_year == pytest.approx(1.30)


def test_dividend_data_scales_quote_unit_fields_only(monkeypatch):
    provider = _provider(monkeypatch)

    class _Stub:
        info = {
            "quoteType": "EQUITY",
            "currency": "GBp",
            "currentPrice": 1421.2,
            "trailingAnnualDividendRate": 0.75,
            "lastDividendValue": 0.074134,
            "dividendYield": 0.0528,
        }
        dividends = pd.Series(
            [33.3016, 7.4134],
            index=pd.to_datetime(["2026-03-12", "2026-08-13"]),
        )

    async def _ticker(ticker):
        return _Stub()

    monkeypatch.setattr(MarketDataProvider, "_yf_ticker", staticmethod(_ticker))
    data = asyncio.run(provider.get_dividend_data("HSBA.L"))
    assert data.currency == "GBP"
    assert data.current_price == pytest.approx(14.212)
    assert data.history[-1].amount == pytest.approx(0.074134)
    assert data.history[0].amount == pytest.approx(0.333016)
    # Already major-unit in yfinance's info — untouched by design.
    assert data.trailing_dividend_rate == pytest.approx(0.75)
    assert data.last_dividend_value == pytest.approx(0.074134)


def test_profile_speaks_major_currency(monkeypatch):
    provider = _provider(monkeypatch, factor=1)

    class _Stub:
        info = {
            "longName": "HSBC Holdings plc",
            "quoteType": "EQUITY",
            "currency": "GBp",
            "regularMarketPrice": 1421.2,
            "marketCap": 243_000_000_000,
        }

    async def _ticker(ticker):
        return _Stub()

    monkeypatch.setattr(MarketDataProvider, "_yf_ticker", staticmethod(_ticker))
    profile = asyncio.run(provider.get_company_profile("HSBA.L"))
    assert profile.currency == "GBP"
    assert profile.name == "HSBC Holdings plc"
