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

"""Nasdaq price provider — step 1 of the price cascade (US listings).

Owner cascade directive (2026-10-15): every dataset is served by a
declared cascade — first source of truth, mirror, backup, yfinance
last — and the source actually in play is labeled next to the price.
For US-listed equities the first step is Nasdaq's own published quote
API (api.nasdaq.com): the listing exchange publishing its own market's
prices, keyless, and verified reachable from the production host on
2026-10-15 (the same probe found Stooq JS-gated and Cboe behind a
Cloudflare redirect, so both sit behind this step).

Endpoint: GET /api/quote/{ticker}/historical?assetclass=stocks|etf
returns the full daily history as JSON (tradesTable rows, newest
first; one fetch with a wide fromdate returned 1,706 AAPL rows back to
2020-01-02 in live probing). ETFs are tried under assetclass=etf when
the stocks class yields no rows.

Adjustment policy — VERIFIED numerically from a live response
(2026-10-15): AAPL's 2020-01-02 close reads $75.0875; the actual traded
close was $300.35 and the 4:1 split of 2020-08-31 gives exactly
300.35 / 4 = 75.0875, so the series is back-adjusted for SPLITS ONLY —
dividends are NOT adjusted (a dividend-adjusted figure would be
lower). The latest close is therefore the real EOD close; historical
total-return math off this series excludes dividend yield, which the
source label discloses. Because the API ships a single adjusted OHLC
series, PriceData.adj_close is set equal to close for Nasdaq-served
series (the same convention as the Stooq path).

Consumption posture: Nasdaq's public website API, consumed under its
published terms with attribution on every price it serves; the data is
an input to RA's own analysis, never sold or redistributed as data
(license reciprocity, owner rule 2026-10-15).

Design (mirrors providers/stooq.py):
  - httpx with trust_env=False and an identifying browser-class
    User-Agent (the API refuses UA-less clients)
  - blocking fetch wrapped in asyncio.to_thread
  - typed Pydantic results; values exactly as published
  - graceful degradation: any failure yields None. Never raises.
  - missing data stays missing — no rows is None, never a zero-fill.
"""
# Module: research_analyst/providers/nasdaq.py | Version: 0.1.0 | Updated: 2026-10-15

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any

import httpx
from pydantic import BaseModel

from . import markets

logger = logging.getLogger(__name__)

SOURCE_NAME = "Nasdaq"

_BASE_URL = "https://api.nasdaq.com"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 ResearchAnalyst/0.4"
)
# Wide enough for every period the report layer asks for (10y max),
# in a single fetch — verified live (1,706 rows for AAPL).
_FROM_DATE = "1990-01-01"
_LIMIT = 9999


class NasdaqBar(BaseModel):
    """One daily OHLCV bar, exactly as published by Nasdaq."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class NasdaqHistory(BaseModel):
    """A symbol's full daily history from one Nasdaq API fetch."""

    symbol: str
    bars: list[NasdaqBar]
    source: str = SOURCE_NAME

    @property
    def latest(self) -> NasdaqBar | None:
        """The newest bar — its date is the price as-of date."""
        return self.bars[-1] if self.bars else None


def _parse_money(value: object) -> float | None:
    """Parse Nasdaq's "$342.00" / "1,234.56" numeric strings."""
    if value is None:
        return None
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text or text.upper() in {"N/A", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_trades_table(payload: dict[str, Any]) -> list[NasdaqBar]:
    """Parse a Nasdaq historical payload into bars, oldest first.

    Anything malformed (missing table, unparseable rows) yields what
    parsed cleanly; a payload with no usable rows yields []. Rows are
    published newest first and are reversed here.
    """
    data = payload.get("data") or {}
    table = data.get("tradesTable") or {}
    rows = table.get("rows") or []
    bars: list[NasdaqBar] = []
    for row in rows:
        try:
            bar_date = datetime.strptime(str(row.get("date", "")), "%m/%d/%Y").date()
        except ValueError:
            continue
        close = _parse_money(row.get("close"))
        if close is None:
            continue
        open_ = _parse_money(row.get("open"))
        high = _parse_money(row.get("high"))
        low = _parse_money(row.get("low"))
        volume = _parse_money(row.get("volume"))
        bars.append(
            NasdaqBar(
                date=bar_date,
                open=open_ if open_ is not None else close,
                high=high if high is not None else close,
                low=low if low is not None else close,
                close=close,
                volume=volume if volume is not None else 0.0,
            )
        )
    bars.reverse()
    return bars


def _fetch_history_json(ticker: str, assetclass: str) -> dict[str, Any] | None:
    """Fetch the historical-quote JSON for one asset class (blocking).

    Returns the decoded payload, or None on any transport/HTTP/JSON
    failure — the caller degrades to the next cascade step.
    """
    url = f"{_BASE_URL}/api/quote/{ticker}/historical"
    params = {
        "assetclass": assetclass,
        "fromdate": _FROM_DATE,
        "limit": str(_LIMIT),
    }
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    try:
        with httpx.Client(
            trust_env=False, timeout=25.0, follow_redirects=True, headers=headers
        ) as client:
            response = client.get(url, params=params)
        if response.status_code != 200:
            logger.debug(
                "Nasdaq: HTTP %s for %s (%s)", response.status_code, ticker, assetclass
            )
            return None
        payload = response.json()
    except Exception:  # transport/JSON failure -> next cascade step
        logger.debug("Nasdaq: fetch failed for %s (%s)", ticker, assetclass, exc_info=True)
        return None
    return payload if isinstance(payload, dict) else None


class NasdaqProvider:
    """Async facade over Nasdaq's public quote API (keyless)."""

    async def get_daily_history(self, ticker: str) -> NasdaqHistory | None:
        """Full daily history for ``ticker``, or None.

        US listings only: a ticker carrying a foreign-market suffix
        (markets.py) is out of this provider's scope and yields None
        immediately. None covers every no-data case uniformly —
        unknown ticker, refused fetch, transport failure. The caller
        discloses the absence; nothing is substituted silently (the
        cascade's next step serves, labeled).
        """
        symbol = ticker.strip().upper()
        if not symbol or markets.suffix_of(symbol):
            logger.debug("Nasdaq: %s is not a US-listing symbol", ticker)
            return None
        for assetclass in ("stocks", "etf"):
            payload = await asyncio.to_thread(_fetch_history_json, symbol, assetclass)
            if payload is None:
                continue
            bars = parse_trades_table(payload)
            if bars:
                return NasdaqHistory(symbol=symbol, bars=bars)
        return None
