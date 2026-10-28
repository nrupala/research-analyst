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

"""US Treasury Fiscal Data provider — first source for US fiscal/rates.

Dataset: Average Interest Rates on U.S. Treasury Securities (monthly) from
the Bureau of the Fiscal Service's Fiscal Data API. No API key. Terms:
data is free without restriction (fiscaldata.treasury.gov API docs).

Design (mirrors the FRED client in market_data.py):
  - Stdlib urllib only; blocking fetch wrapped in asyncio.to_thread
  - Typed Pydantic results; values kept in percent, exactly as published
  - Graceful degradation: any failure returns None, never raises
  - Missing data stays missing — unparseable rows are skipped, not zeroed

The Treasury Bills average rate is the risk-free-grade input the quant
engine can consume. A daily par-yield-curve endpoint was NOT verified on
Fiscal Data (probed 2026-10-14: candidate paths 404) — this provider
therefore wires the verified average-interest-rates dataset only.
"""
# Module: research_analyst/providers/treasury.py | Version: 0.1.0 | Updated: 2026-10-14

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "US Treasury Fiscal Data"
_AVG_RATES_PATH = "/v2/accounting/od/avg_interest_rates"


class TreasuryRatePoint(BaseModel):
    """One security class's average interest rate at the record date."""

    security_desc: str  # e.g. "Treasury Bills", "Treasury Notes"
    security_type_desc: str  # e.g. "Marketable"
    avg_interest_rate_pct: float  # percent, as published (e.g. 3.870)


class TreasuryAvgRates(BaseModel):
    """Average interest rates for the latest record date in the dataset."""

    as_of: date  # the record_date every point below belongs to
    rates: list[TreasuryRatePoint]
    source: str = SOURCE_NAME

    def rate_pct_for(self, security_desc: str) -> float | None:
        """Published percent rate for one security class, or None if absent."""
        for point in self.rates:
            if point.security_desc == security_desc:
                return point.avg_interest_rate_pct
        return None

    @property
    def treasury_bills_pct(self) -> float | None:
        """Treasury Bills average rate (percent) — short risk-free input."""
        return self.rate_pct_for("Treasury Bills")


def _fetch_avg_interest_rates(base_url: str, page_size: int = 30) -> dict[str, Any]:
    """Fetch the newest Average Interest Rates page. Stdlib only.

    Raises on transport/HTTP errors so the caller can degrade gracefully.
    """
    params = urllib.parse.urlencode(
        {"sort": "-record_date", "page[size]": page_size, "format": "json"}
    )
    url = f"{base_url.rstrip('/')}{_AVG_RATES_PATH}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "ResearchAnalyst/0.4"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())  # type: ignore[no-any-return]


def parse_avg_interest_rates(payload: dict[str, Any]) -> TreasuryAvgRates | None:
    """Parse a Fiscal Data response into the latest record date's rates.

    Rows arrive newest-first but span more than one record date; only the
    newest date's rows are kept. Rows with a missing/unparseable rate are
    skipped (missing stays missing). Returns None when no usable row exists.
    """
    rows = payload.get("data") or []
    by_date: dict[str, list[TreasuryRatePoint]] = {}
    for row in rows:
        record_date = row.get("record_date")
        desc = row.get("security_desc")
        raw = row.get("avg_interest_rate_amt")
        if not record_date or not desc or raw in (None, ""):
            continue
        try:
            rate = float(raw)
        except (TypeError, ValueError):
            continue
        by_date.setdefault(record_date, []).append(
            TreasuryRatePoint(
                security_desc=str(desc),
                security_type_desc=str(row.get("security_type_desc") or ""),
                avg_interest_rate_pct=rate,
            )
        )
    if not by_date:
        return None
    latest = max(by_date)  # ISO dates sort lexicographically
    try:
        as_of = date.fromisoformat(latest)
    except ValueError:
        return None
    return TreasuryAvgRates(as_of=as_of, rates=by_date[latest])


class TreasuryProvider:
    """Async facade over the Fiscal Data API (keyless)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.market.treasury_base_url).rstrip("/")

    async def get_avg_interest_rates(self) -> TreasuryAvgRates | None:
        """Latest average interest rates, or None on any failure."""
        try:
            payload = await asyncio.to_thread(_fetch_avg_interest_rates, self._base_url)
            return parse_avg_interest_rates(payload)
        except Exception as e:
            logger.debug("US Treasury Fiscal Data fetch failed: %s", e)
            return None
