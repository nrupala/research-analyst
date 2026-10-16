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

"""First-source step-2 tests: SDMX layer (ECB/Bundesbank), Eurostat, BoJ,
and FRED per-series rights gating.

Fixtures are REAL responses recorded 2026-10-14 from the live keyless
APIs (ECB Data Portal, Bundesbank SDMX, Eurostat statistics API, BoJ
Time-Series API). Offline only: transport is mocked with the recorded
payloads.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

import research_analyst.providers.market_data as market_data_module
import research_analyst.providers.sdmx as sdmx_module
from research_analyst.models import MacroSnapshot
from research_analyst.providers.boj import (
    BankOfJapanProvider,
    parse_latest_observation,
)
from research_analyst.providers.market_data import MarketDataProvider
from research_analyst.providers.sdmx import (
    BUNDESBANK_BUND_10Y_KEY,
    ECB_DFR_KEY,
    ECB_EUR_USD_KEY,
    ECB_HICP_KEY,
    BundesbankProvider,
    EcbProvider,
    EurostatProvider,
    SdmxClient,
    parse_jsonstat_latest,
    parse_sdmx_latest,
)
from research_analyst.providers.source_registry import (
    FRED_SERIES_RIGHTS,
    RIGHTS_PUBLIC_DOMAIN,
    RIGHTS_THIRD_PARTY_COPYRIGHTED,
    fred_series_displayable,
    fred_series_rights,
    primary_entry,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# SDMX-JSON parsing (both dialects) against recorded fixtures
# ---------------------------------------------------------------------------


def test_ecb_fixtures_parse_to_recorded_values():
    exr = parse_sdmx_latest(_load("ecb_exr.json"), ECB_EUR_USD_KEY)
    assert exr is not None
    assert (exr.period, exr.value) == ("2026-10-13", 1.1188)

    dfr = parse_sdmx_latest(_load("ecb_fm_dfr.json"), ECB_DFR_KEY)
    assert dfr is not None
    assert (dfr.period, dfr.value) == ("2026-10-14", 2.5)

    hicp = parse_sdmx_latest(_load("ecb_hicp.json"), ECB_HICP_KEY)
    assert hicp is not None
    assert (hicp.period, hicp.value) == ("2026-09", 3.8)


def test_bundesbank_fixture_parses_to_recorded_value():
    obs = parse_sdmx_latest(_load("bundesbank_bbsis_10y.json"), BUNDESBANK_BUND_10Y_KEY)
    assert obs is not None
    assert (obs.period, obs.value) == ("2026-09", 3.64)


def test_sdmx_parse_missing_stays_missing():
    assert parse_sdmx_latest({}, ECB_EUR_USD_KEY) is None
    assert parse_sdmx_latest({"dataSets": [], "structure": {}}, ECB_EUR_USD_KEY) is None
    # A real payload queried for a series it does not contain.
    assert parse_sdmx_latest(_load("ecb_exr.json"), ECB_DFR_KEY) is None


def test_sdmx_client_negotiation_differs_by_source():
    seen: list[tuple[str, str]] = []

    def fake_fetch(url: str, accept: str = "application/json") -> dict:
        seen.append((url, accept))
        return _load("ecb_exr.json")

    with patch.object(sdmx_module, "_fetch_json", side_effect=fake_fetch):
        ecb = SdmxClient("https://data-api.ecb.europa.eu/service", format_param=True)
        obs = ecb.fetch_latest("EXR", ECB_EUR_USD_KEY)
    assert obs is not None and obs.value == 1.1188
    assert "format=jsondata" in seen[0][0]  # ECB negotiates via query param

    seen.clear()
    with patch.object(sdmx_module, "_fetch_json", side_effect=fake_fetch):
        bbk = SdmxClient("https://api.statistiken.bundesbank.de/rest", format_param=False)
        bbk.fetch_latest("EXR", ECB_EUR_USD_KEY)
    assert "format=" not in seen[0][0]  # Bundesbank 406s on format params
    assert seen[0][1] == "application/json"


# ---------------------------------------------------------------------------
# SDMX providers composed over mocked transport
# ---------------------------------------------------------------------------


def _sdmx_transport(url: str, accept: str = "application/json") -> dict:
    if "/EXR/" in url:
        return _load("ecb_exr.json")
    if "/FM/" in url:
        return _load("ecb_fm_dfr.json")
    if "/HICP/" in url:
        return _load("ecb_hicp.json")
    if "BBSIS" in url:
        return _load("bundesbank_bbsis_10y.json")
    raise AssertionError(f"unexpected URL {url}")


async def test_ecb_provider_composes_all_series():
    with patch.object(sdmx_module, "_fetch_json", side_effect=_sdmx_transport):
        macro = await EcbProvider().get_latest_macro()
    assert macro is not None
    assert macro.eur_usd == 1.1188
    assert macro.eur_usd_as_of == date(2026, 10, 13)
    assert macro.deposit_facility_rate_pct == 2.5
    assert macro.deposit_facility_as_of == date(2026, 10, 14)
    assert macro.hicp_yoy_pct == 3.8
    assert macro.hicp_as_of == date(2026, 9, 1)


async def test_ecb_provider_partial_failure_keeps_good_series():
    def flaky(url: str, accept: str = "application/json") -> dict:
        if "/FM/" in url:
            raise OSError("boom")
        return _sdmx_transport(url, accept)

    with patch.object(sdmx_module, "_fetch_json", side_effect=flaky):
        macro = await EcbProvider().get_latest_macro()
    assert macro is not None
    assert macro.deposit_facility_rate_pct is None  # missing stays missing
    assert macro.eur_usd == 1.1188
    assert macro.hicp_yoy_pct == 3.8


async def test_ecb_provider_total_failure_is_none():
    with patch.object(sdmx_module, "_fetch_json", side_effect=OSError("boom")):
        assert await EcbProvider().get_latest_macro() is None


async def test_bundesbank_provider_uses_recorded_transport():
    with patch.object(sdmx_module, "_fetch_json", side_effect=_sdmx_transport):
        macro = await BundesbankProvider().get_latest_macro()
    assert macro is not None
    assert macro.bund_10y_yield_pct == 3.64
    assert macro.bund_10y_as_of == date(2026, 9, 1)


async def test_bundesbank_provider_degrades_to_none():
    with patch.object(sdmx_module, "_fetch_json", side_effect=OSError("boom")):
        assert await BundesbankProvider().get_latest_macro() is None


# ---------------------------------------------------------------------------
# Eurostat JSON-stat adapter
# ---------------------------------------------------------------------------


def test_eurostat_fixtures_parse_to_recorded_values():
    assert parse_jsonstat_latest(_load("eurostat_hicp_minr.json")) == ("2026-08", 3.2)
    assert parse_jsonstat_latest(_load("eurostat_tec00115_gdp.json")) == ("2025", 1.2)
    assert parse_jsonstat_latest({}) is None


def _eurostat_transport(url: str, accept: str = "application/json") -> dict:
    if "prc_hicp_minr" in url:
        return _load("eurostat_hicp_minr.json")
    if "tec00115" in url:
        return _load("eurostat_tec00115_gdp.json")
    raise AssertionError(f"unexpected URL {url}")


async def test_eurostat_provider_composes_both_datasets():
    with patch.object(sdmx_module, "_fetch_json", side_effect=_eurostat_transport):
        macro = await EurostatProvider().get_latest_macro()
    assert macro is not None
    assert macro.hicp_yoy_pct == 3.2
    assert macro.hicp_as_of == date(2026, 8, 1)
    assert macro.gdp_growth_pct == 1.2
    assert macro.gdp_as_of == date(2025, 1, 1)


async def test_eurostat_provider_degrades_to_none():
    with patch.object(sdmx_module, "_fetch_json", side_effect=OSError("boom")):
        assert await EurostatProvider().get_latest_macro() is None


# ---------------------------------------------------------------------------
# Bank of Japan
# ---------------------------------------------------------------------------


def test_boj_fixtures_parse_to_recorded_values():
    fx = parse_latest_observation(_load("boj_fm08_usdjpy.json"))
    assert fx == (date(2026, 10, 9), 158.34)
    policy = parse_latest_observation(_load("boj_ir01_policy_rate.json"))
    assert policy == (date(2026, 10, 12), 1.5)


def test_boj_parse_missing_stays_missing():
    assert parse_latest_observation({}) is None
    assert parse_latest_observation({"RESULTSET": []}) is None
    nulls = {"RESULTSET": [{"VALUES": {"SURVEY_DATES": [20261013], "VALUES": [None]}}]}
    assert parse_latest_observation(nulls) is None


def _boj_transport(base: str, db: str, code: str, start: str, end: str) -> dict:
    if db == "FM08":
        return _load("boj_fm08_usdjpy.json")
    if db == "IR01":
        return _load("boj_ir01_policy_rate.json")
    raise AssertionError(f"unexpected db {db}")


async def test_boj_provider_composes_both_series():
    with patch(
        "research_analyst.providers.boj._fetch_series", side_effect=_boj_transport
    ):
        rates = await BankOfJapanProvider().get_latest_rates()
    assert rates is not None
    assert rates.usd_jpy == 158.34
    assert rates.usd_jpy_as_of == date(2026, 10, 9)
    assert rates.policy_rate_pct == 1.5
    assert rates.policy_rate_as_of == date(2026, 10, 12)
    assert "Basic Discount Rate" in rates.policy_rate_series_name


async def test_boj_provider_partial_failure_keeps_good_series():
    def flaky(base: str, db: str, code: str, start: str, end: str) -> dict:
        if db == "FM08":
            raise OSError("boom")
        return _boj_transport(base, db, code, start, end)

    with patch("research_analyst.providers.boj._fetch_series", side_effect=flaky):
        rates = await BankOfJapanProvider().get_latest_rates()
    assert rates is not None
    assert rates.usd_jpy is None  # missing stays missing
    assert rates.policy_rate_pct == 1.5


async def test_boj_provider_total_failure_is_none():
    with patch(
        "research_analyst.providers.boj._fetch_series", side_effect=OSError("boom")
    ):
        assert await BankOfJapanProvider().get_latest_rates() is None


def test_boj_registry_entries_carry_obligation_flags():
    for dataset in ("fx_rates", "policy_rate"):
        entry = primary_entry(dataset, "JP")
        assert entry is not None
        assert entry.source_name == "Bank of Japan Time-Series API"
        assert entry.status == "wired"
        flags = " ".join(entry.flags)
        assert "credit-line-required" in flags
        assert "pre-release-notification-required" in flags


# ---------------------------------------------------------------------------
# FRED per-series rights gating
# ---------------------------------------------------------------------------

FETCHED_SERIES = {"CPIAUCSL", "A191RL1Q225SBEA", "BAMLH0A0HYM2", "T10Y2Y"}


def test_every_fetched_fred_series_has_a_classification():
    source = Path(market_data_module.__file__).read_text()
    fetched = set(re.findall(r'_gated\("([A-Z0-9]+)"', source))
    assert fetched == FETCHED_SERIES
    classified = {r.series_id for r in FRED_SERIES_RIGHTS}
    assert fetched <= classified, "a fetched series lacks a rights classification"


def test_fred_classifications_match_series_sources():
    cpi = fred_series_rights("CPIAUCSL")
    assert cpi is not None and cpi.rights == RIGHTS_PUBLIC_DOMAIN
    assert "Bureau of Labor Statistics" in cpi.source_organization
    assert fred_series_displayable("CPIAUCSL") is True

    gdp = fred_series_rights("A191RL1Q225SBEA")
    assert gdp is not None and gdp.rights == RIGHTS_PUBLIC_DOMAIN
    assert "Bureau of Economic Analysis" in gdp.source_organization
    assert fred_series_displayable("A191RL1Q225SBEA") is True

    curve = fred_series_rights("T10Y2Y")
    assert curve is not None and curve.rights == RIGHTS_PUBLIC_DOMAIN
    assert fred_series_displayable("T10Y2Y") is True

    hy = fred_series_rights("BAMLH0A0HYM2")
    assert hy is not None and hy.rights == RIGHTS_THIRD_PARTY_COPYRIGHTED
    assert "ICE Data Indices" in hy.source_organization
    assert hy.commercial_display is False
    assert fred_series_displayable("BAMLH0A0HYM2") is False


def test_fred_gate_fails_closed_for_unclassified_series():
    assert fred_series_rights("NO_SUCH_SERIES") is None
    assert fred_series_displayable("NO_SUCH_SERIES") is False
    assert fred_series_displayable("") is False


async def test_populate_fred_never_fetches_the_gated_series():
    fetched: list[str] = []

    def fake_observations(series_id: str, api_key: str, base_url: str, limit: int = 14):
        fetched.append(series_id)
        if series_id == "CPIAUCSL":
            # 14 monthly points, newest first; index 12 is a year earlier.
            return [(f"m{i:02d}", 113.0 - i) for i in range(14)]
        if series_id == "A191RL1Q225SBEA":
            return [("2026-04-01", 2.2)]
        if series_id == "T10Y2Y":
            return [("2026-10-13", 0.35)]
        raise AssertionError(f"gate let {series_id} through")

    snapshot = MacroSnapshot(as_of_date=date(2026, 10, 14))
    provider = MarketDataProvider()
    with (
        patch.object(market_data_module.settings.market, "fred_api_key", "test-key"),
        patch.object(market_data_module, "_fred_observations", side_effect=fake_observations),
    ):
        got = await provider._populate_fred(snapshot)
    assert got is True
    assert "BAMLH0A0HYM2" not in fetched  # excluded by the rights gate
    assert set(fetched) == {"CPIAUCSL", "A191RL1Q225SBEA", "T10Y2Y"}
    # Public-domain series behave exactly as before the gate existed.
    assert snapshot.cpi_yoy is not None and snapshot.cpi_yoy > 0
    assert snapshot.gdp_growth_latest == pytest.approx(0.022)
    assert snapshot.yield_curve_spread == pytest.approx(0.0035)
    # The gated series contributes nothing — no silent substitute value.
    assert snapshot.credit_spread_hy is None


# ---------------------------------------------------------------------------
# Macro snapshot integration (provenance only — no existing field changes)
# ---------------------------------------------------------------------------


class _FakeEcb:
    async def get_latest_macro(self):
        from research_analyst.providers.sdmx import EcbMacro

        return EcbMacro(
            eur_usd=1.1188,
            eur_usd_as_of=date(2026, 10, 13),
            deposit_facility_rate_pct=2.5,
            deposit_facility_as_of=date(2026, 10, 14),
            hicp_yoy_pct=3.8,
            hicp_as_of=date(2026, 9, 1),
        )


class _FakeBundesbank:
    async def get_latest_macro(self):
        from research_analyst.providers.sdmx import BundesbankMacro

        return BundesbankMacro(bund_10y_yield_pct=3.64, bund_10y_as_of=date(2026, 9, 1))


class _FakeEurostat:
    async def get_latest_macro(self):
        from research_analyst.providers.sdmx import EurostatMacro

        return EurostatMacro(
            hicp_yoy_pct=3.2,
            hicp_as_of=date(2026, 8, 1),
            gdp_growth_pct=1.2,
            gdp_as_of=date(2025, 1, 1),
        )


class _FakeBoj:
    async def get_latest_rates(self):
        from research_analyst.providers.boj import BojRates

        return BojRates(
            usd_jpy=158.34,
            usd_jpy_as_of=date(2026, 10, 9),
            policy_rate_pct=1.5,
            policy_rate_as_of=date(2026, 10, 12),
        )


class _NoneProvider:
    async def get_avg_interest_rates(self):
        return None

    async def get_latest_rates(self):
        return None

    async def get_latest_macro(self):
        return None


async def test_populate_first_sources_step2_adds_provenance_only():
    snapshot = MacroSnapshot(as_of_date=date(2026, 10, 14), us_10y_yield=0.041)
    provider = MarketDataProvider()
    with (
        patch.object(market_data_module, "TreasuryProvider", lambda: _NoneProvider()),
        patch.object(market_data_module, "BankOfCanadaProvider", lambda: _NoneProvider()),
        patch.object(market_data_module, "EcbProvider", lambda: _FakeEcb()),
        patch.object(market_data_module, "BundesbankProvider", lambda: _FakeBundesbank()),
        patch.object(market_data_module, "EurostatProvider", lambda: _FakeEurostat()),
        patch.object(market_data_module, "BankOfJapanProvider", lambda: _FakeBoj()),
        patch.object(market_data_module, "BcbProvider", lambda: _NoneProvider()),
    ):
        got = await provider._populate_first_sources(snapshot)
    assert got is True
    # Rates/HICP/GDP land as fractions; FX exactly as published.
    assert snapshot.ecb_eur_usd == 1.1188
    assert snapshot.ecb_eur_usd_as_of == date(2026, 10, 13)
    assert snapshot.ecb_deposit_facility_rate == 0.025
    assert snapshot.ecb_hicp_yoy == 0.038
    assert snapshot.ecb_hicp_as_of == date(2026, 9, 1)
    assert snapshot.bundesbank_bund_10y_yield == 0.0364
    assert snapshot.eurostat_hicp_yoy == 0.032
    assert snapshot.eurostat_gdp_growth == 0.012
    assert snapshot.boj_usd_jpy == 158.34
    assert snapshot.boj_policy_rate == 0.015
    assert snapshot.boj_policy_rate_as_of == date(2026, 10, 12)
    assert snapshot.supplemental_sources == [
        "ECB Data Portal (EUR/USD reference, deposit facility rate, HICP)",
        "Deutsche Bundesbank SDMX (10-year Bund yield)",
        "Eurostat Statistics API (EU HICP, real GDP growth)",
        "Bank of Japan Time-Series API (USD/JPY, basic discount/loan rate)",
    ]
    # No existing field was touched.
    assert snapshot.us_10y_yield == 0.041
    assert snapshot.cpi_yoy is None


async def test_populate_first_sources_step2_failure_leaves_fields_empty():
    snapshot = MacroSnapshot(as_of_date=date(2026, 10, 14))
    provider = MarketDataProvider()
    with (
        patch.object(market_data_module, "TreasuryProvider", lambda: _NoneProvider()),
        patch.object(market_data_module, "BankOfCanadaProvider", lambda: _NoneProvider()),
        patch.object(market_data_module, "EcbProvider", lambda: _NoneProvider()),
        patch.object(market_data_module, "BundesbankProvider", lambda: _NoneProvider()),
        patch.object(market_data_module, "EurostatProvider", lambda: _NoneProvider()),
        patch.object(market_data_module, "BankOfJapanProvider", lambda: _NoneProvider()),
        patch.object(market_data_module, "BcbProvider", lambda: _NoneProvider()),
    ):
        got = await provider._populate_first_sources(snapshot)
    assert got is False
    assert snapshot.ecb_eur_usd is None
    assert snapshot.ecb_deposit_facility_rate is None
    assert snapshot.bundesbank_bund_10y_yield is None
    assert snapshot.eurostat_hicp_yoy is None
    assert snapshot.boj_usd_jpy is None
    assert snapshot.supplemental_sources == []
