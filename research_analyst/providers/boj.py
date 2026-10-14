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

"""Bank of Japan Time-Series API provider — first source for JP rates/FX.

The BoJ Time-Series Data Search API (launched 18 Feb 2026) is keyless.
Series wired (verified live 2026-10-14; fixtures in tests/):
  - FM08 / FXERD04  -> USD/JPY spot rate at 17:00 JST, Tokyo market
                       (yen per U.S. dollar, as published)
  - IR01 / MADR1Z@D -> "The Basic Discount Rate and Basic Loan Rate"
                       (percent per annum, as published) — the BoJ's
                       administered policy-rate series in its IR01
                       interest-rates database

BoJ obligations (api_notice_en.pdf, via the BoJ API pages) — carried in
the source registry entry's flags and in BOJ_OBLIGATIONS below:
  - A service built on this API must display BoJ's prescribed credit line.
  - BoJ's Research and Statistics Department must be notified by email
    BEFORE such a service is released.
  - Excessive (high-frequency) access is prohibited.

Design (mirrors treasury.py / boc.py):
  - Stdlib urllib only; blocking fetch wrapped in asyncio.to_thread
  - Typed Pydantic results; values exactly as published
  - Graceful degradation: a failed series yields None for that series
    only; total failure yields None overall. Never raises.
  - Missing data stays missing — trailing null observations in a window
    (future dates) are skipped, never zeroed.
"""
# Module: research_analyst/providers/boj.py | Version: 0.1.0 | Updated: 2026-10-14

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

SOURCE_NAME = "Bank of Japan Time-Series API"

USD_JPY_DB = "FM08"  # Foreign Exchange Rates (Daily)
USD_JPY_CODE = "FXERD04"  # spot rate at 17:00 JST, Tokyo market
POLICY_RATE_DB = "IR01"  # Interest Rates
POLICY_RATE_CODE = "MADR1Z@D"
POLICY_RATE_SERIES_NAME = "The Basic Discount Rate and Basic Loan Rate"

# Obligations BoJ attaches to API use (matrix §4, verified 2026-10-14).
BOJ_OBLIGATIONS: tuple[str, ...] = (
    "credit-line-required: any service displaying BoJ API data must show "
    "BoJ's prescribed credit line (api_notice_en.pdf)",
    "pre-release-notification-required: BoJ's Research and Statistics "
    "Department must be notified by email before a service built on this "
    "API is released",
    "no-excessive-access: high-frequency access is prohibited by BoJ",
)


class BojRates(BaseModel):
    """Latest Bank of Japan USD/JPY spot and administered policy rate."""

    usd_jpy: float | None = None  # yen per USD, as published
    usd_jpy_as_of: date | None = None
    policy_rate_pct: float | None = None  # percent per annum, as published
    policy_rate_as_of: date | None = None
    policy_rate_series_name: str = POLICY_RATE_SERIES_NAME
    source: str = SOURCE_NAME


def _fetch_series(
    base_url: str, db: str, code: str, start_yyyymm: str, end_yyyymm: str
) -> dict[str, Any]:
    """Fetch one BoJ series over a YYYYMM window. Stdlib only.

    Raises on transport/HTTP errors so the caller can degrade gracefully.
    """
    params = urllib.parse.urlencode(
        {"db": db, "code": code, "lang": "en", "startDate": start_yyyymm, "endDate": end_yyyymm}
    )
    url = f"{base_url.rstrip('/')}/getDataCode?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "ResearchAnalyst/0.4"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())  # type: ignore[no-any-return]


def _period_to_date(raw: Any) -> date | None:
    """BoJ survey date (20261009 daily / 202610 monthly) -> date, or None."""
    text = str(raw)
    try:
        if len(text) == 8:
            return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
        if len(text) == 6:
            return date(int(text[:4]), int(text[4:6]), 1)
    except ValueError:
        return None
    return None


def parse_latest_observation(payload: dict[str, Any]) -> tuple[date, float] | None:
    """Latest non-null (date, value) from a getDataCode response, or None.

    The API pads the requested window with nulls for dates not yet
    published; those are skipped (missing stays missing).
    """
    try:
        result_set = payload.get("RESULTSET") or []
        if not result_set:
            return None
        values = result_set[0].get("VALUES") or {}
        dates = values.get("SURVEY_DATES") or []
        observations = values.get("VALUES") or []
        best: tuple[date, float] | None = None
        for raw_date, raw_value in zip(dates, observations, strict=False):
            if raw_value is None:
                continue
            parsed_date = _period_to_date(raw_date)
            if parsed_date is None:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if best is None or parsed_date > best[0]:
                best = (parsed_date, value)
        return best
    except (TypeError, ValueError) as e:
        logger.debug("BoJ parse failed: %s", e)
        return None


def _yyyymm(day: date) -> str:
    return f"{day.year:04d}{day.month:02d}"


class BankOfJapanProvider:
    """Async facade over the BoJ Time-Series API (keyless)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.market.boj_base_url).rstrip("/")

    async def get_latest_rates(self) -> BojRates | None:
        """Latest USD/JPY spot + basic discount/loan rate.

        Windows are deliberately short (BoJ prohibits excessive access):
        ~75 days for the daily FX series, ~14 months for the policy rate
        (an administered rate that changes only on decision days).
        None only when both series fail.
        """
        today = date.today()
        end = _yyyymm(today)
        jobs = {
            "fx": (USD_JPY_DB, USD_JPY_CODE, _yyyymm(today - timedelta(days=75))),
            "policy": (POLICY_RATE_DB, POLICY_RATE_CODE, _yyyymm(today - timedelta(days=425))),
        }
        results = await asyncio.gather(
            *(
                asyncio.to_thread(_fetch_series, self._base_url, db, code, start, end)
                for db, code, start in jobs.values()
            ),
            return_exceptions=True,
        )
        rates = BojRates()
        got = False
        for name, result in zip(jobs, results, strict=True):
            if isinstance(result, BaseException):
                logger.debug("Bank of Japan %s fetch failed: %s", name, result)
                continue
            latest = parse_latest_observation(result)
            if latest is None:
                continue
            got = True
            if name == "fx":
                rates.usd_jpy_as_of, rates.usd_jpy = latest
            else:
                rates.policy_rate_as_of, rates.policy_rate_pct = latest
        return rates if got else None
