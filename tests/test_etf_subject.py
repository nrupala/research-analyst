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

"""Tests for the ETF-as-subject report path (Slice B, Option A)."""
# Module: tests/test_etf_subject.py | Version: 0.3.0 | Updated: 2026-08-24

from decimal import Decimal

from research_analyst.engines.etf import ETFEngine
from research_analyst.enums import SecurityType
from research_analyst.models import CompanyProfile
from research_analyst.reports.renderer import ReportRenderer


def _etf_profile() -> CompanyProfile:
    return CompanyProfile(
        ticker="SPY",
        name="SPDR S&P 500 ETF Trust",
        security_type=SecurityType.ETF,
        market_cap=Decimal("500000000000"),
        currency="USD",
        description="Seeks to track the S&P 500 index.",
    )


def _equity_profile() -> CompanyProfile:
    return CompanyProfile(
        ticker="AAPL",
        name="Apple Inc.",
        security_type=SecurityType.EQUITY,
        market_cap=Decimal("3000000000000"),
        currency="USD",
        description="Designs and sells consumer electronics.",
    )


def test_etf_engine_surfaces_overview_and_aum():
    result = ETFEngine().analyze(_etf_profile())
    assert result["fund_overview"] == "Seeks to track the S&P 500 index."
    assert result["aum"] == Decimal("500000000000")
    labels = [a.label for a in result["assumptions"]]
    assert "Assets Under Management" in labels
    assert all(isinstance(a.value, str) for a in result["assumptions"])
    assert any("Expense ratio" in g for g in result["data_gaps"])


def test_etf_engine_records_gaps_when_fields_missing():
    profile = CompanyProfile(
        ticker="XYZ",
        name="Mystery Fund",
        security_type=SecurityType.ETF,
    )
    result = ETFEngine().analyze(profile)
    assert result["fund_overview"] is None
    assert result["aum"] is None
    assert any("description unavailable" in g for g in result["data_gaps"])
    assert any("Assets under management unavailable" in g for g in result["data_gaps"])


def test_etf_block_present_for_etf_subject():
    renderer = ReportRenderer()
    parts, visuals, assumptions, gaps = renderer._build_etf_block({"profile": _etf_profile()})
    assert "### ETF Overview" in parts
    assert any(p.startswith("**Strategy:**") for p in parts)
    assert any("Assets Under Management" in p for p in parts)
    assert any("$500000000000.00" in p for p in parts)
    assert any(a.label == "Assets Under Management" for a in assumptions)


def test_etf_block_absent_for_equity_subject():
    renderer = ReportRenderer()
    parts, visuals, assumptions, gaps = renderer._build_etf_block({"profile": _equity_profile()})
    assert parts == []
    assert visuals == []
    assert assumptions == []
    assert gaps == []
