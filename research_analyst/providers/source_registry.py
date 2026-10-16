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

"""Source registry — the declarative first-source map for every dataset.

Doctrine (owner-set, 2026-10-11; matrix verified 2026-10-14 in
docs/goals source-registry-matrix.md):

  - Every dataset declares its FIRST source of truth here: the regulator,
    the exchange itself, the central bank, or the statistics office.
  - Only free first sources are wired. A dataset whose first source is
    paid-only is declared ``out_of_scope`` — never filled with an
    aggregator, never worked around.
  - yfinance is registered explicitly as a development backup
    (``is_primary=False``). It is never the production source of record
    and is never silently substituted for a primary.
  - A primary-source failure surfaces honestly (stale-with-disclosure or
    out of scope). There is no fallback logic in this module — it is a
    declaration, not a router.

Status values:
  - ``wired``        — a provider in this codebase fetches from it today.
  - ``planned``      — verified free first source, provider not built yet.
  - ``out_of_scope`` — first source exists but is paid-only / licence-gated
                       under the owner's free-sources-only scope rule.
"""
# Module: research_analyst/providers/source_registry.py | Version: 0.3.0 | Updated: 2026-10-14

from __future__ import annotations

from dataclasses import dataclass

from .boj import BOJ_OBLIGATIONS

STATUS_WIRED = "wired"
STATUS_PLANNED = "planned"
STATUS_OUT_OF_SCOPE = "out_of_scope"
STATUSES = frozenset({STATUS_WIRED, STATUS_PLANNED, STATUS_OUT_OF_SCOPE})

ROLE_PRIMARY = "primary source"
ROLE_DEV_BACKUP = "development backup — non-primary"
ROLE_PRODUCTION_EOD = (
    "owner-designated production price source — free EOD, "
    "not an exchange first source"
)
# Price cascade roles (owner directive, 2026-10-15): every price is
# served by the declared cascade and labeled with the serving source.
ROLE_CASCADE_1 = "price cascade step 1 — market-direct (exchange-published)"
ROLE_CASCADE_2 = "price cascade step 2 — free key service"
ROLE_CASCADE_3 = "price cascade step 3 — free EOD aggregator"
ROLE_CASCADE_4 = "price cascade step 4 — last resort"


@dataclass(frozen=True)
class SourceEntry:
    """One dataset's declared source."""

    dataset: str  # dataset key, e.g. "financial_statements", "macro"
    market: str  # market code (US / CA / EU / DE / UK / JP / BR / GLOBAL)
    source_name: str  # product/feed name, e.g. "SEC EDGAR"
    organization: str  # the first-source organisation
    base_url: str  # API / portal base URL
    access_method: str  # REST / bulk download / SDMX / web portal …
    key_env_var: str | None  # env var holding the API key, or None
    terms_note: str  # one-line display/redistribution terms (matrix-verified)
    status: str  # wired / planned / out_of_scope
    is_primary: bool  # True only for first sources of truth
    role: str = ROLE_PRIMARY
    rights_note: str = ""  # per-source/per-series rights caveats
    flags: tuple[str, ...] = ()  # explicit obligations attached to use


@dataclass(frozen=True)
class DatasetGap:
    """A dataset with no declarable source entry — an explicit, named gap."""

    dataset: str
    market: str
    reason: str


SOURCE_REGISTRY: tuple[SourceEntry, ...] = (
    # ------------------------------------------------------------------
    # US filings & fundamentals — SEC EDGAR (wired, in production)
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="filings",
        market="US",
        source_name="SEC EDGAR",
        organization="U.S. Securities and Exchange Commission",
        base_url="https://data.sec.gov",
        access_method="REST JSON + nightly bulk ZIPs",
        key_env_var=None,
        terms_note=(
            "EDGAR data is public; a redistribution licence statement was "
            "UNVERIFIED on official pages (matrix §9) — confirm before display."
        ),
        status=STATUS_WIRED,
        is_primary=True,
    ),
    SourceEntry(
        dataset="financial_statements",
        market="US",
        source_name="SEC EDGAR XBRL",
        organization="U.S. Securities and Exchange Commission",
        base_url="https://data.sec.gov/api/xbrl",
        access_method="REST JSON (XBRL company facts)",
        key_env_var=None,
        terms_note="As SEC EDGAR (filings).",
        status=STATUS_WIRED,
        is_primary=True,
    ),
    SourceEntry(
        dataset="company_profile",
        market="US",
        source_name="SEC EDGAR",
        organization="U.S. Securities and Exchange Commission",
        base_url="https://data.sec.gov/submissions",
        access_method="REST JSON (submissions)",
        key_env_var=None,
        terms_note="As SEC EDGAR (filings).",
        status=STATUS_WIRED,
        is_primary=True,
    ),
    SourceEntry(
        dataset="etf_metadata",
        market="US",
        source_name="SEC EDGAR",
        organization="U.S. Securities and Exchange Commission",
        base_url="https://data.sec.gov",
        access_method="REST JSON (fund filings)",
        key_env_var=None,
        terms_note="As SEC EDGAR (filings). Fund filings are the first source; not yet wired.",
        status=STATUS_PLANNED,
        is_primary=True,
    ),
    # ------------------------------------------------------------------
    # US macro — FRED (wired, in production)
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="macro",
        market="US",
        source_name="FRED",
        organization="Federal Reserve Bank of St. Louis",
        base_url="https://api.stlouisfed.org/fred",
        access_method="REST JSON",
        key_env_var="RA_MARKET_FRED_API_KEY",
        terms_note="Cite the series source + FRED (fred.stlouisfed.org/legal).",
        status=STATUS_WIRED,
        is_primary=True,
        rights_note=(
            "Per-series rights: public-domain and citation series may be "
            "displayed commercially with attribution; copyrighted third-party "
            "series (e.g. ICE BofA index series) require the owner's permission "
            "beyond personal use and are NOT cleared for commercial display."
        ),
    ),
    # ------------------------------------------------------------------
    # US fiscal / rates — US Treasury Fiscal Data (wired by this change)
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="fiscal_rates",
        market="US",
        source_name="US Treasury Fiscal Data",
        organization="U.S. Department of the Treasury, Bureau of the Fiscal Service",
        base_url="https://api.fiscaldata.treasury.gov/services/api/fiscal_service",
        access_method="REST JSON (Average Interest Rates dataset)",
        key_env_var=None,
        terms_note=(
            "Data is free without restriction — copy/adapt/redistribute, "
            "commercial or not (fiscaldata.treasury.gov API documentation)."
        ),
        status=STATUS_WIRED,
        is_primary=True,
    ),
    # ------------------------------------------------------------------
    # Canada macro / FX — Bank of Canada Valet (wired by this change)
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="fx_rates",
        market="CA",
        source_name="Bank of Canada Valet",
        organization="Bank of Canada",
        base_url="https://www.bankofcanada.ca/valet",
        access_method="REST JSON (observations)",
        key_env_var=None,
        terms_note="Use/copy/distribution permitted with attribution (bankofcanada.ca/terms).",
        status=STATUS_WIRED,
        is_primary=True,
    ),
    SourceEntry(
        dataset="policy_rate",
        market="CA",
        source_name="Bank of Canada Valet",
        organization="Bank of Canada",
        base_url="https://www.bankofcanada.ca/valet",
        access_method="REST JSON (observations, series V39079)",
        key_env_var=None,
        terms_note="Use/copy/distribution permitted with attribution (bankofcanada.ca/terms).",
        status=STATUS_WIRED,
        is_primary=True,
    ),
    # ------------------------------------------------------------------
    # Eurozone / Germany / EU statistics — SDMX layer (wired, step 2)
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="macro",
        market="EU",
        source_name="ECB Data Portal",
        organization="European Central Bank",
        base_url="https://data-api.ecb.europa.eu/service",
        access_method="SDMX 2.1 REST (SDMX-JSON)",
        key_env_var=None,
        terms_note=(
            "ESCB statistics: free access and free reuse, commercial or not, "
            "with source quoted and statistics unmodified."
        ),
        status=STATUS_WIRED,
        is_primary=True,
    ),
    SourceEntry(
        dataset="macro",
        market="DE",
        source_name="Deutsche Bundesbank SDMX",
        organization="Deutsche Bundesbank",
        base_url="https://api.statistiken.bundesbank.de/rest",
        access_method="SDMX 2.1 REST (SDMX-JSON)",
        key_env_var=None,
        terms_note="ESCB policy: free reuse with source quoted, statistics unmodified.",
        status=STATUS_WIRED,
        is_primary=True,
    ),
    SourceEntry(
        dataset="statistics",
        market="EU",
        source_name="Eurostat Statistics API",
        organization="Eurostat (European Commission)",
        base_url="https://ec.europa.eu/eurostat/api/dissemination",
        access_method="REST (JSON-stat 2.0)",
        key_env_var=None,
        terms_note=(
            "Reuse authorised for commercial and non-commercial purposes with "
            "source acknowledgement (Commission reuse policy / CC BY 4.0)."
        ),
        status=STATUS_WIRED,
        is_primary=True,
    ),
    # ------------------------------------------------------------------
    # Japan rates / FX — Bank of Japan Time-Series API (wired, step 2)
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="fx_rates",
        market="JP",
        source_name="Bank of Japan Time-Series API",
        organization="Bank of Japan",
        base_url="https://www.stat-search.boj.or.jp/api/v1",
        access_method="REST JSON (getDataCode, FM08/FXERD04)",
        key_env_var=None,
        terms_note=(
            "Keyless. Display carries BoJ obligations — see flags "
            "(credit line + pre-release notification, api_notice_en.pdf)."
        ),
        status=STATUS_WIRED,
        is_primary=True,
        flags=BOJ_OBLIGATIONS,
    ),
    SourceEntry(
        dataset="policy_rate",
        market="JP",
        source_name="Bank of Japan Time-Series API",
        organization="Bank of Japan",
        base_url="https://www.stat-search.boj.or.jp/api/v1",
        access_method="REST JSON (getDataCode, IR01/MADR1Z@D)",
        key_env_var=None,
        terms_note=(
            "Keyless. Display carries BoJ obligations — see flags "
            "(credit line + pre-release notification, api_notice_en.pdf)."
        ),
        status=STATUS_WIRED,
        is_primary=True,
        flags=BOJ_OBLIGATIONS,
    ),
    # ------------------------------------------------------------------
    # UK filings — Companies House (planned; free key not yet obtained)
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="filings",
        market="UK",
        source_name="Companies House",
        organization="Companies House",
        base_url="https://api.company-information.service.gov.uk",
        access_method="REST + bulk iXBRL downloads",
        key_env_var="RA_COMPANIES_HOUSE_API_KEY",
        terms_note=(
            "Public-register information; Crown copyright under the Open "
            "Government Licence v3.0."
        ),
        status=STATUS_PLANNED,
        is_primary=True,
    ),
    # ------------------------------------------------------------------
    # Japan filings — EDINET (planned; free key not yet obtained)
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="filings",
        market="JP",
        source_name="EDINET API v2",
        organization="Financial Services Agency (Japan)",
        base_url="https://api.edinet-fsa.go.jp/api/v2",
        access_method="REST",
        key_env_var="RA_EDINET_API_KEY",
        terms_note=(
            "Redistribution terms UNVERIFIED (Japanese-only spec, matrix §9) — "
            "read before any display."
        ),
        status=STATUS_PLANNED,
        is_primary=True,
    ),
    # ------------------------------------------------------------------
    # US energy — EIA (planned; free key not yet obtained)
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="energy",
        market="US",
        source_name="EIA Open Data API v2",
        organization="U.S. Energy Information Administration",
        base_url="https://api.eia.gov/v2",
        access_method="REST + bulk files",
        key_env_var="RA_EIA_API_KEY",
        terms_note=(
            "Free of charge; registration and the API Terms of Service apply "
            "(EIA Copyrights and Reuse Policy)."
        ),
        status=STATUS_PLANNED,
        is_primary=True,
    ),
    # ------------------------------------------------------------------
    # Brazil filings — CVM open data (WIRED 2026-10-15: DFP annual
    # statements lead for .SA listings; ticker resolved by company
    # name against the CVM register, never guessed. ITR quarterly is
    # a named fast-follow.)
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="filings",
        market="BR",
        source_name="CVM Portal de Dados Abertos",
        organization="Comissão de Valores Mobiliários",
        base_url="https://dados.cvm.gov.br",
        access_method="Bulk ZIP/TXT via CKAN datasets (DFP/ITR/FRE/FCA)",
        key_env_var=None,
        terms_note=(
            "ODbL (license_id=odc-odbl, verified on the DFP dataset's "
            "own CKAN record 2026-10-15): consume with attribution; "
            "RA sells its analysis, never the dataset."
        ),
        status=STATUS_WIRED,
        is_primary=True,
    ),
    # ------------------------------------------------------------------
    # Prices — the owner's cascade (2026-10-15). Order: (1) market-
    # direct (Nasdaq for US; TMX designated for Canada, route not yet
    # established), (2) free key services (Tiingo, Alpha Vantage;
    # Twelve Data and FMP join as their providers land), (3) Stooq,
    # (4) yfinance last. The serving step is stamped on the series and
    # labeled next to the price. The declared first source (exchange
    # tape) stays out_of_scope below: it is paid-only.
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="price_data",
        market="US",
        source_name="Nasdaq",
        organization="Nasdaq",
        base_url="https://api.nasdaq.com",
        access_method="Public quote API (historical, keyless)",
        key_env_var=None,
        terms_note=(
            "The listing exchange's own published end-of-day data — "
            "the closest free window on the first source. Split-"
            "adjusted only (verified numerically 2026-10-15: AAPL "
            "2020-01-02 $75.0875 = $300.35 / 4), NOT dividend-adjusted; "
            "consumed under Nasdaq's published terms with attribution; "
            "an input to RA's analysis, never sold as data."
        ),
        status=STATUS_WIRED,
        is_primary=False,
        role=ROLE_CASCADE_1,
    ),
    SourceEntry(
        dataset="price_history",
        market="US",
        source_name="Nasdaq",
        organization="Nasdaq",
        base_url="https://api.nasdaq.com",
        access_method="Public quote API (historical, keyless)",
        key_env_var=None,
        terms_note=(
            "As Nasdaq (price_data): the same historical fetch serves "
            "the full price history and the latest EOD close."
        ),
        status=STATUS_WIRED,
        is_primary=False,
        role=ROLE_CASCADE_1,
    ),
    SourceEntry(
        dataset="price_data",
        market="CA",
        source_name="TMX",
        organization="TMX Group",
        base_url="https://www.tmx.com",
        access_method="Exchange-published quotes (route under probe)",
        key_env_var=None,
        terms_note=(
            "Canada's market-direct primary, designated by the owner "
            "(2026-10-15). The exchange site answers from the "
            "production host but no keyless machine route is verified "
            "yet; until one lands, Canada's cascade secondaries serve "
            "(owner's Canada rule), labeled."
        ),
        status=STATUS_PLANNED,
        is_primary=True,
    ),
    SourceEntry(
        dataset="price_data",
        market="GLOBAL",
        source_name="Tiingo",
        organization="Tiingo",
        base_url="https://api.tiingo.com",
        access_method="REST API (daily prices, free key tier)",
        key_env_var="RA_MARKET_TIINGO_API_KEY",
        terms_note=(
            "Cascade step 2, first key service. Split- and dividend-"
            "adjusted EOD (adjClose basis). Canada coverage thin. "
            "Dormant until its key is configured; consumed under "
            "Tiingo's terms as an analysis input, never sold as data."
        ),
        status=STATUS_WIRED,
        is_primary=False,
        role=ROLE_CASCADE_2,
    ),
    SourceEntry(
        dataset="price_data",
        market="GLOBAL",
        source_name="Alpha Vantage",
        organization="Alpha Vantage",
        base_url="https://www.alphavantage.co",
        access_method="REST API (TIME_SERIES_DAILY, free key tier)",
        key_env_var="RA_MARKET_ALPHA_VANTAGE_KEY",
        terms_note=(
            "Cascade step 2 gap-filler: the free tier is capped at "
            "~25 requests/day and serves as-traded (unadjusted) daily "
            "prices — the ADJUSTED variant is premium. Dormant until "
            "its key is configured; basis disclosed wherever it serves."
        ),
        status=STATUS_WIRED,
        is_primary=False,
        role=ROLE_CASCADE_2,
    ),
    # ------------------------------------------------------------------
    # Prices cascade step 3 — Stooq free EOD. An aggregator, NOT a
    # first source (owner, 2026-10-15); redistribution consent under
    # its terms §5.3 is still being sought. Its bot gate refuses the
    # production host's egress today, so in practice this step falls
    # through until access lands — the cascade makes that non-fatal.
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="price_data",
        market="US",
        source_name="Stooq",
        organization="Stooq",
        base_url="https://stooq.com",
        access_method="CSV download (daily history, /q/d/l/)",
        key_env_var=None,
        terms_note=(
            "Free end-of-day data published by Stooq — an aggregator, "
            "not an exchange first source; declared on every report "
            "that uses it. Redistribution consent (terms §5.3) pending."
        ),
        status=STATUS_WIRED,
        is_primary=False,
        role=ROLE_CASCADE_3,
    ),
    SourceEntry(
        dataset="price_history",
        market="US",
        source_name="Stooq",
        organization="Stooq",
        base_url="https://stooq.com",
        access_method="CSV download (daily history, /q/d/l/)",
        key_env_var=None,
        terms_note=(
            "As Stooq (price_data): the same single CSV fetch serves "
            "the full price history and the latest EOD close."
        ),
        status=STATUS_WIRED,
        is_primary=False,
        role=ROLE_CASCADE_3,
    ),
    # ------------------------------------------------------------------
    # Declared primaries that are paid-only — out of scope, never filled
    # ------------------------------------------------------------------
    SourceEntry(
        dataset="price_data",
        market="US",
        source_name="Exchange EOD price feeds (CTA/UTP + proprietary)",
        organization="U.S. exchanges / CTA / UTP",
        base_url="https://www.ctaplan.com",
        access_method="Licensed feeds under exchange agreements",
        key_env_var=None,
        terms_note=(
            "Licensed. No free official EOD feed exists (matrix §2) — "
            "out of scope under the free-sources-only rule."
        ),
        status=STATUS_OUT_OF_SCOPE,
        is_primary=True,
    ),
    SourceEntry(
        dataset="dividends",
        market="US",
        source_name="Exchange corporate-actions files (Nasdaq Daily List)",
        organization="Nasdaq / U.S. exchanges",
        base_url="https://www.nasdaqtrader.com",
        access_method="Subscription files (secured FTP/website, data agreements)",
        key_env_var=None,
        terms_note=(
            "Licensed (matrix §3). No free machine-readable first-source "
            "corporate-actions feed; EDGAR filings are a partial route only."
        ),
        status=STATUS_OUT_OF_SCOPE,
        is_primary=True,
    ),
    # ------------------------------------------------------------------
    # yfinance — development backup ONLY. Never primary, never the
    # production source of record, never silently substituted.
    # ------------------------------------------------------------------
    *(
        SourceEntry(
            dataset=_yf_dataset,
            market="GLOBAL",
            source_name="yfinance",
            organization="Yahoo Finance (via yfinance library)",
            base_url="https://finance.yahoo.com",
            access_method="Library scrape (unofficial)",
            key_env_var=None,
            terms_note=(
                "Unofficial, ToS-gray development backup — labelled "
                "non-primary wherever it appears; never production of record."
            ),
            status=STATUS_WIRED,
            is_primary=False,
            role=ROLE_DEV_BACKUP,
        )
        for _yf_dataset in (
            "company_profile",
            "financial_statements",
            "analyst_estimates",
            "sector_peers",
            "macro",
            "dividends",
            "etf_metadata",
        )
    ),
    # yfinance for prices is the cascade's LAST RESORT (owner
    # directive, 2026-10-15): it serves only when market-direct, the
    # key services, and Stooq have all failed for a ticker, and every
    # price it serves is labeled "Yahoo Finance" next to the price.
    # Supersedes the 2026-10-14 development-backup-only posture and
    # the retired RA_DEV_FALLBACK_YFINANCE dev flag.
    SourceEntry(
        dataset="price_data",
        market="GLOBAL",
        source_name="yfinance",
        organization="Yahoo Finance (via yfinance library)",
        base_url="https://finance.yahoo.com",
        access_method="Library scrape (unofficial)",
        key_env_var=None,
        terms_note=(
            "Cascade step 4 — last resort (owner directive, "
            "2026-10-15). Unofficial source; labeled non-primary "
            "wherever it appears; never the sole basis for a claim "
            "the steps above could have served."
        ),
        status=STATUS_WIRED,
        is_primary=False,
        role=ROLE_CASCADE_4,
    ),
)


# Datasets the Research Analyst declares (orchestrator source labels) that
# have NO source entry — named explicitly so the absence is a decision,
# not an oversight. Each must stay explainable in one line.
REGISTRY_GAPS: tuple[DatasetGap, ...] = (
    DatasetGap(
        dataset="analyst_estimates",
        market="US",
        reason=(
            "No first source exists: analyst estimates are published by no "
            "regulator, exchange, or statistics office — aggregator-only data."
        ),
    ),
    DatasetGap(
        dataset="sector_peers",
        market="US",
        reason=(
            "Derived dataset: computed from the curated sector map over "
            "company_profile and price_data; no standalone source exists."
        ),
    ),
)


def entries_for_dataset(dataset: str) -> tuple[SourceEntry, ...]:
    """All registry entries declaring ``dataset`` (any market/status)."""
    return tuple(e for e in SOURCE_REGISTRY if e.dataset == dataset)


def primary_entry(dataset: str, market: str) -> SourceEntry | None:
    """The declared primary entry for (dataset, market), or None."""
    for e in SOURCE_REGISTRY:
        if e.dataset == dataset and e.market == market and e.is_primary:
            return e
    return None


def wired_primaries() -> tuple[SourceEntry, ...]:
    """Primary entries a provider fetches from today."""
    return tuple(e for e in SOURCE_REGISTRY if e.is_primary and e.status == STATUS_WIRED)


def declared_datasets() -> frozenset[str]:
    """Every dataset key named by an entry or an explicit gap."""
    return frozenset(
        [e.dataset for e in SOURCE_REGISTRY] + [g.dataset for g in REGISTRY_GAPS]
    )


# ---------------------------------------------------------------------------
# FRED per-series rights classification (step 2, 2026-10-14)
#
# FRED aggregates 100+ sources; rights attach to the SERIES, not to FRED.
# Each classification below is sourced from the series' own FRED page
# (Source line + series notes, verified 2026-10-14):
#   - Series whose source is a U.S. federal agency (BLS, BEA, the Federal
#     Reserve) are public domain: displayable commercially with citation.
#   - BAMLH0A0HYM2's source is ICE Data Indices, LLC; its FRED notes state
#     reproduction/distribution is prohibited without ICE's prior written
#     permission — flagged NOT for commercial display.
# The gate FAILS CLOSED: a series with no classification is not
# displayable. The FRED fetch path (providers/market_data.py) consults
# fred_series_displayable() for every series it requests; an excluded
# series is skipped with a debug log, never silently swapped.
# ---------------------------------------------------------------------------

RIGHTS_PUBLIC_DOMAIN = "public_domain"
RIGHTS_THIRD_PARTY_COPYRIGHTED = "third_party_copyrighted"


@dataclass(frozen=True)
class FredSeriesRights:
    """Rights classification for one FRED series the macro path fetches."""

    series_id: str
    source_organization: str  # as named in the series' FRED source notes
    rights: str  # RIGHTS_PUBLIC_DOMAIN / RIGHTS_THIRD_PARTY_COPYRIGHTED
    commercial_display: bool
    note: str


FRED_SERIES_RIGHTS: tuple[FredSeriesRights, ...] = (
    FredSeriesRights(
        series_id="CPIAUCSL",
        source_organization="U.S. Bureau of Labor Statistics",
        rights=RIGHTS_PUBLIC_DOMAIN,
        commercial_display=True,
        note="Federal statistical agency series; cite BLS + FRED.",
    ),
    FredSeriesRights(
        series_id="A191RL1Q225SBEA",
        source_organization="U.S. Bureau of Economic Analysis",
        rights=RIGHTS_PUBLIC_DOMAIN,
        commercial_display=True,
        note="Federal statistical agency series; cite BEA + FRED.",
    ),
    FredSeriesRights(
        series_id="T10Y2Y",
        source_organization="Federal Reserve Bank of St. Louis",
        rights=RIGHTS_PUBLIC_DOMAIN,
        commercial_display=True,
        note="Federal Reserve series calculated from U.S. Treasury data; cite FRED.",
    ),
    FredSeriesRights(
        series_id="BAMLH0A0HYM2",
        source_organization="ICE Data Indices, LLC",
        rights=RIGHTS_THIRD_PARTY_COPYRIGHTED,
        commercial_display=False,
        note=(
            "Third-party copyrighted index data: the series' FRED notes "
            "prohibit reproduction/distribution without ICE Data Indices' "
            "prior written permission — NOT cleared for commercial display."
        ),
    ),
)


def fred_series_rights(series_id: str) -> FredSeriesRights | None:
    """The rights classification for a FRED series, or None if unclassified."""
    for entry in FRED_SERIES_RIGHTS:
        if entry.series_id == series_id:
            return entry
    return None


def fred_series_displayable(series_id: str) -> bool:
    """True only when the series is classified AND cleared for display.

    Fail closed: no classification -> not displayable.
    """
    entry = fred_series_rights(series_id)
    return entry is not None and entry.commercial_display
