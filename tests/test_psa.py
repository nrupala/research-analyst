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

"""Tests for the PSA OpenSTAT provider (macro supplement step 6).

Fixtures are the REAL table metadata + query responses captured
from openstat.psa.gov.ph on 2026-10-16 (large value lists trimmed
in the metadata only, shape preserved): CPI YoY 7.2% at 2026-09
(missing months arrive as '..'), unemployment 5.269% at 2026-08
(missing months as '.'). Year codes are index-coded per table and
resolved from metadata — the CPI table's 2026 is code '7', the
LFS table's is '21'; both fixtures pin that difference.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

from research_analyst.providers import psa as psa_module
from research_analyst.providers.psa import (
    PsaProvider,
    _month_codes,
    _newest_year,
    parse_rows,
)

FIXTURES = Path(__file__).parent / "fixtures"
CPI_META = json.loads((FIXTURES / "psa_cpi_meta.json").read_text())
CPI_ROWS = json.loads((FIXTURES / "psa_cpi.json").read_text())
LFS_META = json.loads((FIXTURES / "psa_lfs_meta.json").read_text())
LFS_ROWS = json.loads((FIXTURES / "psa_lfs.json").read_text())


def test_newest_year_resolves_per_table_codes():
    assert _newest_year(CPI_META) == ("7", 2026)
    assert _newest_year(LFS_META) == ("21", 2026)


def test_month_codes_skip_averages():
    cpi_months = _month_codes(CPI_META, "Period")
    assert len(cpi_months) == 12  # 'Ave' excluded
    assert cpi_months["8"] == 9  # Sep
    lfs_months = _month_codes(LFS_META, "Month")
    assert len(lfs_months) == 12  # 'Annual' excluded
    assert lfs_months["7"] == 8  # August


def test_parse_cpi_takes_newest_present_month():
    months = _month_codes(CPI_META, "Period")
    assert parse_rows(CPI_ROWS, 2026, months, ("Year", "Period")) == (
        date(2026, 9, 1),
        7.2,
    )


def test_parse_lfs_takes_newest_present_month():
    months = _month_codes(LFS_META, "Month")
    assert parse_rows(LFS_ROWS, 2026, months, ("Year", "Month")) == (
        date(2026, 8, 1),
        5.269,
    )


def _fake_transport(fail_table: str | None = None):
    def fake_get(base_url, path):
        if path == fail_table:
            raise OSError("boom")
        return CPI_META if "ACP23" in path else LFS_META

    def fake_post(base_url, path, selections):
        return CPI_ROWS if "ACP23" in path else LFS_ROWS

    return fake_get, fake_post


async def _macro(monkeypatch, fail_table=None):
    fake_get, fake_post = _fake_transport(fail_table)
    monkeypatch.setattr(psa_module, "_get_json", fake_get)
    monkeypatch.setattr(psa_module, "_post_query", fake_post)
    return await PsaProvider(base_url="https://example.test").get_latest_macro()


def test_provider_assembles_both_series(monkeypatch):
    macro = asyncio.run(_macro(monkeypatch))
    assert macro is not None
    assert macro.cpi_yoy_pct == 7.2
    assert macro.cpi_as_of == date(2026, 9, 1)
    assert macro.unemployment_pct == 5.269
    assert macro.unemployment_as_of == date(2026, 8, 1)


def test_provider_tolerates_one_dead_table(monkeypatch):
    macro = asyncio.run(_macro(monkeypatch, fail_table=psa_module.CPI_TABLE))
    assert macro is not None
    assert macro.cpi_yoy_pct is None
    assert macro.unemployment_pct == 5.269


def test_provider_none_when_both_tables_dead(monkeypatch):
    def dead(base_url, path, *args):
        raise OSError("boom")

    monkeypatch.setattr(psa_module, "_get_json", dead)
    monkeypatch.setattr(psa_module, "_post_query", dead)
    macro = asyncio.run(
        PsaProvider(base_url="https://example.test").get_latest_macro()
    )
    assert macro is None


# ---- Population integration (mirrors tests/test_bcb.py) ----------

from research_analyst.models import MacroSnapshot  # noqa: E402
from research_analyst.providers import market_data as market_data_module  # noqa: E402


def test_population_fills_psa_as_fractions(monkeypatch):
    fake_get, fake_post = _fake_transport()
    monkeypatch.setattr(psa_module, "_get_json", fake_get)
    monkeypatch.setattr(psa_module, "_post_query", fake_post)

    async def _run():
        snapshot = MacroSnapshot(as_of_date=date(2026, 10, 16))
        got = await market_data_module.MarketDataProvider._populate_first_sources(
            object(), snapshot
        )
        return got, snapshot

    got, snapshot = asyncio.run(_run())
    assert got is True
    assert snapshot.psa_cpi_yoy == 7.2 / 100.0
    assert snapshot.psa_cpi_as_of == date(2026, 9, 1)
    assert snapshot.psa_unemployment_rate == 5.269 / 100.0
    assert snapshot.psa_unemployment_as_of == date(2026, 8, 1)
    assert (
        "Philippine Statistics Authority OpenSTAT (CPI, unemployment rate)"
        in snapshot.supplemental_sources
    )
