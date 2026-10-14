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
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""Bank of Canada Valet provider — first source for CA rates and FX.

Valet is the Bank of Canada's public data API. No key, no registration.
Terms: use/copy/distribution permitted with attribution
(bankofcanada.ca/terms).

Series wired:
  - V39079   -> policy interest rate (target for the overnight rate, %)
  - FXUSDCAD -> USD/CAD daily average (CAD per USD, as published)

Design (mirrors the FRED client in market_data.py):
  - Stdlib urllib only; blocking fetch wrapped in asyncio.to_thread
  - Typed Pydantic results; values exactly as published (no rescaling)
  - Graceful degradation: a failed series yields None for that series
    only; total failure yields None overall. Never raises.
  - Missing data stays missing — a series with no usable observation is
    None, never a fabricated zero.
"""
# Module: research_analyst/providers/boc.py | Version: 0.1.0 | Updated: 2026-10-14

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from datetime import date

from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "Bank of Canada Valet"
POLICY_RATE_SERIES = "V39079"
USD_CAD_SERIES = "FXUSDCAD"


class BocRates(BaseModel):
    """Latest Bank of Canada policy rate and USD/CAD observation."""

    policy_rate_pct: float | None = None  # percent, as published
    policy_rate_as_of: date | None = None
    usd_cad: float | None = None  # CAD per USD, as published
    usd_cad_as_of: date | None = None
    source: str = SOURCE_NAME


def _fetch_series_observations(
    base_url: str, series: str, recent: int = 5
) -> list[tuple[str, float]]:
    """Fetch recent observations for one Valet series, newest first.

    Stdlib only. Missing values are skipped. Raises on transport/HTTP
    errors so the caller can degrade gracefully.
    """
    params = urllib.parse.urlencode({"recent": recent})
    url = f"{base_url.rstrip('/')}/observations/{series}/json?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "ResearchAnalyst/0.4"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode())
    out: list[tuple[str, float]] = []
    for obs in payload.get("observations", []):
        cell = obs.get(series) or {}
        raw = cell.get("v")
        if raw in (None, ""):
            continue
        try:
            out.append((obs.get("d", ""), float(raw)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def _latest(obs: list[tuple[str, float]]) -> tuple[date, float] | None:
    """Newest (date, value) or None — an unparseable date means missing."""
    if not obs:
        return None
    try:
        return date.fromisoformat(obs[0][0]), obs[0][1]
    except ValueError:
        return None


class BankOfCanadaProvider:
    """Async facade over the Valet API (keyless)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.market.boc_base_url).rstrip("/")

    async def get_latest_rates(self) -> BocRates | None:
        """Latest policy rate + USD/CAD. None only when both series fail."""
        results = await asyncio.gather(
            asyncio.to_thread(
                _fetch_series_observations, self._base_url, POLICY_RATE_SERIES
            ),
            asyncio.to_thread(
                _fetch_series_observations, self._base_url, USD_CAD_SERIES
            ),
            return_exceptions=True,
        )
        rates = BocRates()
        got = False
        for series, result in zip((POLICY_RATE_SERIES, USD_CAD_SERIES), results, strict=True):
            if isinstance(result, Exception):
                logger.debug("Bank of Canada Valet %s failed: %s", series, result)
                continue
            latest = _latest(result)
            if latest is None:
                continue
            got = True
            if series == POLICY_RATE_SERIES:
                rates.policy_rate_as_of, rates.policy_rate_pct = latest
            else:
                rates.usd_cad_as_of, rates.usd_cad = latest
        return rates if got else None
