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

"""Alpha Vantage price provider — price cascade step 2 (gap-filler).

Owner cascade directive (2026-10-15): the free key services sit
between market-direct and Stooq. Alpha Vantage's free key tier is
capped at ~25 requests/day, so this step is a GAP-FILLER behind the
disk cache, never a workhorse: it serves only tickers the steps above
missed, and an exhausted quota yields None (rate-limit bodies are
detected and treated as no-data, not as errors).

Endpoint: GET /query?function=TIME_SERIES_DAILY&symbol=...&
outputsize=full returns the full daily series as a JSON object keyed
by date. The free tier serves TIME_SERIES_DAILY only (the ADJUSTED
variant is premium), so the basis is **as-traded prices, unadjusted**
— disclosed here and in the registry; the frame contract sets Adj
Close == Close for this step, meaning historical return math off an
Alpha-Vantage-served series excludes split/dividend adjustment. The
source label next to the price names the step, so the basis is never
hidden. TSX symbols are requested with Alpha Vantage's .TSX suffix
when the RA ticker carries .TO.

Key-gated: no key configured (settings.market.alpha_vantage_key, env
RA_MARKET_ALPHA_VANTAGE_KEY) -> None immediately. The key travels
only in the request URL to Alpha Vantage itself (their API design);
it is never logged.

Design (mirrors providers/tiingo.py): httpx trust_env=False, blocking
fetch in asyncio.to_thread, typed results, failures yield None.
"""
# Module: research_analyst/providers/alphavantage.py | Version: 0.1.0 | Updated: 2026-10-15

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "Alpha Vantage"


class AlphaVantageBar(BaseModel):
    """One daily OHLCV bar, exactly as published (as-traded basis)."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class AlphaVantageHistory(BaseModel):
    """A symbol's daily history from one Alpha Vantage fetch."""

    symbol: str
    bars: list[AlphaVantageBar]
    source: str = SOURCE_NAME

    @property
    def latest(self) -> AlphaVantageBar | None:
        return self.bars[-1] if self.bars else None


def parse_time_series(payload: dict[str, Any]) -> list[AlphaVantageBar]:
    """Parse a TIME_SERIES_DAILY payload into bars, oldest first.

    Rate-limit and premium notice bodies ({"Note": ...} /
    {"Information": ...}) have no series key and yield [].
    """
    series = payload.get("Time Series (Daily)")
    if not isinstance(series, dict):
        return []
    bars: list[AlphaVantageBar] = []
    for day, row in series.items():
        if not isinstance(row, dict):
            continue
        try:
            bar_date = date.fromisoformat(str(day)[:10])
            close = float(row["4. close"])
            open_ = float(row.get("1. open") or close)
            high = float(row.get("2. high") or close)
            low = float(row.get("3. low") or close)
            volume = float(row.get("6. volume") or row.get("5. volume") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        bars.append(
            AlphaVantageBar(
                date=bar_date, open=open_, high=high, low=low, close=close, volume=volume
            )
        )
    bars.sort(key=lambda b: b.date)
    return bars


def _fetch_series_json(symbol: str, api_key: str) -> dict[str, Any] | None:
    """Fetch the TIME_SERIES_DAILY payload for ``symbol`` (blocking)."""
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": "full",
        "apikey": api_key,
    }
    headers = {"User-Agent": "ResearchAnalyst/0.4"}
    try:
        with httpx.Client(
            trust_env=False, timeout=30.0, follow_redirects=True, headers=headers
        ) as client:
            response = client.get(settings.market.alpha_vantage_base_url, params=params)
        if response.status_code != 200:
            logger.debug("Alpha Vantage: HTTP %s for %s", response.status_code, symbol)
            return None
        payload = response.json()
    except Exception:  # transport/JSON failure -> next cascade step
        logger.debug("Alpha Vantage: fetch failed for %s", symbol, exc_info=True)
        return None
    return payload if isinstance(payload, dict) else None


class AlphaVantageProvider:
    """Async facade over Alpha Vantage's daily series API (key-gated)."""

    async def get_daily_history(self, ticker: str) -> AlphaVantageHistory | None:
        """Full daily history for ``ticker``, or None.

        None covers: no key configured, unknown ticker, quota
        exhausted, refused fetch, transport failure. For a .TO ticker
        the .TSX symbol form Alpha Vantage uses is tried as well.
        """
        api_key = settings.market.alpha_vantage_key.strip()
        if not api_key:
            return None
        symbol = ticker.strip().upper()
        if not symbol:
            return None
        candidates = [symbol]
        if symbol.endswith(".TO"):
            candidates.append(symbol[: -len(".TO")] + ".TSX")
        for candidate in candidates:
            payload = await asyncio.to_thread(_fetch_series_json, candidate, api_key)
            if payload is None:
                continue
            bars = parse_time_series(payload)
            if bars:
                return AlphaVantageHistory(symbol=candidate, bars=bars)
        return None
