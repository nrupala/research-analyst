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

"""Tests for the Statistics Canada WDS provider (step 7).

The fixture is the REAL getDataFromVectorsAndLatestNPeriods
response captured from www150.statcan.gc.ca on 2026-10-16:
All-items CPI index 169.8 at 2026-08 vs 164.8 at 2025-08
(12-month change +3.03...%) and the seasonally adjusted
unemployment rate 6.5% at 2026-09. Vector identities were
confirmed via getSeriesInfoFromVector.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

from research_analyst.providers import statcan as statcan_module
from research_analyst.providers.statcan import (
    StatCanProvider,
    parse_vectors_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"
PAYLOAD = json.loads((FIXTURES / "statcan_wds.json").read_text())


def test_parse_computes_cpi_yoy_from_index():
    macro = parse_vectors_payload(PAYLOAD)
    assert macro.cpi_as_of == date(2026, 8, 1)
    assert macro.cpi_yoy_pct is not None
    assert abs(macro.cpi_yoy_pct - (169.8 / 164.8 - 1.0) * 100.0) < 1e-9


def test_parse_unemployment_takes_newest_point():
    macro = parse_vectors_payload(PAYLOAD)
    assert macro.unemployment_pct == 6.5
    assert macro.unemployment_as_of == date(2026, 9, 1)


def test_cpi_missing_year_ago_point_stays_none():
    trimmed = json.loads(json.dumps(PAYLOAD))
    for item in trimmed:
        if item["object"]["vectorId"] == statcan_module.CPI_VECTOR:
            item["object"]["vectorDataPoint"] = item["object"][
                "vectorDataPoint"
            ][-3:]
    macro = parse_vectors_payload(trimmed)
    assert macro.cpi_yoy_pct is None
    assert macro.unemployment_pct == 6.5


def test_provider_none_on_transport_failure(monkeypatch):
    def dead(base_url):
        raise OSError("boom")

    monkeypatch.setattr(statcan_module, "_fetch_vectors", dead)
    macro = asyncio.run(
        StatCanProvider(base_url="https://example.test").get_latest_macro()
    )
    assert macro is None


def test_provider_assembles_from_fixture(monkeypatch):
    monkeypatch.setattr(
        statcan_module, "_fetch_vectors", lambda base_url: PAYLOAD
    )
    macro = asyncio.run(
        StatCanProvider(base_url="https://example.test").get_latest_macro()
    )
    assert macro is not None
    assert macro.unemployment_pct == 6.5
    assert macro.cpi_yoy_pct is not None and macro.cpi_yoy_pct > 3.0


# ---- Population integration (mirrors tests/test_bcb.py) ----------

from research_analyst.models import MacroSnapshot  # noqa: E402
from research_analyst.providers import market_data as market_data_module  # noqa: E402


def test_population_fills_statcan_as_fractions(monkeypatch):
    monkeypatch.setattr(
        statcan_module, "_fetch_vectors", lambda base_url: PAYLOAD
    )

    async def _run():
        snapshot = MacroSnapshot(as_of_date=date(2026, 10, 16))
        got = await market_data_module.MarketDataProvider._populate_first_sources(
            object(), snapshot
        )
        return got, snapshot

    got, snapshot = asyncio.run(_run())
    assert got is True
    assert snapshot.statcan_cpi_yoy is not None
    assert abs(snapshot.statcan_cpi_yoy - (169.8 / 164.8 - 1.0)) < 1e-9
    assert snapshot.statcan_cpi_as_of == date(2026, 8, 1)
    assert snapshot.statcan_unemployment_rate == 6.5 / 100.0
    assert snapshot.statcan_unemployment_as_of == date(2026, 9, 1)
    assert (
        "Statistics Canada WDS (CPI, unemployment rate)"
        in snapshot.supplemental_sources
    )
