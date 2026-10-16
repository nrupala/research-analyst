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

"""Statistics Canada Web Data Service (WDS) provider — CA statistics.

Series wired (identities confirmed from getSeriesInfoFromVector
on 2026-10-16; the base path is /t1/wds/rest — the /n1/ variant
in older references 404s):
  - Vector 41690973, table 18-10-0004: "Canada; All-items"
    Consumer Price Index (2002=100), not seasonally adjusted.
    The WDS publishes the INDEX; the 12-month change is computed
    here from the newest point and the point 12 months earlier —
    the same arithmetic behind StatCan's headline rate. Aug 2026:
    169.8 vs 164.8 a year earlier = +3.03%.
  - Vector 2062815, table 14-10-0287: "Canada; Unemployment
    rate; Total - Gender; 15 years and over; Estimate; Seasonally
    adjusted" — published as a percent: 6.5% at 2026-09.

One POST (getDataFromVectorsAndLatestNPeriods) fetches both
vectors. If the year-earlier CPI point is absent, the CPI change
stays None — never estimated. Keyless; Statistics Canada Open
Licence (attribution).

The provider is a first-source SUPPLEMENT (source registry step
7): it fills the macro snapshot's StatCan fields and adds its
label to ``supplemental_sources``; it never overwrites other
fields.

Design (mirrors treasury.py / boc.py / bcb.py / abs.py / psa.py):
  - Stdlib urllib only; blocking call wrapped in asyncio.to_thread
  - Typed Pydantic results; graceful degradation; never raises.
"""
# Module: research_analyst/providers/statcan.py | Version: 0.1.0 | Updated: 2026-10-16

from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from datetime import date
from typing import Any

from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "Statistics Canada WDS"
CPI_VECTOR = 41690973
UNEMPLOYMENT_VECTOR = 2062815


class StatCanMacro(BaseModel):
    """Latest StatCan CPI 12-month change and unemployment rate."""

    cpi_yoy_pct: float | None = None  # percent, computed from the index
    cpi_as_of: date | None = None  # first of the newest index month
    unemployment_pct: float | None = None  # percent, as published
    unemployment_as_of: date | None = None
    source: str = SOURCE_NAME


def _points(payload: list[Any], vector_id: int) -> list[tuple[date, float]]:
    """(date, value) points for one vector, sorted ascending.

    Points with an unparseable period or value are skipped; the
    response order is not trusted.
    """
    out: list[tuple[date, float]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        obj = item.get("object") or {}
        if obj.get("vectorId") != vector_id:
            continue
        for dp in obj.get("vectorDataPoint", []):
            try:
                day = date.fromisoformat(str(dp.get("refPer"))[:10])
                value = float(dp.get("value"))
            except (TypeError, ValueError):
                continue
            out.append((day, value))
    out.sort(key=lambda p: p[0])
    return out


def _year_ago(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # Feb 29 -> Feb 28
        return day.replace(year=day.year - 1, day=28)


def parse_vectors_payload(payload: list[Any]) -> StatCanMacro:
    """Assemble the macro result from a WDS vectors response."""
    macro = StatCanMacro()
    cpi = _points(payload, CPI_VECTOR)
    if cpi:
        newest_day, newest_value = cpi[-1]
        prior = dict(cpi).get(_year_ago(newest_day))
        if prior:
            macro.cpi_as_of = newest_day
            macro.cpi_yoy_pct = (newest_value / prior - 1.0) * 100.0
    jobs = _points(payload, UNEMPLOYMENT_VECTOR)
    if jobs:
        macro.unemployment_as_of, macro.unemployment_pct = jobs[-1]
    return macro


def _fetch_vectors(base_url: str) -> list[Any]:
    """POST both vectors in one call. Raises on transport errors."""
    body = json.dumps(
        [
            {"vectorId": CPI_VECTOR, "latestN": 13},
            {"vectorId": UNEMPLOYMENT_VECTOR, "latestN": 2},
        ]
    ).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/getDataFromVectorsAndLatestNPeriods",
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ResearchAnalyst/0.4",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data: list[Any] = json.loads(resp.read().decode("utf-8-sig"))
    return data


class StatCanProvider:
    """Async facade over the Statistics Canada WDS (keyless)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.market.statcan_base_url).rstrip("/")

    async def get_latest_macro(self) -> StatCanMacro | None:
        """Latest CPI change + unemployment. None when both fail."""
        try:
            payload = await asyncio.to_thread(_fetch_vectors, self._base_url)
        except Exception as e:
            logger.debug("StatCan fetch failed: %s", e)
            return None
        macro = parse_vectors_payload(payload)
        if macro.cpi_yoy_pct is None and macro.unemployment_pct is None:
            return None
        return macro
