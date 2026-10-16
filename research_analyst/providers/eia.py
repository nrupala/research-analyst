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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""EIA Open Data API v2 provider — first source for US energy prices.

The U.S. Energy Information Administration is the official source
for US energy statistics. Series wired (verified live 2026-10-15
and 2026-10-16 via the account key; fixtures in tests/):
  - PET.RWTC.D   -> Cushing, OK WTI spot price FOB ($/barrel)
  - PET.RBRTE.D  -> Europe Brent spot price FOB ($/barrel)
  - NG.RNGWHHD.D -> Henry Hub natural gas spot price ($/MMBtu)

The provider is a first-source SUPPLEMENT (source registry step 3):
it fills the macro snapshot's EIA fields and adds its label to
``supplemental_sources``; it never overwrites other fields. A free
registration key is required (held in the Secure Vault since
2026-10-14); the provider arms when RA_MARKET_EIA_API_KEY is placed
in the environment — without a key it is dormant and returns None.

Design (mirrors treasury.py / boc.py / boj.py):
  - Stdlib urllib only; blocking fetch wrapped in asyncio.to_thread
  - Typed Pydantic results; values exactly as published
  - Graceful degradation: a failed series yields None for that series
    only; total failure yields None overall. Never raises.
  - Missing data stays missing — null observations are skipped,
    never zeroed.
"""
# Module: research_analyst/providers/eia.py | Version: 0.1.0 | Updated: 2026-10-16

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "EIA Open Data API v2"

WTI_SERIES = "PET.RWTC.D"  # Cushing, OK WTI Spot Price FOB ($/BBL)
BRENT_SERIES = "PET.RBRTE.D"  # Europe Brent Spot Price FOB ($/BBL)
HENRY_HUB_SERIES = "NG.RNGWHHD.D"  # Henry Hub Natural Gas Spot ($/MMBTU)

_REQUEST_TIMEOUT = 30.0
_WINDOW_DAYS = 45  # bound the seriesid payload; spot prices are daily


class EiaEnergyPrices(BaseModel):
    """Latest published spot prices, each with its own as-of date."""

    wti_spot_usd: float | None = None  # $/barrel, as published
    wti_as_of: date | None = None
    brent_spot_usd: float | None = None  # $/barrel, as published
    brent_as_of: date | None = None
    henry_hub_spot_usd: float | None = None  # $/MMBtu, as published
    henry_hub_as_of: date | None = None


def parse_series_payload(payload: dict[str, Any]) -> tuple[float, date] | None:
    """(value, period) of the newest non-null observation, or None.

    The v2 seriesid response carries ``response.data`` rows with
    ``period`` (YYYY-MM-DD) and ``value``; rows are not trusted to be
    ordered, so the maximum period wins.
    """
    rows = payload.get("response", {}).get("data")
    if not isinstance(rows, list):
        return None
    best: tuple[float, date] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_value = row.get("value")
        raw_period = row.get("period")
        if raw_value is None or not isinstance(raw_period, str):
            continue
        try:
            value = float(raw_value)
            period = date.fromisoformat(raw_period[:10])
        except (TypeError, ValueError):
            continue
        if best is None or period > best[1]:
            best = (value, period)
    return best


def _fetch_series(series_id: str, api_key: str) -> dict[str, Any] | None:
    start = (date.today() - timedelta(days=_WINDOW_DAYS)).isoformat()
    query = urllib.parse.urlencode({"api_key": api_key, "start": start})
    url = f"{settings.market.eia_base_url}/seriesid/{series_id}?{query}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "ResearchAnalyst/0.1 (nrupalakolkar@gmail.com)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug("EIA fetch failed for %s: %s", series_id, e)
        return None
    return payload if isinstance(payload, dict) else None


class EiaProvider:
    """Latest EIA spot energy prices (key-gated, never raises)."""

    async def get_latest_energy_prices(self) -> EiaEnergyPrices | None:
        api_key = settings.market.eia_api_key.strip()
        if not api_key:
            return None
        prices = EiaEnergyPrices()
        series_fields = (
            (WTI_SERIES, "wti_spot_usd", "wti_as_of"),
            (BRENT_SERIES, "brent_spot_usd", "brent_as_of"),
            (HENRY_HUB_SERIES, "henry_hub_spot_usd", "henry_hub_as_of"),
        )
        contributed = False
        for series_id, value_field, date_field in series_fields:
            payload = await asyncio.to_thread(_fetch_series, series_id, api_key)
            if payload is None:
                continue
            latest = parse_series_payload(payload)
            if latest is None:
                continue
            setattr(prices, value_field, latest[0])
            setattr(prices, date_field, latest[1])
            contributed = True
        return prices if contributed else None
