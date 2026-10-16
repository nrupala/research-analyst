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

"""Tiingo price provider — price cascade step 2 (first key service).

Owner cascade directive (2026-10-15): market-direct first, then the
free key services (Tiingo -> Alpha Vantage -> Twelve Data -> FMP),
then Stooq, then yfinance last; the serving source is labeled next to
the price. Tiingo leads the key services: clean end-of-day history on
its free key tier, one JSON fetch per ticker.

Endpoint: GET /tiingo/daily/{ticker}/prices?startDate=1990-01-01
returns the daily series as JSON, oldest first, with both raw and
adjusted fields. Adjustment basis: this provider serves Tiingo's
``adjClose`` (split- AND dividend-adjusted, Tiingo's documented
convention) as the close, so the frame contract (Adj Close == Close
for single-series providers) carries the adjusted basis — the same
convention as the Stooq step.

Key-gated: with no key configured (settings.market.tiingo_api_key,
env RA_MARKET_TIINGO_API_KEY) the provider yields None immediately and
the cascade falls through. The key is a credential: it travels only
in the request header, never in logs or errors.

Design (mirrors providers/nasdaq.py): httpx with trust_env=False,
blocking fetch in asyncio.to_thread, typed Pydantic results, any
failure yields None, missing stays missing.
"""
# Module: research_analyst/providers/tiingo.py | Version: 0.1.0 | Updated: 2026-10-15

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "Tiingo"


class TiingoBar(BaseModel):
    """One daily OHLCV bar (adjusted close basis, as published)."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class TiingoHistory(BaseModel):
    """A symbol's daily history from one Tiingo fetch."""

    symbol: str
    bars: list[TiingoBar]
    source: str = SOURCE_NAME

    @property
    def latest(self) -> TiingoBar | None:
        return self.bars[-1] if self.bars else None


def parse_daily_prices(payload: list[dict[str, Any]]) -> list[TiingoBar]:
    """Parse Tiingo's daily-prices JSON into bars, oldest first.

    Serves the ADJUSTED fields (adjOpen/adjHigh/adjLow/adjClose) so the
    series is split- and dividend-adjusted end to end; rows missing an
    adjusted close are skipped — a partial row is not data.
    """
    bars: list[TiingoBar] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            bar_date = date.fromisoformat(str(row.get("date", ""))[:10])
            close = float(row["adjClose"])
            open_ = float(row.get("adjOpen") or close)
            high = float(row.get("adjHigh") or close)
            low = float(row.get("adjLow") or close)
            volume = float(row.get("adjVolume") or row.get("volume") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        bars.append(
            TiingoBar(
                date=bar_date, open=open_, high=high, low=low, close=close, volume=volume
            )
        )
    return bars


def _fetch_daily_json(ticker: str, api_key: str) -> list[dict[str, Any]] | None:
    """Fetch the daily-prices JSON for ``ticker`` (blocking)."""
    url = f"{settings.market.tiingo_base_url.rstrip('/')}/tiingo/daily/{ticker}/prices"
    params = {"startDate": "1990-01-01", "format": "json"}
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "ResearchAnalyst/0.4",
    }
    try:
        with httpx.Client(
            trust_env=False, timeout=25.0, follow_redirects=True, headers=headers
        ) as client:
            response = client.get(url, params=params)
        if response.status_code != 200:
            logger.debug("Tiingo: HTTP %s for %s", response.status_code, ticker)
            return None
        payload = response.json()
    except Exception:  # transport/JSON failure -> next cascade step
        logger.debug("Tiingo: fetch failed for %s", ticker, exc_info=True)
        return None
    return payload if isinstance(payload, list) else None


class TiingoProvider:
    """Async facade over Tiingo's daily-prices API (key-gated)."""

    async def get_daily_history(self, ticker: str) -> TiingoHistory | None:
        """Full daily history for ``ticker``, or None.

        None covers: no key configured (step dormant), unknown ticker,
        refused fetch, transport failure. TSX coverage on Tiingo is
        thin — a Canadian miss here is expected and falls through to
        the next cascade step, labeled.
        """
        api_key = settings.market.tiingo_api_key.strip()
        if not api_key:
            return None
        symbol = ticker.strip().upper()
        if not symbol:
            return None
        payload = await asyncio.to_thread(_fetch_daily_json, symbol, api_key)
        if payload is None:
            return None
        bars = parse_daily_prices(payload)
        if not bars:
            return None
        return TiingoHistory(symbol=symbol, bars=bars)
