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

"""First-source provider tests: US Treasury Fiscal Data + Bank of Canada.

Fixtures are REAL responses recorded 2026-10-14 from the live keyless
APIs (Fiscal Data avg_interest_rates page; Valet V39079 + FXUSDCAD).
Offline only: transport is mocked with the recorded payloads.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import research_analyst.providers.market_data as market_data_module
from research_analyst.models import MacroSnapshot
from research_analyst.providers.boc import (
    BankOfCanadaProvider,
    _fetch_series_observations,
)
from research_analyst.providers.market_data import MarketDataProvider
from research_analyst.providers.treasury import (
    TreasuryProvider,
    parse_avg_interest_rates,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _urlopen_cm(payload: dict) -> MagicMock:
    fake = MagicMock()
    fake.read.return_value = json.dumps(payload).encode()
    cm = MagicMock()
    cm.__enter__.return_value = fake
    cm.__exit__.return_value = False
    return cm


# ---------------------------------------------------------------------------
# US Treasury Fiscal Data
# ---------------------------------------------------------------------------


def test_treasury_parse_recorded_fixture():
    result = parse_avg_interest_rates(_load("fiscaldata_avg_interest_rates.json"))
    assert result is not None
    assert result.as_of == date(2026, 9, 30)
    # Recorded values at 2026-09-30 (percent, as published).
    assert result.treasury_bills_pct == 3.870
    assert result.rate_pct_for("Treasury Notes") == 3.383
    # Only the newest record date's rows survive the multi-date page.
    assert {p.avg_interest_rate_pct for p in result.rates}
    assert len(result.rates) >= 10


def test_treasury_parse_missing_stays_missing():
    assert parse_avg_interest_rates({"data": []}) is None
    assert parse_avg_interest_rates({}) is None
    bad = {"data": [{"record_date": "2026-09-30", "security_desc": "Treasury Bills",
                     "avg_interest_rate_amt": ""}]}
    assert parse_avg_interest_rates(bad) is None


async def test_treasury_provider_uses_recorded_transport():
    payload = _load("fiscaldata_avg_interest_rates.json")
    with patch("urllib.request.urlopen", return_value=_urlopen_cm(payload)):
        result = await TreasuryProvider().get_avg_interest_rates()
    assert result is not None
    assert result.treasury_bills_pct == 3.870


async def test_treasury_provider_degrades_to_none():
    with patch("urllib.request.urlopen", side_effect=OSError("boom")):
        assert await TreasuryProvider().get_avg_interest_rates() is None


# ---------------------------------------------------------------------------
# Bank of Canada Valet
# ---------------------------------------------------------------------------


def test_boc_series_parse_recorded_fixtures():
    with patch(
        "urllib.request.urlopen",
        return_value=_urlopen_cm(_load("boc_policy_rate.json")),
    ):
        policy = _fetch_series_observations("https://www.bankofcanada.ca/valet", "V39079")
    assert policy[0] == ("2026-10-12", 2.25)

    with patch(
        "urllib.request.urlopen",
        return_value=_urlopen_cm(_load("boc_fx_usdcad.json")),
    ):
        fx = _fetch_series_observations("https://www.bankofcanada.ca/valet", "FXUSDCAD")
    assert fx[0] == ("2026-10-13", 1.4222)


async def test_boc_provider_composes_both_series():
    payloads = {
        "V39079": _load("boc_policy_rate.json"),
        "FXUSDCAD": _load("boc_fx_usdcad.json"),
    }
    with patch(
        "research_analyst.providers.boc._fetch_series_observations",
        side_effect=lambda base, series, recent=5: _series_from(payloads[series], series),
    ):
        result = await BankOfCanadaProvider().get_latest_rates()
    assert result is not None
    assert result.policy_rate_pct == 2.25
    assert result.policy_rate_as_of == date(2026, 10, 12)
    assert result.usd_cad == 1.4222
    assert result.usd_cad_as_of == date(2026, 10, 13)


def _series_from(payload: dict, series: str) -> list[tuple[str, float]]:
    out = []
    for obs in payload.get("observations", []):
        out.append((obs["d"], float(obs[series]["v"])))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


async def test_boc_provider_partial_failure_keeps_good_series():
    def flaky(base: str, series: str, recent: int = 5):
        if series == "V39079":
            raise OSError("boom")
        return _series_from(_load("boc_fx_usdcad.json"), series)

    with patch("research_analyst.providers.boc._fetch_series_observations", side_effect=flaky):
        result = await BankOfCanadaProvider().get_latest_rates()
    assert result is not None
    assert result.policy_rate_pct is None  # missing stays missing
    assert result.usd_cad == 1.4222


async def test_boc_provider_total_failure_is_none():
    with patch(
        "research_analyst.providers.boc._fetch_series_observations",
        side_effect=OSError("boom"),
    ):
        assert await BankOfCanadaProvider().get_latest_rates() is None


# ---------------------------------------------------------------------------
# Macro snapshot integration (provenance only — no existing field changes)
# ---------------------------------------------------------------------------


class _FakeTreasuryProvider:
    def __init__(self, result):
        self._result = result

    async def get_avg_interest_rates(self):
        return self._result


class _FakeBocProvider:
    def __init__(self, result):
        self._result = result

    async def get_latest_rates(self):
        return self._result


async def test_populate_first_sources_adds_provenance_only():
    from research_analyst.providers.boc import BocRates

    treasury = parse_avg_interest_rates(_load("fiscaldata_avg_interest_rates.json"))
    boc = BocRates(
        policy_rate_pct=2.25,
        policy_rate_as_of=date(2026, 10, 12),
        usd_cad=1.4222,
        usd_cad_as_of=date(2026, 10, 13),
    )
    snapshot = MacroSnapshot(as_of_date=date(2026, 10, 14), us_10y_yield=0.041)
    provider = MarketDataProvider()
    with (
        patch.object(
            market_data_module, "TreasuryProvider", lambda: _FakeTreasuryProvider(treasury)
        ),
        patch.object(market_data_module, "BankOfCanadaProvider", lambda: _FakeBocProvider(boc)),
    ):
        got = await provider._populate_first_sources(snapshot)
    assert got is True
    # Supplemental fields: fractions for rates, FX exactly as published.
    assert snapshot.treasury_avg_rates["Treasury Bills"] == 0.0387
    assert snapshot.treasury_as_of == date(2026, 9, 30)
    assert snapshot.boc_policy_rate == 0.0225
    assert snapshot.boc_usd_cad == 1.4222
    assert snapshot.boc_as_of == date(2026, 10, 13)
    assert snapshot.supplemental_sources == [
        "US Treasury Fiscal Data (average interest rates)",
        "Bank of Canada Valet (policy rate, USD/CAD)",
    ]
    # No existing field was touched.
    assert snapshot.us_10y_yield == 0.041
    assert snapshot.cpi_yoy is None


async def test_populate_first_sources_failure_leaves_fields_empty():
    snapshot = MacroSnapshot(as_of_date=date(2026, 10, 14))
    provider = MarketDataProvider()
    with (
        patch.object(market_data_module, "TreasuryProvider", lambda: _FakeTreasuryProvider(None)),
        patch.object(market_data_module, "BankOfCanadaProvider", lambda: _FakeBocProvider(None)),
    ):
        got = await provider._populate_first_sources(snapshot)
    assert got is False
    assert snapshot.treasury_avg_rates == {}
    assert snapshot.boc_policy_rate is None
    assert snapshot.supplemental_sources == []
