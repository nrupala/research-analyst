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

"""BCB SGS provider tests — fixtures are the REAL API responses
captured live on 2026-10-16 (Selic strip flat at 13.75 across the
captured window 2026-10-30 → 2026-11-04; IPCA 12m rows Jul–Sep 2026;
PTAX 5.0521 on 2026-10-15).

The Selic series is a FORWARD strip (the current target applied to
coming days), so the parser must never present a future-dated row
as the current rate: newest row dated today or earlier wins.
"""
# Module: tests/test_bcb.py

import asyncio
from datetime import date

from research_analyst.models import MacroSnapshot
from research_analyst.providers import bcb
from research_analyst.providers.bcb import BcbProvider, parse_sgs_payload
from research_analyst.providers.market_data import MarketDataProvider

TODAY = date(2026, 10, 16)

SELIC_STRIP = [
    {"data": "16/10/2026", "valor": "13.75"},
    {"data": "30/10/2026", "valor": "13.75"},
    {"data": "04/11/2026", "valor": "13.75"},
]
# The real date-range response shape (2026-09-16 -> 2026-10-16
# window, captured live): the Selic was CUT inside the window —
# 14.00 at the start, 13.75 at the end. The newest row wins.
SELIC_RANGE = [
    {"data": "16/09/2026", "valor": "14.00"},
    {"data": "15/10/2026", "valor": "13.75"},
    {"data": "16/10/2026", "valor": "13.75"},
]
IPCA_ROWS = [
    {"data": "01/07/2026", "valor": "4.44"},
    {"data": "01/08/2026", "valor": "4.22"},
    {"data": "01/09/2026", "valor": "4.58"},
]
PTAX_ROWS = [{"data": "15/10/2026", "valor": "5.0521"}]


def test_parse_selic_skips_future_strip():
    assert parse_sgs_payload(SELIC_STRIP, today=TODAY) == (TODAY, 13.75)


def test_parse_selic_range_takes_newest_not_first():
    assert parse_sgs_payload(SELIC_RANGE, today=TODAY) == (TODAY, 13.75)


def test_parse_all_future_is_missing_not_current():
    future_only = [{"data": "04/11/2026", "valor": "13.75"}]
    assert parse_sgs_payload(future_only, today=TODAY) is None


def test_parse_ipca_and_ptax_goldens():
    assert parse_sgs_payload(IPCA_ROWS, today=TODAY) == (date(2026, 9, 1), 4.58)
    assert parse_sgs_payload(PTAX_ROWS, today=TODAY) == (date(2026, 10, 15), 5.0521)


def test_parse_skips_junk_and_disorder():
    rows = [
        {"data": "15/10/2026", "valor": "5.0521"},
        {"data": "14/10/2026", "valor": None},
        {"data": "not-a-date", "valor": "9.99"},
        {"data": "13/10/2026", "valor": "5.0100"},
    ]
    assert parse_sgs_payload(rows, today=TODAY) == (date(2026, 10, 15), 5.0521)
    assert parse_sgs_payload([], today=TODAY) is None
    assert parse_sgs_payload({"not": "a list"}, today=TODAY) is None


def _fake_fetch_factory(by_series):
    def fake(base_url, series, recent):
        result = by_series[series]
        if isinstance(result, Exception):
            raise result
        return result

    return fake


def test_provider_assembles_all_series(monkeypatch):
    monkeypatch.setattr(
        bcb,
        "_fetch_series",
        _fake_fetch_factory(
            {
                bcb.SELIC_SERIES: SELIC_STRIP,
                bcb.IPCA_12M_SERIES: IPCA_ROWS,
                bcb.USD_BRL_SERIES: PTAX_ROWS,
            }
        ),
    )
    macro = asyncio.run(BcbProvider().get_latest_macro())
    assert macro is not None
    assert macro.selic_target_pct == 13.75
    assert macro.ipca_12m_pct == 4.58
    assert macro.usd_brl_ptax == 5.0521


def test_provider_degrades_per_series(monkeypatch):
    monkeypatch.setattr(
        bcb,
        "_fetch_series",
        _fake_fetch_factory(
            {
                bcb.SELIC_SERIES: SELIC_STRIP,
                bcb.IPCA_12M_SERIES: RuntimeError("boom"),
                bcb.USD_BRL_SERIES: PTAX_ROWS,
            }
        ),
    )
    macro = asyncio.run(BcbProvider().get_latest_macro())
    assert macro is not None
    assert macro.selic_target_pct == 13.75
    assert macro.ipca_12m_pct is None


def test_population_fills_snapshot_as_fractions(monkeypatch):
    monkeypatch.setattr(
        bcb,
        "_fetch_series",
        _fake_fetch_factory(
            {
                bcb.SELIC_SERIES: SELIC_STRIP,
                bcb.IPCA_12M_SERIES: IPCA_ROWS,
                bcb.USD_BRL_SERIES: PTAX_ROWS,
            }
        ),
    )
    snapshot = MacroSnapshot(as_of_date=TODAY)
    asyncio.run(MarketDataProvider()._populate_first_sources(snapshot))
    assert snapshot.bcb_selic_rate == 0.1375
    assert snapshot.bcb_ipca_yoy == 0.0458
    assert snapshot.bcb_usd_brl == 5.0521
    assert any(
        s.startswith("Banco Central do Brasil") for s in snapshot.supplemental_sources
    )
