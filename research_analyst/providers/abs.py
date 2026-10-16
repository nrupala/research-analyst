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

"""Australian Bureau of Statistics (ABS) Data API provider — AU macro.

ABS publishes Australia's official statistics over an SDMX REST
API. Series wired (keys decoded from the live DSD codelists and
verified against the API on 2026-10-16; fixtures in tests/):
  - CPI_Q key 3.999901.20.50.Q -> All groups CPI, seasonally
    adjusted, weighted average of eight capital cities, percentage
    change from the corresponding quarter of the previous year
    (MEASURE 3 / INDEX 999901 / TSEST 20 / REGION 50 per the ABS
    codelists CL_CPI_*): 3.9% at 2026-Q2.
  - LF key M13.3.1599.20.AUS.M -> unemployment rate (M13), persons
    (SEX 3), total age (1599), seasonally adjusted (20), Australia
    (AUS): 4.72% at 2026-09.

Endpoint note (learned live): the working host is
``data.api.abs.gov.au`` with a ``/rest`` prefix. The transposed
``api.data.abs.gov.au`` printed in ABS's own beta page does not
resolve in DNS.

Keyless (ABS encourages key registration for production, optional).
ABS content is CC BY 4.0 Australia: consume with attribution.

The provider is a first-source SUPPLEMENT (source registry step
5): it fills the macro snapshot's ABS fields and adds its label to
``supplemental_sources``; it never overwrites other fields.

Design (mirrors treasury.py / boc.py / boj.py / bcb.py):
  - Stdlib urllib only; blocking fetch wrapped in asyncio.to_thread
  - SDMX-CSV responses parsed with csv.DictReader (the format
    verified live; dimension columns ride along and are checked)
  - Typed Pydantic results; values exactly as published (percents)
  - Graceful degradation per series; never raises; missing = None.
"""
# Module: research_analyst/providers/abs.py | Version: 0.1.0 | Updated: 2026-10-16

from __future__ import annotations

import asyncio
import calendar
import csv
import io
import logging
import urllib.parse
import urllib.request
from datetime import date

from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "Australian Bureau of Statistics Data API"
CPI_DATAFLOW = "ABS,CPI_Q,1.0.0"
CPI_KEY = "3.999901.20.50.Q"
LF_DATAFLOW = "ABS,LF,1.0.0"
LF_KEY = "M13.3.1599.20.AUS.M"


class AbsMacro(BaseModel):
    """Latest ABS CPI YoY inflation and unemployment rate."""

    cpi_yoy_pct: float | None = None  # percent, as published
    cpi_as_of: date | None = None  # quarter-end date
    unemployment_pct: float | None = None  # percent, as published
    unemployment_as_of: date | None = None  # first of the month
    source: str = SOURCE_NAME


def _period_key(period: str) -> tuple[int, int] | None:
    """Sortable (year, sub-period) for '2026-Q2' / '2026-09'."""
    try:
        year_s, sub = period.strip().split("-")
        year = int(year_s)
        if sub.startswith("Q"):
            return year, int(sub[1:]) * 3
        return year, int(sub)
    except (ValueError, IndexError):
        return None


def _period_date(period: str) -> date | None:
    """Quarter -> its end date; month -> its first day."""
    key = _period_key(period)
    if key is None:
        return None
    year, month = key
    try:
        if "-Q" in period:
            return date(year, month, calendar.monthrange(year, month)[1])
        return date(year, month, 1)
    except ValueError:
        return None


def parse_sdmx_csv(text: str) -> tuple[date, float] | None:
    """Newest (date, value) from an SDMX-CSV response, or None.

    Rows carry TIME_PERIOD + OBS_VALUE; order is not trusted, and
    rows with unparseable periods/values are skipped — never zeroed.
    """
    best: tuple[tuple[int, int], date, float] | None = None
    for row in csv.DictReader(io.StringIO(text)):
        period = (row.get("TIME_PERIOD") or "").strip()
        raw = (row.get("OBS_VALUE") or "").strip()
        if not period or not raw:
            continue
        key = _period_key(period)
        day = _period_date(period)
        if key is None or day is None:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if best is None or key > best[0]:
            best = (key, day, value)
    if best is None:
        return None
    return best[1], best[2]


def _fetch_csv(base_url: str, dataflow: str, key: str, start_period: str) -> str:
    """Fetch one keyed SDMX-CSV series. Raises on transport errors."""
    params = urllib.parse.urlencode({"startPeriod": start_period, "format": "csv"})
    url = f"{base_url.rstrip('/')}/data/{dataflow}/{key}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "ResearchAnalyst/0.4"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        text: str = resp.read().decode("utf-8", errors="replace")
    return text


class AbsProvider:
    """Async facade over the ABS Data API (keyless)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.market.abs_base_url).rstrip("/")

    async def get_latest_macro(self) -> AbsMacro | None:
        """Latest CPI YoY + unemployment. None when both series fail."""
        year = date.today().year
        plan = (
            (CPI_DATAFLOW, CPI_KEY, str(year - 1)),
            (LF_DATAFLOW, LF_KEY, str(year)),
        )
        results = await asyncio.gather(
            *(
                asyncio.to_thread(
                    _fetch_csv, self._base_url, dataflow, key, start
                )
                for dataflow, key, start in plan
            ),
            return_exceptions=True,
        )
        macro = AbsMacro()
        got = False
        for (dataflow, _, _), result in zip(plan, results, strict=True):
            if isinstance(result, BaseException):
                logger.debug("ABS %s failed: %s", dataflow, result)
                continue
            latest = parse_sdmx_csv(result)
            if latest is None:
                continue
            got = True
            if dataflow == CPI_DATAFLOW:
                macro.cpi_as_of, macro.cpi_yoy_pct = latest
            else:
                macro.unemployment_as_of, macro.unemployment_pct = latest
        return macro if got else None
