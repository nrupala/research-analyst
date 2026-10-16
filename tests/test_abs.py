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

"""Tests for the ABS Data API provider (macro supplement step 5).

Fixtures are the REAL keyed responses captured from data.api.
abs.gov.au on 2026-10-16 (public statistics, CC BY 4.0 Australia):
CPI All-groups YoY 3.9% at 2026-Q2; unemployment rate (persons,
seasonally adjusted) 4.71834873% at 2026-09. Series keys were
decoded from the live DSD codelists (CL_CPI_* / CL_LF_*), not
assumed.
"""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from research_analyst.providers import abs as abs_module
from research_analyst.providers.abs import AbsProvider, parse_sdmx_csv

FIXTURES = Path(__file__).parent / "fixtures"
CPI_CSV = (FIXTURES / "abs_cpi_q.csv").read_text()
LF_CSV = (FIXTURES / "abs_lf.csv").read_text()


def test_parse_cpi_takes_newest_quarter_end():
    assert parse_sdmx_csv(CPI_CSV) == (date(2026, 6, 30), 3.9)


def test_parse_unemployment_takes_newest_month():
    assert parse_sdmx_csv(LF_CSV) == (date(2026, 9, 1), 4.71834873)


def test_parse_skips_junk_and_empty():
    text = (
        "TIME_PERIOD,OBS_VALUE\n"
        "not-a-period,5.0\n"
        "2026-Q1,\n"
        "2026-Q2,3.9\n"
    )
    assert parse_sdmx_csv(text) == (date(2026, 6, 30), 3.9)
    assert parse_sdmx_csv("") is None
    assert parse_sdmx_csv("TIME_PERIOD,OBS_VALUE\n") is None


def _fake_fetch_factory(fail_flow: str | None = None):
    def fake_fetch(base_url, dataflow, key, start_period):
        if dataflow == fail_flow:
            raise OSError("boom")
        return CPI_CSV if "CPI_Q" in dataflow else LF_CSV

    return fake_fetch


async def _macro(monkeypatch, fail_flow=None):
    monkeypatch.setattr(
        abs_module, "_fetch_csv", _fake_fetch_factory(fail_flow)
    )
    return await AbsProvider(base_url="https://example.test").get_latest_macro()


def test_provider_assembles_both_series(monkeypatch):
    macro = asyncio.run(_macro(monkeypatch))
    assert macro is not None
    assert macro.cpi_yoy_pct == 3.9
    assert macro.cpi_as_of == date(2026, 6, 30)
    assert macro.unemployment_pct == 4.71834873
    assert macro.unemployment_as_of == date(2026, 9, 1)


def test_provider_tolerates_one_dead_series(monkeypatch):
    macro = asyncio.run(_macro(monkeypatch, fail_flow=abs_module.CPI_DATAFLOW))
    assert macro is not None
    assert macro.cpi_yoy_pct is None
    assert macro.unemployment_pct == 4.71834873


def test_provider_none_when_all_series_dead(monkeypatch):
    def dead_fetch(base_url, dataflow, key, start_period):
        raise OSError("boom")

    monkeypatch.setattr(abs_module, "_fetch_csv", dead_fetch)
    macro = asyncio.run(
        AbsProvider(base_url="https://example.test").get_latest_macro()
    )
    assert macro is None


# ---- Population integration (mirrors tests/test_bcb.py) ----------

from research_analyst.models import MacroSnapshot  # noqa: E402
from research_analyst.providers import market_data as market_data_module  # noqa: E402


def test_population_fills_abs_as_fractions(monkeypatch):
    monkeypatch.setattr(
        abs_module, "_fetch_csv", _fake_fetch_factory()
    )

    async def _run():
        snapshot = MacroSnapshot(as_of_date=date(2026, 10, 16))
        got = await market_data_module.MarketDataProvider._populate_first_sources(
            object(), snapshot
        )
        return got, snapshot

    got, snapshot = asyncio.run(_run())
    assert got is True
    assert snapshot.abs_cpi_yoy == 0.039
    assert snapshot.abs_cpi_as_of == date(2026, 6, 30)
    assert snapshot.abs_unemployment_rate == 4.71834873 / 100.0
    assert snapshot.abs_unemployment_as_of == date(2026, 9, 1)
    assert (
        "Australian Bureau of Statistics Data API (CPI, unemployment rate)"
        in snapshot.supplemental_sources
    )
