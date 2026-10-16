# Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
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

"""Ticker validation — international suffixes must survive the provider.

Regression (found live 2026-10-15): the API layer admits tickers up to
20 chars (api_models, raised for suffixed international symbols), but
the market-data provider's _sanitize_ticker still capped at 10 — so
RELIANCE.NS (11) and TATAMOTORS.NS (13) died with "Invalid ticker"
while INFY.NS (7) served. The cap is now 20 in both layers; the
charset guard (alphanumeric + dot/hyphen) is unchanged.
"""
# Module: tests/test_ticker_validation.py

import pandas as pd
import pytest

from research_analyst.providers.market_data import MarketDataProvider, _sanitize_ticker


@pytest.mark.parametrize(
    "ticker",
    [
        "AAPL",          # US plain
        "SHOP.TO",       # Canada
        "INFY.NS",       # India, short symbol
        "RELIANCE.NS",   # India, 11 chars — the regression case
        "TATAMOTORS.NS", # India, 13 chars
        "RELIANCE.BO",   # India (BSE)
        "600519.SS",     # China
        "SAP.DE",        # Germany
        "MC.PA",         # France
        "7203.T",        # Japan
        "D05.SI",        # Singapore
        "9988.HK",       # Hong Kong
        "BRK-B",         # hyphenated class share
    ],
)
def test_valid_tickers_accepted(ticker):
    assert _sanitize_ticker(ticker) == ticker
    assert _sanitize_ticker(ticker.lower()) == ticker  # case-normalized


@pytest.mark.parametrize(
    "ticker",
    [
        "",
        "A" * 21,             # over the 20-char cap
        "RELIANCE.NS EXTRA",  # spaces are not ticker chars
        "AA$",                # punctuation outside dot/hyphen
        "AA/BB",              # path separator
    ],
)
def test_invalid_tickers_rejected(ticker):
    with pytest.raises(ValueError):
        _sanitize_ticker(ticker)


class _NullCache:
    def get(self, key):  # noqa: ARG002
        return None

    def set(self, key, value):  # noqa: ARG002
        return None


async def test_price_series_reaches_cascade_for_long_india_ticker(monkeypatch):
    """RELIANCE.NS must get past validation to the cascade (which may
    legitimately return empty in a stubbed test — the defect was the
    ValueError before any source was tried)."""
    provider = MarketDataProvider()
    monkeypatch.setattr(provider, "_cache", _NullCache())

    async def _empty_cascade(ticker, period="1y", interval="1d"):
        return pd.DataFrame(), ""

    monkeypatch.setattr(provider, "_cascade_download", _empty_cascade)
    series = await provider.get_price_series("RELIANCE.NS", period="3mo")
    assert series.ticker == "RELIANCE.NS"
    assert series.data == []
