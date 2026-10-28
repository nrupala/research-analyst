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

"""Philippine Statistics Authority (PSA) OpenSTAT provider — PH macro.

PSA's OpenSTAT is a PxWeb API. Tables wired (located by walking the
live catalogue and reading each table's metadata on 2026-10-16):
  - Prices > CPI YoY table 0012M4ACP23.px ("Year-on-Year Changes of
    the Consumer Price Index in Percent by Commodity Group"):
    Geolocation PHILIPPINES, Commodity ALL ITEMS -> 7.2% at 2026-09.
  - Labor Force Survey rates table 0021B3FKEI2.px ("Rates Key
    Employment Indicators"): Rates = Unemployment Rate, Sex = Both
    sexes -> 5.269% at 2026-08.

Year values in PxWeb tables are INDEX-coded ("7" means 2026 in one
table, "21" in the other) and the codes shift as years are added —
so the provider reads each table's metadata at runtime, resolves
the newest year's code and the month codes from the value texts,
and only then posts the query. Missing cells arrive as ".." / "."
and are skipped, never zeroed. Anonymous access; the API rejects
the default Python user agent (HTTP 403), so requests carry the
fleet UA, and POST responses can carry a UTF-8 BOM, so bodies are
decoded as utf-8-sig. Rate guidance (registry matrix): 10 requests / 10 s —
this provider makes four small calls per snapshot population.

The provider is a first-source SUPPLEMENT (source registry step
6): it fills the macro snapshot's PSA fields and adds its label to
``supplemental_sources``; it never overwrites other fields.

Design (mirrors treasury.py / boc.py / bcb.py / abs.py):
  - Stdlib urllib only; blocking calls wrapped in asyncio.to_thread
  - Typed Pydantic results; values exactly as published (percents)
  - Graceful degradation per series; never raises; missing = None.
"""
# Module: research_analyst/providers/psa.py | Version: 0.1.0 | Updated: 2026-10-16

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

SOURCE_NAME = "Philippine Statistics Authority OpenSTAT"
CPI_TABLE = "DB/2M/PI/CPI/2018NEW/0012M4ACP23.px"
LFS_TABLE = "DB/1B/LFS/0021B3FKEI2.px"
_UA = {"User-Agent": "ResearchAnalyst/0.4"}

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7,
    "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


class PsaMacro(BaseModel):
    """Latest PSA CPI YoY inflation and unemployment rate."""

    cpi_yoy_pct: float | None = None  # percent, as published
    cpi_as_of: date | None = None  # first of the month
    unemployment_pct: float | None = None  # percent, as published
    unemployment_as_of: date | None = None  # first of the month
    source: str = SOURCE_NAME


def _variable(meta: dict[str, Any], code: str) -> dict[str, Any] | None:
    for var in meta.get("variables", []):
        if isinstance(var, dict) and var.get("code") == code:
            found: dict[str, Any] = var
            return found
    return None


def _newest_year(meta: dict[str, Any]) -> tuple[str, int] | None:
    """(code, year) for the numerically greatest Year value text."""
    var = _variable(meta, "Year")
    if var is None:
        return None
    best: tuple[str, int] | None = None
    for code, text in zip(var["values"], var["valueTexts"], strict=True):
        try:
            year = int(str(text).strip())
        except ValueError:
            continue
        if best is None or year > best[1]:
            best = (str(code), year)
    return best


def _month_codes(meta: dict[str, Any], code: str) -> dict[str, int]:
    """Map a month variable's codes -> month numbers (months only)."""
    var = _variable(meta, code)
    if var is None:
        return {}
    out: dict[str, int] = {}
    for value, text in zip(var["values"], var["valueTexts"], strict=True):
        month = _MONTHS.get(str(text).strip().lower())
        if month is not None:
            out[str(value)] = month
    return out


def _code_for_text(meta: dict[str, Any], code: str, needle: str) -> str | None:
    var = _variable(meta, code)
    if var is None:
        return None
    for value, text in zip(var["values"], var["valueTexts"], strict=True):
        if needle.lower() in str(text).strip().lower():
            return str(value)
    return None


def parse_rows(
    payload: dict[str, Any], year: int, months: dict[str, int],
    dims: tuple[str, ...],
) -> tuple[date, float] | None:
    """Newest (date, value) from a PxWeb 'json' response.

    ``dims`` names the key positions of (year, month) inside each
    row's key array. Non-numeric cells ('..', '.') are missing.
    """
    columns = [c.get("code") for c in payload.get("columns", [])]
    try:
        yi = columns.index(dims[0])
        mi = columns.index(dims[1])
    except ValueError:
        return None
    best: tuple[int, date, float] | None = None
    for row in payload.get("data", []):
        key = row.get("key", [])
        values = row.get("values", [])
        if len(key) <= max(yi, mi) or not values:
            continue
        month = months.get(str(key[mi]))
        if month is None:
            continue
        try:
            value = float(str(values[0]).strip())
        except ValueError:
            continue
        if best is None or month > best[0]:
            best = (month, date(year, month, 1), value)
    if best is None:
        return None
    return best[1], best[2]


def _get_json(base_url: str, path: str) -> dict[str, Any]:
    req = urllib.request.Request(f"{base_url.rstrip('/')}/{path}", headers=_UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data: dict[str, Any] = json.loads(resp.read().decode("utf-8-sig"))
    return data


def _post_query(
    base_url: str, path: str, selections: list[dict[str, Any]]
) -> dict[str, Any]:
    body = json.dumps(
        {"query": selections, "response": {"format": "json"}}
    ).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/{path}",
        data=body,
        headers={**_UA, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data: dict[str, Any] = json.loads(resp.read().decode("utf-8-sig"))
    return data


def _sel(code: str, values: list[str]) -> dict[str, Any]:
    return {"code": code, "selection": {"filter": "item", "values": values}}


class PsaProvider:
    """Async facade over PSA OpenSTAT (anonymous, PxWeb)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.market.psa_base_url).rstrip("/")

    async def _series(
        self,
        table: str,
        fixed: list[tuple[str, str]],
        month_var: str,
    ) -> tuple[date, float] | None:
        meta = await asyncio.to_thread(_get_json, self._base_url, table)
        newest = _newest_year(meta)
        months = _month_codes(meta, month_var)
        if newest is None or not months:
            return None
        year_code, year = newest
        selections = [_sel("Year", [year_code])]
        selections.append(_sel(month_var, list(months.keys())))
        for code, needle in fixed:
            resolved = _code_for_text(meta, code, needle)
            if resolved is None:
                return None
            selections.append(_sel(code, [resolved]))
        payload = await asyncio.to_thread(
            _post_query, self._base_url, table, selections
        )
        return parse_rows(payload, year, months, ("Year", month_var))

    async def get_latest_macro(self) -> PsaMacro | None:
        """Latest CPI YoY + unemployment. None when both series fail."""
        macro = PsaMacro()
        got = False
        try:
            cpi = await self._series(
                CPI_TABLE,
                [("Geolocation", "PHILIPPINES"),
                 ("Commodity Description", "ALL ITEMS")],
                "Period",
            )
            if cpi is not None:
                macro.cpi_as_of, macro.cpi_yoy_pct = cpi
                got = True
        except Exception as e:
            logger.debug("PSA CPI failed: %s", e)
        try:
            lfs = await self._series(
                LFS_TABLE,
                [("Rates", "Unemployment Rate"), ("Sex", "Both sexes")],
                "Month",
            )
            if lfs is not None:
                macro.unemployment_as_of, macro.unemployment_pct = lfs
                got = True
        except Exception as e:
            logger.debug("PSA LFS failed: %s", e)
        return macro if got else None
