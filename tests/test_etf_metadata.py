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

"""Tests for ETF metadata integration (Slice B-B).

Fully mocked / deterministic - no network, no yfinance, no pandas. The pure
extractor is exercised with plain dicts; the engine and renderer block with a
constructed ETFMetadata. One optional live smoke test is marked and skipped by
default (set RA_LIVE_SMOKE to 1 to run it).
"""
# Module: tests/test_etf_metadata.py | Version: 0.3.1 | Updated: 2026-08-24

import os
from decimal import Decimal

import pytest

from research_analyst.engines.etf import ETFEngine
from research_analyst.enums import SecurityType
from research_analyst.models import CompanyProfile, ETFMetadata, ETFTopHolding
from research_analyst.providers.market_data import _extract_etf_metadata
from research_analyst.reports.renderer import ReportRenderer


def _etf_profile(**overrides) -> CompanyProfile:
    base = dict(
        ticker="SPY",
        name="SPDR S&P 500 ETF Trust",
        security_type=SecurityType.ETF,
        market_cap=Decimal("500000000000"),
        currency="USD",
        description="Seeks to track the S&P 500 index.",
    )
    base.update(overrides)
    return CompanyProfile(**base)


def _full_metadata() -> ETFMetadata:
    return ETFMetadata(
        ticker="SPY",
        expense_ratio=Decimal("0.0009"),
        distribution_yield=Decimal("0.0132"),
        aum=Decimal("480000000000"),
        tracking_index="Large Blend",
        fund_family="SPDR State Street",
        top_holdings=[
            ETFTopHolding(symbol="AAPL", name="Apple Inc", weight=Decimal("0.071")),
            ETFTopHolding(symbol="MSFT", name="Microsoft Corp", weight=Decimal("0.065")),
        ],
        sector_weights={"Technology": Decimal("0.31"), "Financials": Decimal("0.13")},
        data_gaps=[],
    )


# --- pure extractor -------------------------------------------------------

def test_extract_etf_metadata_full_info():
    info = {
        "annualReportExpenseRatio": 0.0009,
        "yield": 0.0132,
        "totalAssets": 480000000000,
        "category": "Large Blend",
        "fundFamily": "SPDR State Street",
    }
    holdings = [
        {"symbol": "AAPL", "name": "Apple Inc", "weight": 0.071},
        {"symbol": "MSFT", "name": "Microsoft Corp", "weight": 0.065},
    ]
    sectors = {"Technology": 0.31, "Financials": 0.13}
    md = _extract_etf_metadata("SPY", info, holdings, sectors)
    assert md.ticker == "SPY"
    assert md.expense_ratio == Decimal("0.0009")
    assert md.distribution_yield == Decimal("0.0132")
    assert md.aum == Decimal("480000000000")
    assert md.tracking_index == "Large Blend"
    assert md.fund_family == "SPDR State Street"
    assert [h.symbol for h in md.top_holdings] == ["AAPL", "MSFT"]
    assert md.top_holdings[0].weight == Decimal("0.071")
    assert md.sector_weights["Technology"] == Decimal("0.31")
    assert md.data_gaps == []


def test_extract_etf_metadata_fallback_keys():
    info = {
        "netExpenseRatio": 0.03,
        "trailingAnnualDividendYield": 0.02,
        "netAssets": 1000000,
        "category": "",
    }
    md = _extract_etf_metadata("XYZ", info)
    # netExpenseRatio is percent-scaled (0.03 == 0.03%) -> normalised to 0.0003.
    assert md.expense_ratio == Decimal("0.0003")
    assert md.distribution_yield == Decimal("0.02")
    assert md.aum == Decimal("1000000")
    assert any("Tracking index" in g for g in md.data_gaps)
    assert any("Top holdings" in g for g in md.data_gaps)


def test_extract_etf_metadata_empty_records_all_gaps():
    md = _extract_etf_metadata("EMPTY", {})
    assert md.expense_ratio is None
    assert md.distribution_yield is None
    assert md.aum is None
    assert md.tracking_index == ""
    assert md.fund_family == ""
    assert md.top_holdings == []
    assert md.sector_weights == {}
    joined = " ".join(md.data_gaps)
    assert "Expense ratio unavailable" in joined
    assert "Distribution yield unavailable" in joined
    assert "Assets under management unavailable" in joined
    assert "Tracking index" in joined
    assert "Top holdings unavailable" in joined


# --- engine (enriched) ----------------------------------------------------

def test_etf_engine_enriched_surfaces_metadata():
    result = ETFEngine().analyze(_etf_profile(), _full_metadata())
    assert result["expense_ratio"] == Decimal("0.0009")
    assert result["distribution_yield"] == Decimal("0.0132")
    assert result["aum"] == Decimal("480000000000")
    assert result["tracking_index"] == "Large Blend"
    assert result["fund_family"] == "SPDR State Street"
    assert result["top_holdings"][0]["symbol"] == "AAPL"
    assert result["sector_weights"]["Technology"] == Decimal("0.31")
    labels = [a.label for a in result["assumptions"]]
    assert "Expense Ratio" in labels
    assert "Distribution Yield" in labels
    assert "Assets Under Management" in labels
    aum_assump = next(a for a in result["assumptions"] if a.label == "Assets Under Management")
    assert "ETF metadata" in aum_assump.source


def test_etf_engine_aum_falls_back_to_market_cap_proxy():
    md = _full_metadata()
    md.aum = None
    result = ETFEngine().analyze(_etf_profile(), md)
    assert result["aum"] == Decimal("500000000000")
    aum_assump = next(a for a in result["assumptions"] if a.label == "Assets Under Management")
    assert "proxy" in aum_assump.source


def test_etf_engine_carries_forward_metadata_gaps():
    md = _full_metadata()
    md.data_gaps = ["Top holdings unavailable from source."]
    result = ETFEngine().analyze(_etf_profile(), md)
    assert "Top holdings unavailable from source." in result["data_gaps"]


def test_etf_engine_backward_compatible_without_metadata():
    result = ETFEngine().analyze(_etf_profile())
    assert result["fund_overview"] == "Seeks to track the S&P 500 index."
    assert result["aum"] == Decimal("500000000000")
    assert any("Slice B-B" in g for g in result["data_gaps"])


# --- renderer block (enriched) -------------------------------------------

def test_build_etf_block_enriched():
    renderer = ReportRenderer()
    etf = ETFEngine().analyze(_etf_profile(), _full_metadata())
    parts, visuals, assumptions, gaps = renderer._build_etf_block(
        {"profile": _etf_profile(), "etf": etf}
    )
    text = "\n".join(parts)
    assert "### ETF Overview" in parts
    assert "**Expense Ratio:** 0.09%" in text
    assert "**Distribution Yield:** 1.32%" in text
    assert "**Index / Category:** Large Blend" in text
    assert "**Fund Family:** SPDR State Street" in text
    assert "**Top Holdings:**" in text
    assert "AAPL" in text and "7.10%" in text
    assert "**Sector Weights:**" in text
    assert "Technology" in text
    assert any(a.label == "Expense Ratio" for a in assumptions)


def test_build_etf_block_enriched_ignored_for_equity():
    renderer = ReportRenderer()
    equity = _etf_profile(ticker="AAPL", security_type=SecurityType.EQUITY)
    etf = ETFEngine().analyze(_etf_profile(), _full_metadata())
    parts, visuals, assumptions, gaps = renderer._build_etf_block(
        {"profile": equity, "etf": etf}
    )
    assert parts == [] and visuals == [] and assumptions == [] and gaps == []


# --- render() threading through a single-subject report type --------------

def test_long_term_step1_includes_etf_overview():
    import types

    renderer = ReportRenderer()
    etf = ETFEngine().analyze(_etf_profile(), _full_metadata())
    step = types.SimpleNamespace(
        step_number=1, title="Business Overview & Structural Position"
    )
    section, n = renderer._render_long_term_step1(
        step, {"profile": _etf_profile(), "etf": etf}
    )
    assert "### ETF Overview" in section.content
    assert "Expense Ratio" in section.content


# --- optional live smoke (skipped by default) ----------------------------

@pytest.mark.skipif(
    os.environ.get("RA_LIVE_SMOKE", "") not in ("1", "true", "yes"),
    reason="live network smoke test; set RA_LIVE_SMOKE to 1 to run",
)
def test_live_etf_metadata_smoke():
    import asyncio

    from research_analyst.providers.market_data import MarketDataProvider

    md = asyncio.run(MarketDataProvider().fetch_etf_metadata("SPY"))
    assert md.ticker == "SPY"
    assert (md.expense_ratio is not None) or (md.aum is not None)


def test_extract_etf_metadata_expense_ratio_percent_scaled():
    # Regression for the live prod bug: yfinance netExpenseRatio is
    # percent-scaled (SPY: 0.0945 == 0.0945%). It must be normalised to a
    # fraction so the renderer shows ~0.09%, never 9.45%.
    info = {"netExpenseRatio": 0.0945, "category": "Large Blend"}
    md = _extract_etf_metadata("SPY", info)
    assert md.expense_ratio == Decimal("0.000945")
    assert f"{md.expense_ratio:.2%}" == "0.09%"


def test_extract_etf_metadata_expense_ratio_backstop_clamp():
    # Defensive: a percent-scaled value landing in the fraction field
    # (annualReportExpenseRatio) is >= 5% and gets divided by 100.
    info = {"annualReportExpenseRatio": 0.09}
    md = _extract_etf_metadata("XYZ", info)
    assert md.expense_ratio == Decimal("0.0009")
    assert f"{md.expense_ratio:.2%}" == "0.09%"
