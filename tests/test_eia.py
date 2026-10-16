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

"""EIA provider (US energy prices, wire-the-unwired matrix §7).

Fixtures are REAL EIA API v2 responses (seriesid route), trimmed to
the newest three rows, captured 2026-10-16: WTI $101.91, Brent
$126.55, Henry Hub $3.22 — all as of 2026-10-14.
"""
# Module: tests/test_eia.py

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest

from research_analyst.config import settings
from research_analyst.providers import eia
from research_analyst.providers.eia import EiaProvider, parse_series_payload

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"eia_{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("name", "value"),
    (("wti", 101.91), ("brent", 126.55), ("henry_hub", 3.22)),
)
def test_parse_real_series(name, value):
    latest = parse_series_payload(_fixture(name))
    assert latest == (value, date(2026, 10, 14))


def test_parse_skips_nulls_and_disorder():
    payload = {
        "response": {
            "data": [
                {"period": "2026-10-10", "value": 90.0},
                {"period": "2026-10-12", "value": None},
                {"period": "2026-10-11", "value": 95.5},
                {"period": "not-a-date", "value": 1.0},
            ]
        }
    }
    assert parse_series_payload(payload) == (95.5, date(2026, 10, 11))
    assert parse_series_payload({"response": {"data": []}}) is None
    assert parse_series_payload({}) is None


def test_dormant_without_key(monkeypatch):
    monkeypatch.setattr(settings.market, "eia_api_key", "")
    assert asyncio.run(EiaProvider().get_latest_energy_prices()) is None


def test_populates_from_fixtures(monkeypatch):
    monkeypatch.setattr(settings.market, "eia_api_key", "test-key")
    by_series = {
        eia.WTI_SERIES: _fixture("wti"),
        eia.BRENT_SERIES: _fixture("brent"),
        eia.HENRY_HUB_SERIES: _fixture("henry_hub"),
    }
    monkeypatch.setattr(
        eia, "_fetch_series", lambda series_id, api_key: by_series[series_id]
    )
    prices = asyncio.run(EiaProvider().get_latest_energy_prices())
    assert prices is not None
    assert prices.wti_spot_usd == 101.91
    assert prices.brent_spot_usd == 126.55
    assert prices.henry_hub_spot_usd == 3.22
    assert prices.wti_as_of == date(2026, 10, 14)


def test_partial_failure_degrades_per_series(monkeypatch):
    monkeypatch.setattr(settings.market, "eia_api_key", "test-key")

    def flaky(series_id, api_key):
        if series_id == eia.BRENT_SERIES:
            return None
        return _fixture("wti")

    monkeypatch.setattr(eia, "_fetch_series", flaky)
    prices = asyncio.run(EiaProvider().get_latest_energy_prices())
    assert prices is not None
    assert prices.wti_spot_usd == 101.91
    assert prices.brent_spot_usd is None
