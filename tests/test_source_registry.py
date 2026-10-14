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

"""Source registry integrity tests (first-source wiring, step 1).

The registry is a declaration, and these tests keep it honest:
  - every entry is well-formed;
  - yfinance is NEVER primary (the owner's first-source doctrine);
  - every dataset the orchestrator declares has a registry entry or an
    explicit gap entry;
  - the wired-primary set is exactly what production fetches today, so
    a silent status flip fails loudly here.
Offline only: no network.
"""

from __future__ import annotations

from research_analyst.providers.source_registry import (
    REGISTRY_GAPS,
    ROLE_DEV_BACKUP,
    SOURCE_REGISTRY,
    STATUSES,
    declared_datasets,
    entries_for_dataset,
    primary_entry,
    wired_primaries,
)

# Dataset keys behind the orchestrator's data_sources labels
# (orchestrator.py: "company profile", "price data", "financial
# statements", "analyst estimates", "sector peers", "macro proxies",
# "dividends", "ETF metadata").
ORCHESTRATOR_DATASETS = {
    "company_profile",
    "price_data",
    "financial_statements",
    "analyst_estimates",
    "sector_peers",
    "macro",
    "dividends",
    "etf_metadata",
}


def test_every_entry_well_formed():
    for e in SOURCE_REGISTRY:
        assert e.dataset and e.market and e.source_name and e.organization
        assert e.base_url.startswith("https://"), e.source_name
        assert e.access_method and e.terms_note
        assert e.status in STATUSES, (e.source_name, e.status)
        assert e.key_env_var is None or e.key_env_var.startswith("RA_")


def test_no_duplicate_entries():
    keys = [(e.dataset, e.market, e.source_name) for e in SOURCE_REGISTRY]
    assert len(keys) == len(set(keys))


def test_yfinance_is_never_primary():
    yf = [e for e in SOURCE_REGISTRY if e.source_name == "yfinance"]
    assert yf, "yfinance must be registered explicitly as the dev backup"
    for e in yf:
        assert e.is_primary is False
        assert e.role == ROLE_DEV_BACKUP


def test_non_backup_entries_are_primary_sourced():
    for e in SOURCE_REGISTRY:
        if e.role != ROLE_DEV_BACKUP:
            assert e.is_primary is True, e.source_name


def test_orchestrator_datasets_all_declared():
    gaps = {g.dataset for g in REGISTRY_GAPS}
    for dataset in ORCHESTRATOR_DATASETS:
        assert entries_for_dataset(dataset) or dataset in gaps, dataset
        assert dataset in declared_datasets(), dataset


def test_gaps_are_explicit_and_reasoned():
    for gap in REGISTRY_GAPS:
        assert gap.dataset in ORCHESTRATOR_DATASETS
        assert len(gap.reason) > 20


def test_wired_primaries_are_exactly_the_production_set():
    wired = {(e.dataset, e.market, e.source_name) for e in wired_primaries()}
    assert wired == {
        ("filings", "US", "SEC EDGAR"),
        ("financial_statements", "US", "SEC EDGAR XBRL"),
        ("company_profile", "US", "SEC EDGAR"),
        ("macro", "US", "FRED"),
        ("fiscal_rates", "US", "US Treasury Fiscal Data"),
        ("fx_rates", "CA", "Bank of Canada Valet"),
        ("policy_rate", "CA", "Bank of Canada Valet"),
        ("macro", "EU", "ECB Data Portal"),
        ("macro", "DE", "Deutsche Bundesbank SDMX"),
        ("statistics", "EU", "Eurostat Statistics API"),
        ("fx_rates", "JP", "Bank of Japan Time-Series API"),
        ("policy_rate", "JP", "Bank of Japan Time-Series API"),
    }


def test_fred_rights_note_gates_copyrighted_series():
    fred = primary_entry("macro", "US")
    assert fred is not None and fred.source_name == "FRED"
    assert "copyrighted" in fred.rights_note
    assert "commercial display" in fred.rights_note
    assert fred.key_env_var == "RA_MARKET_FRED_API_KEY"


def test_paid_only_primaries_are_declared_out_of_scope():
    price = primary_entry("price_data", "US")
    assert price is not None and price.status == "out_of_scope"
    dividends = primary_entry("dividends", "US")
    assert dividends is not None and dividends.status == "out_of_scope"


def test_planned_first_sources_present():
    planned = {(e.dataset, e.market) for e in SOURCE_REGISTRY if e.status == "planned"}
    assert planned == {
        ("etf_metadata", "US"),
        ("filings", "UK"),
        ("filings", "JP"),
        ("energy", "US"),
        ("filings", "BR"),
    }
