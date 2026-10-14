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

"""SDMX macro providers — ECB, Deutsche Bundesbank, Eurostat (step 2).

One small SDMX 2.1 REST client (httpx, trust_env=False) serves the two
SDMX-JSON sources; Eurostat's statistics API speaks JSON-stat 2.0, a
different shape, so it gets a thin adapter over the same HTTP helper —
NOT the SDMX parser (recorded here per the step-2 brief).

Series wired (all verified live 2026-10-14; fixtures in tests/):
  - ECB EXR  D.USD.EUR.SP00.A            EUR/USD reference rate (daily)
  - ECB FM   D.U2.EUR.4F.KR.DFR.LEV     deposit facility rate (%)
  - ECB HICP M.U2.N.000000.4D0.ANR      euro-area HICP, annual rate (%)
    (the legacy ICP flow froze at 2025-12 with the ECOICOP v2 change;
    the HICP flow is its live successor — same DSD shape, new codelists)
  - Bundesbank BBSIS 10-year Svensson zero-coupon yield estimate for
    listed Federal securities, monthly (%). Key:
    M.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A
  - Eurostat prc_hicp_minr (EU27_2020, TOTAL, RCH_A) — EU HICP y/y (%);
    prc_hicp_manr was frozen at 2025-12 by the same ECOICOP v2 change.
  - Eurostat tec00115 (EA21) — real GDP growth rate, volume (%)

Dialect notes:
  - ECB negotiates format via ?format=jsondata and answers SDMX-JSON 1.0
    ({header, dataSets, structure} at the top level).
  - The Bundesbank REJECTS format parameters (HTTP 406); it negotiates
    via the Accept header and answers SDMX-JSON 2.0 ({meta, data:{...}}).
    The parser normalises both shapes.
  - ECB's data-api host is unreachable from some egress networks; a
    failure degrades to None like every other provider here.

Design (mirrors treasury.py / boc.py):
  - Typed Pydantic results; values exactly as published (percents stay
    percent — the snapshot layer converts to fractions)
  - Graceful degradation: any failure returns None, never raises
  - Missing data stays missing — null observations are skipped, never
    zeroed; the latest NON-NULL observation wins
"""
# Module: research_analyst/providers/sdmx.py | Version: 0.1.0 | Updated: 2026-10-14

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel

from ..config import settings

logger = logging.getLogger(__name__)

ECB_SOURCE_NAME = "ECB Data Portal"
BUNDESBANK_SOURCE_NAME = "Deutsche Bundesbank SDMX"
EUROSTAT_SOURCE_NAME = "Eurostat Statistics API"

ECB_EXR_FLOW = "EXR"
ECB_EUR_USD_KEY = "D.USD.EUR.SP00.A"
ECB_FM_FLOW = "FM"
ECB_DFR_KEY = "D.U2.EUR.4F.KR.DFR.LEV"
ECB_HICP_FLOW = "HICP"
ECB_HICP_KEY = "M.U2.N.000000.4D0.ANR"

BUNDESBANK_BBSIS_FLOW = "BBSIS"
BUNDESBANK_BUND_10Y_KEY = "M.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A"

EUROSTAT_HICP_DATASET = "prc_hicp_minr"
EUROSTAT_HICP_GEO = "EU27_2020"
EUROSTAT_GDP_DATASET = "tec00115"
EUROSTAT_GDP_GEO = "EA21"


class SdmxObservation(BaseModel):
    """The latest observation of one SDMX series."""

    series_key: str
    period: str  # as published: YYYY-MM-DD (daily) or YYYY-MM (monthly)
    value: float  # as published


def _fetch_json(url: str, accept: str = "application/json") -> dict[str, Any]:
    """GET a JSON document. httpx with trust_env=False (sandbox proxies
    must never reroute these calls). Raises on transport/HTTP errors."""
    with httpx.Client(trust_env=False, timeout=20.0) as client:
        resp = client.get(url, headers={"Accept": accept, "User-Agent": "ResearchAnalyst/0.4"})
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


def _structure_and_datasets(payload: dict[str, Any]) -> tuple[dict[str, Any], list[Any]]:
    """Locate (structure, dataSets) in either SDMX-JSON dialect."""
    if "structure" in payload and "dataSets" in payload:  # 1.0 (ECB)
        return payload["structure"], payload["dataSets"]
    data = payload.get("data") or {}  # 2.0 (Bundesbank)
    return data.get("structure") or {}, data.get("dataSets") or []


def parse_sdmx_latest(payload: dict[str, Any], series_key: str) -> SdmxObservation | None:
    """Latest non-null observation for ``series_key`` in an SDMX-JSON payload.

    Series are keyed by dimension-index tuples; the requested key is
    rebuilt from the structure's dimension values and must match exactly.
    Returns None when the series or any usable observation is absent.
    """
    try:
        structure, datasets = _structure_and_datasets(payload)
        dimensions = structure["dimensions"]
        series_dims = dimensions["series"]
        obs_values = dimensions["observation"][0]["values"]
        periods = [str(v["id"]) for v in obs_values]
        for dataset in datasets:
            for index_key, series in (dataset.get("series") or {}).items():
                indices = [int(p) for p in index_key.split(":")]
                key = ".".join(
                    str(series_dims[i]["values"][indices[i]]["id"]) for i in range(len(indices))
                )
                if key != series_key:
                    continue
                best: SdmxObservation | None = None
                for obs_index, obs in (series.get("observations") or {}).items():
                    if not obs or obs[0] is None:
                        continue  # missing stays missing
                    period = periods[int(obs_index)]
                    if best is None or period > best.period:
                        best = SdmxObservation(
                            series_key=key, period=period, value=float(obs[0])
                        )
                return best
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.debug("SDMX parse failed for %s: %s", series_key, e)
    return None


def _period_start(period: str) -> date | None:
    """Period string -> its first day (YYYY-MM-DD / YYYY-MM / YYYY)."""
    try:
        parts = period.split("-")
        if len(parts) == 3:
            return date.fromisoformat(period)
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
        return date(int(parts[0]), 1, 1)
    except (ValueError, IndexError):
        return None


class SdmxClient:
    """Minimal SDMX 2.1 REST client for latest-value fetches."""

    def __init__(self, base_url: str, *, format_param: bool) -> None:
        self._base_url = base_url.rstrip("/")
        self._format_param = format_param

    def fetch_latest(self, flow: str, key: str, last_n: int = 3) -> SdmxObservation | None:
        """Blocking latest-observation fetch. Raises on transport errors."""
        if self._format_param:  # ECB style: ?format=jsondata
            url = (
                f"{self._base_url}/data/{flow}/{key}"
                f"?format=jsondata&lastNObservations={last_n}"
            )
            payload = _fetch_json(url, accept="application/vnd.sdmx.data+json")
        else:  # Bundesbank style: Accept negotiation, no format parameter
            url = (
                f"{self._base_url}/data/{flow}/{key}"
                f"?detail=dataonly&lastNObservations={last_n}"
            )
            payload = _fetch_json(url, accept="application/json")
        return parse_sdmx_latest(payload, key)


# ---------------------------------------------------------------------------
# ECB
# ---------------------------------------------------------------------------


class EcbMacro(BaseModel):
    """Latest ECB reference values (percent / FX exactly as published)."""

    eur_usd: float | None = None  # USD per 1 EUR (ECB reference rate)
    eur_usd_as_of: date | None = None
    deposit_facility_rate_pct: float | None = None
    deposit_facility_as_of: date | None = None
    hicp_yoy_pct: float | None = None  # euro area, annual rate of change
    hicp_as_of: date | None = None  # first day of the reference month
    source: str = ECB_SOURCE_NAME


class EcbProvider:
    """Async facade over the ECB Data Portal SDMX API (keyless)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._client = SdmxClient(
            base_url or settings.market.ecb_base_url, format_param=True
        )

    async def get_latest_macro(self) -> EcbMacro | None:
        """Latest EUR/USD, deposit facility rate, and HICP y/y.

        Each series degrades independently; None only when all fail.
        """
        jobs = {
            "eur_usd": (ECB_EXR_FLOW, ECB_EUR_USD_KEY),
            "dfr": (ECB_FM_FLOW, ECB_DFR_KEY),
            "hicp": (ECB_HICP_FLOW, ECB_HICP_KEY),
        }
        results = await asyncio.gather(
            *(
                asyncio.to_thread(self._client.fetch_latest, flow, key)
                for flow, key in jobs.values()
            ),
            return_exceptions=True,
        )
        macro = EcbMacro()
        got = False
        for name, result in zip(jobs, results, strict=True):
            if isinstance(result, BaseException) or result is None:
                if isinstance(result, BaseException):
                    logger.debug("ECB %s fetch failed: %s", name, result)
                continue
            got = True
            if name == "eur_usd":
                macro.eur_usd = result.value
                macro.eur_usd_as_of = _period_start(result.period)
            elif name == "dfr":
                macro.deposit_facility_rate_pct = result.value
                macro.deposit_facility_as_of = _period_start(result.period)
            else:
                macro.hicp_yoy_pct = result.value
                macro.hicp_as_of = _period_start(result.period)
        return macro if got else None


# ---------------------------------------------------------------------------
# Deutsche Bundesbank
# ---------------------------------------------------------------------------


class BundesbankMacro(BaseModel):
    """Latest Bundesbank values (percent, as published)."""

    bund_10y_yield_pct: float | None = None  # Svensson estimate, monthly
    bund_10y_as_of: date | None = None  # first day of the reference month
    source: str = BUNDESBANK_SOURCE_NAME


class BundesbankProvider:
    """Async facade over the Bundesbank SDMX web service (keyless)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._client = SdmxClient(
            base_url or settings.market.bundesbank_base_url, format_param=False
        )

    async def get_latest_macro(self) -> BundesbankMacro | None:
        """Latest 10-year Bund yield estimate, or None on any failure."""
        try:
            obs = await asyncio.to_thread(
                self._client.fetch_latest, BUNDESBANK_BBSIS_FLOW, BUNDESBANK_BUND_10Y_KEY
            )
        except Exception as e:
            logger.debug("Bundesbank BBSIS fetch failed: %s", e)
            return None
        if obs is None:
            return None
        return BundesbankMacro(
            bund_10y_yield_pct=obs.value, bund_10y_as_of=_period_start(obs.period)
        )


# ---------------------------------------------------------------------------
# Eurostat — JSON-stat adapter (NOT SDMX; see module docstring)
# ---------------------------------------------------------------------------


def parse_jsonstat_latest(payload: dict[str, Any]) -> tuple[str, float] | None:
    """Latest (time, value) in a JSON-stat 2.0 payload, or None.

    Decodes the flat value index across all dimensions generically, so
    server-side filters (geo/unit/item) need no special handling here.
    """
    try:
        dims: list[str] = payload["id"]
        sizes: list[int] = payload["size"]
        categories: dict[str, list[str]] = {}
        for dim in dims:
            index = payload["dimension"][dim]["category"]["index"]
            if isinstance(index, dict):
                categories[dim] = [k for k, _ in sorted(index.items(), key=lambda kv: kv[1])]
            else:
                categories[dim] = [str(k) for k in index]
        best: tuple[str, float] | None = None
        for flat, raw in (payload.get("value") or {}).items():
            if raw is None:
                continue
            remainder = int(flat)
            coords: dict[str, str] = {}
            for dim, size in zip(reversed(dims), reversed(sizes), strict=True):
                coords[dim] = categories[dim][remainder % size]
                remainder //= size
            period = coords.get("time", "")
            if best is None or period > best[0]:
                best = (period, float(raw))
        return best
    except (KeyError, TypeError, ValueError) as e:
        logger.debug("JSON-stat parse failed: %s", e)
        return None


class EurostatMacro(BaseModel):
    """Latest Eurostat values (percent, as published)."""

    hicp_yoy_pct: float | None = None  # EU27 all-items, annual rate
    hicp_as_of: date | None = None  # first day of the reference month
    gdp_growth_pct: float | None = None  # EA21 real GDP growth, annual
    gdp_as_of: date | None = None  # first day of the reference year
    source: str = EUROSTAT_SOURCE_NAME


class EurostatProvider:
    """Async facade over the Eurostat statistics API (keyless).

    JSON-stat adapter: same HTTP helper as the SDMX client, different
    payload shape, parsed by parse_jsonstat_latest.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.market.eurostat_base_url).rstrip("/")

    def _dataset_url(self, dataset: str, params: dict[str, str]) -> str:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self._base_url}/statistics/1.0/data/{dataset}?{query}"

    async def get_latest_macro(self) -> EurostatMacro | None:
        """Latest EU HICP y/y + EA real GDP growth. Independent degradation."""
        year = date.today().year
        urls = {
            "hicp": self._dataset_url(
                EUROSTAT_HICP_DATASET,
                {
                    "lang": "EN",
                    "coicop18": "TOTAL",
                    "unit": "RCH_A",
                    "geo": EUROSTAT_HICP_GEO,
                    "sinceTimePeriod": f"{year - 2}-01",
                },
            ),
            "gdp": self._dataset_url(
                EUROSTAT_GDP_DATASET,
                {
                    "lang": "EN",
                    "geo": EUROSTAT_GDP_GEO,
                    "sinceTimePeriod": str(year - 7),
                },
            ),
        }
        results = await asyncio.gather(
            *(asyncio.to_thread(_fetch_json, url) for url in urls.values()),
            return_exceptions=True,
        )
        macro = EurostatMacro()
        got = False
        for name, result in zip(urls, results, strict=True):
            if isinstance(result, BaseException):
                logger.debug("Eurostat %s fetch failed: %s", name, result)
                continue
            latest = parse_jsonstat_latest(result)
            if latest is None:
                continue
            got = True
            period, value = latest
            if name == "hicp":
                macro.hicp_yoy_pct = value
                macro.hicp_as_of = _period_start(period)
            else:
                macro.gdp_growth_pct = value
                macro.gdp_as_of = _period_start(period)
        return macro if got else None
