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

"""Stooq EOD price provider — owner-designated production price source.

Owner decision (2026-10-14): "Use Stooq free EOD for prices, labeled
and disclosed." Stooq is a FREE end-of-day source, not an exchange
first source — the registry declares it exactly that way, and reports
label it "Stooq (price data — free end-of-day)".

Endpoint: GET {base}/q/d/l/?s={symbol}&i=d returns the symbol's FULL
daily history as one CSV (Date,Open,High,Low,Close,Volume). That single
fetch serves both the latest EOD close and the price history.

Adjustment policy — VERIFIED from a recorded Stooq response for AAPL
(captured 2025-02-15; excerpts in tests/fixtures/): Stooq's OHLC series
is back-adjusted for BOTH splits and dividends:
  - 2020-08-28 (last pre-split close, actual 499.23): split-only
    adjustment gives 124.81; Stooq shows 121.967 — lower by the
    cumulative dividend factor, so dividends are adjusted too.
  - 2015-01-02 (actual 109.33): split-only gives 27.33; Stooq shows
    24.3738 — a decade of dividend accrual.
  - No 4x discontinuity across the 2020-08-31 split (121.967 ->
    126.106), and the head of the series equals actual traded closes
    (2025-02-14 close 244.6), so the latest close IS the real EOD close.
  - Volumes are adjustment-scaled as well (they carry fractional
    parts, e.g. 191998866.78); consumers treat them as approximate.
Because Stooq ships a single adjusted OHLC series, PriceData.adj_close
is set equal to close for Stooq-served series — the same convention the
yfinance path approximates with its separate Adj Close column.

Browser verification: Stooq serves a JavaScript proof-of-work
verification page to automated clients (recorded live 2026-10-14,
tests/fixtures/stooq_verify_challenge.html). This client completes the
same verification a browser performs — solve the SHA-256 proof-of-work
the page itself publishes, POST it to /__verify, keep the session
cookie — openly, under an identifying User-Agent. If verification or
the download is refused, the fetch yields NO data: observed from the
production host on 2026-10-14, the download endpoint answered
"Access denied" even to a verified session. Since the owner's cascade
directive (2026-10-15), Stooq is step 3 of the declared price cascade
in market_data.py: when this client yields no data the cascade falls
through to the next step, and whichever step serves is stamped on the
series and labeled next to the price — fall-through is disclosed,
never silent. This client itself still serves Stooq data only.

Symbol mapping (providers/markets.py registry driven): an entry is
added ONLY with live-verified evidence that the Stooq symbol returns
data. Today that is the US only (lowercase ticker + ".us"). Every
other market is unmapped and stays missing — never guess a suffix.

Design (mirrors providers/boc.py):
  - httpx with trust_env=False (sandbox proxies must never reroute
    data calls); blocking fetch wrapped in asyncio.to_thread
  - Typed Pydantic results; values exactly as published
  - Graceful degradation: any failure yields None. Never raises.
  - Missing data stays missing — no rows is None, never a zero-fill.
"""
# Module: research_analyst/providers/stooq.py | Version: 0.1.0 | Updated: 2026-10-14

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import logging
import re
from datetime import date

import httpx
from pydantic import BaseModel

from ..config import settings
from . import markets

logger = logging.getLogger(__name__)

SOURCE_NAME = "Stooq"

_CSV_HEADER_PREFIX = "Date,Open,High,Low,Close"
_VERIFY_MARKER = "__verify"
_CHALLENGE_RE = re.compile(r'const c="([^"]+)",d=(\d+)')
# The recorded verification page uses difficulty 4 (hex zeros). Refuse
# anything dramatically harder rather than burn CPU on an anomaly.
_MAX_POW_DIFFICULTY = 6
_MAX_POW_ITERATIONS = 20_000_000

# Market code -> Stooq symbol suffix. ONLY live-verified mappings are
# listed (see module docstring). Keys are markets.py market codes.
_STOOQ_SUFFIX_BY_MARKET: dict[str, str] = {
    "US": ".us",
}


def stooq_symbol(ticker: str) -> str | None:
    """Map an RA ticker to its Stooq symbol, or None when unmapped.

    Unmapped means: the market has no live-verified Stooq mapping, so
    the price stays missing rather than guessed.
    """
    market = markets.resolve(ticker)
    suffix = _STOOQ_SUFFIX_BY_MARKET.get(market.code)
    if suffix is None:
        return None
    base = ticker.strip()
    yf_suffix = markets.suffix_of(base)
    if yf_suffix:
        base = base[: -len(yf_suffix)]
    if not base:
        return None
    return base.lower() + suffix


class StooqBar(BaseModel):
    """One daily OHLCV bar, exactly as published by Stooq."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float  # adjustment-scaled by Stooq; may be fractional


class StooqHistory(BaseModel):
    """A symbol's full daily history from one Stooq CSV fetch."""

    symbol: str
    bars: list[StooqBar]
    source: str = SOURCE_NAME

    @property
    def latest(self) -> StooqBar | None:
        """The newest bar — its date is the price as-of date."""
        return self.bars[-1] if self.bars else None


def parse_daily_csv(text: str) -> list[StooqBar]:
    """Parse a Stooq daily-history CSV body into bars, oldest first.

    Anything that is not a CSV with the expected header — an unknown
    ticker's empty reply, a verification page, an "Access denied"
    body — yields no bars. Malformed rows are skipped, never repaired.
    """
    if not text or not text.lstrip().startswith(_CSV_HEADER_PREFIX):
        return []
    out: list[StooqBar] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            bar = StooqBar(
                date=date.fromisoformat((row.get("Date") or "").strip()),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume") or 0.0),
            )
        except (TypeError, ValueError, KeyError):
            continue
        out.append(bar)
    out.sort(key=lambda b: b.date)
    return out


def parse_challenge(html: str) -> tuple[str, int] | None:
    """Extract (challenge, difficulty) from a Stooq verification page."""
    m = _CHALLENGE_RE.search(html or "")
    if not m:
        return None
    try:
        difficulty = int(m.group(2))
    except ValueError:
        return None
    if difficulty < 0 or difficulty > _MAX_POW_DIFFICULTY:
        return None
    return m.group(1), difficulty


def solve_challenge(challenge: str, difficulty: int) -> int | None:
    """Solve the page's SHA-256 proof-of-work, as a browser would.

    Finds n with sha256(challenge + str(n)) starting with ``difficulty``
    hex zeros. None when the bounded search is exhausted.
    """
    target = "0" * difficulty
    for n in range(_MAX_POW_ITERATIONS):
        digest = hashlib.sha256((challenge + str(n)).encode()).hexdigest()
        if digest.startswith(target):
            return n
    return None


def _download_csv_text(base_url: str, symbol: str) -> str:
    """Fetch the daily-history CSV body for ``symbol`` (blocking).

    Completes Stooq's browser verification once if challenged (see the
    module docstring). Returns the final body, whatever it is — the
    parser decides whether it is data. Raises on transport errors so
    the caller can degrade gracefully.
    """
    base = base_url.rstrip("/")
    url = f"{base}/q/d/l/?s={symbol}&i=d"
    headers = {"User-Agent": "ResearchAnalyst/0.4"}
    with httpx.Client(
        trust_env=False, timeout=20.0, follow_redirects=True, headers=headers
    ) as client:
        text = client.get(url).text
        if _VERIFY_MARKER in text:
            parsed = parse_challenge(text)
            if parsed is not None:
                challenge, difficulty = parsed
                n = solve_challenge(challenge, difficulty)
                if n is not None:
                    client.post(
                        f"{base}/__verify",
                        data={"c": challenge, "n": str(n)},
                        headers={"Referer": url},
                    )
                    text = client.get(url).text
        return text


class StooqProvider:
    """Async facade over Stooq's free EOD CSV download (keyless)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.market.stooq_base_url).rstrip("/")

    async def get_daily_history(self, ticker: str) -> StooqHistory | None:
        """Full daily history for ``ticker``, or None.

        None covers every no-data case uniformly: unmapped market,
        unknown ticker, refused download, transport failure. The
        caller discloses the absence; nothing is substituted.
        """
        symbol = stooq_symbol(ticker)
        if symbol is None:
            logger.debug("Stooq: no verified symbol mapping for %s", ticker)
            return None
        try:
            text = await asyncio.to_thread(_download_csv_text, self._base_url, symbol)
        except Exception as e:  # noqa: BLE001 - degrade, never crash the pipeline
            logger.debug("Stooq fetch failed for %s: %s", symbol, e)
            return None
        bars = parse_daily_csv(text)
        if not bars:
            logger.debug("Stooq returned no data for %s", symbol)
            return None
        return StooqHistory(symbol=symbol, bars=bars)
