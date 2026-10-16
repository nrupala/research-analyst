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

"""Banco Central do Brasil (BCB) SGS provider — first source for BR macro.

BCB's Sistema Gerenciador de Séries Temporais (SGS) is the official
publication channel for Brazilian monetary statistics. Series wired
(verified live 2026-10-16; fixtures in tests/):
  - 432   -> Selic target rate (% p.a.)
  - 13522 -> IPCA consumer inflation, accumulated 12 months (%)
  - 1     -> USD/BRL PTAX selling rate (BRL per USD)

Keyless. License: ODbL per BCB's open-data resource pages — consume
with attribution; RA sells its analysis, never the dataset.

The Selic series is published as a FORWARD strip: the current target
applied to the coming days, so rows can be dated after today. A row
is only "current" if its date is not in the future — the parser
takes the newest observation dated today or earlier and never
presents a future-dated row as the present rate.

Fetching uses explicit date-range queries, never ``ultimos/N``:
the SGS caps that form at 20 values (HTTP 400 beyond it — learned
live 2026-10-16 when a 30-row window silently degraded two of the
three series), and a range ending today excludes the forward
strip by construction.

The provider is a first-source SUPPLEMENT (source registry step 4):
it fills the macro snapshot's BCB fields and adds its label to
``supplemental_sources``; it never overwrites other fields.

Design (mirrors treasury.py / boc.py / boj.py / eia.py):
  - Stdlib urllib only; blocking fetch wrapped in asyncio.to_thread
  - Typed Pydantic results; values exactly as published (percents)
  - Graceful degradation: a failed series yields None for that series
    only; total failure yields None overall. Never raises.
  - Missing data stays missing — never a fabricated zero.
"""
# Module: research_analyst/providers/bcb.py | Version: 0.1.0 | Updated: 2026-10-16

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)

SOURCE_NAME = "Banco Central do Brasil (SGS)"
SELIC_SERIES = 432
IPCA_12M_SERIES = 13522
USD_BRL_SERIES = 1


class BcbMacro(BaseModel):
    """Latest BCB Selic target, IPCA 12-month inflation, USD/BRL PTAX."""

    selic_target_pct: float | None = None  # percent per year, as published
    selic_as_of: date | None = None
    ipca_12m_pct: float | None = None  # percent, as published
    ipca_as_of: date | None = None
    usd_brl_ptax: float | None = None  # BRL per USD, as published
    usd_brl_as_of: date | None = None
    source: str = SOURCE_NAME


def parse_sgs_payload(
    payload: object, *, today: date | None = None
) -> tuple[date, float] | None:
    """Newest usable (date, value) from an SGS JSON payload, or None.

    Rows are {"data": "DD/MM/YYYY", "valor": "13.75"}. Order is not
    trusted; rows dated after ``today`` (the Selic forward strip)
    and rows with unparseable dates/values are skipped — never
    zeroed, never presented as current.
    """
    if not isinstance(payload, list):
        return None
    today = today or date.today()
    best: tuple[date, float] | None = None
    for row in payload:
        if not isinstance(row, dict):
            continue
        raw_date, raw_value = row.get("data"), row.get("valor")
        if raw_date in (None, "") or raw_value in (None, ""):
            continue
        try:
            day = datetime.strptime(str(raw_date).strip(), "%d/%m/%Y").date()
            value = float(str(raw_value).strip().replace(",", "."))
        except (TypeError, ValueError):
            continue
        if day > today:
            continue
        if best is None or day > best[0]:
            best = (day, value)
    return best


def _fetch_series(
    base_url: str, series: int, lookback_days: int, *, today: date | None = None
) -> list[dict[str, Any]]:
    """Fetch one SGS series over an explicit date range. Stdlib only.

    Range form (dataInicial/dataFinal), never ``ultimos/N`` — see
    the module docstring for the 20-value cap. Raises on
    transport/HTTP errors so the caller can degrade.
    """
    end = today or date.today()
    start = end - timedelta(days=lookback_days)
    params = urllib.parse.urlencode(
        {
            "formato": "json",
            "dataInicial": start.strftime("%d/%m/%Y"),
            "dataFinal": end.strftime("%d/%m/%Y"),
        }
    )
    url = f"{base_url.rstrip('/')}/dados/serie/bcdata.sgs.{series}/dados?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "ResearchAnalyst/0.4"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode())
    return payload if isinstance(payload, list) else []


class BcbProvider:
    """Async facade over the BCB SGS API (keyless)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.market.bcb_base_url).rstrip("/")

    async def get_latest_macro(self) -> BcbMacro | None:
        """Latest Selic/IPCA/PTAX. None only when every series fails."""
        plan = (
            (SELIC_SERIES, 45),
            (IPCA_12M_SERIES, 400),
            (USD_BRL_SERIES, 45),
        )
        results = await asyncio.gather(
            *(
                asyncio.to_thread(_fetch_series, self._base_url, series, recent)
                for series, recent in plan
            ),
            return_exceptions=True,
        )
        macro = BcbMacro()
        got = False
        for (series, _), result in zip(plan, results, strict=True):
            if isinstance(result, BaseException):
                logger.debug("BCB SGS %s failed: %s", series, result)
                continue
            latest = parse_sgs_payload(result)
            if latest is None:
                continue
            got = True
            if series == SELIC_SERIES:
                macro.selic_as_of, macro.selic_target_pct = latest
            elif series == IPCA_12M_SERIES:
                macro.ipca_as_of, macro.ipca_12m_pct = latest
            else:
                macro.usd_brl_as_of, macro.usd_brl_ptax = latest
        return macro if got else None
