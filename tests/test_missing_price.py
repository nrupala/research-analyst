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

"""Missing price must stay missing — never a fabricated $0.00.

Regression suite for the 2026-10-15 META report, which rendered
"Current Price: $0.00" when the price source (Stooq) returned an
empty frame: the empty PriceSeries defaulted current_price to 0.0
and every downstream surface formatted it as real money.
"""
# Module: tests/test_missing_price.py

import asyncio
from datetime import date
from decimal import Decimal

from research_analyst.engines.valuation import ValuationEngine
from research_analyst.enums import ReportType, SecurityType
from research_analyst.models import CompanyProfile, PriceSeries
from research_analyst.providers import market_data
from research_analyst.reports.currency import money
from research_analyst.reports.renderer import ReportRenderer
from research_analyst.reports.templates import get_template
from research_analyst.reports.visuals import VisualEngine


def _profile() -> CompanyProfile:
    return CompanyProfile(
        ticker="META",
        name="Meta Platforms",
        security_type=SecurityType.EQUITY,
        sector="Technology",
        industry="Internet",
        market_cap=Decimal("1800000000000"),
        employees=74000,
        currency="USD",
        description="Test profile.",
    )


def _empty_series() -> PriceSeries:
    return PriceSeries(
        ticker="META",
        data=[],
        period_start=date(2026, 10, 15),
        period_end=date(2026, 10, 15),
        data_source="stooq",
    )


class TestMissingPriceModel:
    def test_empty_series_price_is_none_not_zero(self):
        ps = _empty_series()
        assert ps.current_price is None
        assert ps.price_52w_high is None
        assert ps.price_52w_low is None
        assert ps.ytd_return is None
        assert ps.total_return_1y is None

    def test_money_none_is_not_available(self):
        assert money(None) == "Not available"
        assert money(None, "EUR") == "Not available"
        assert money(736.72) == "$736.72"


class TestMissingPriceProvider:
    def test_stooq_empty_frame_yields_none_price(self, monkeypatch):
        class _NoDataStooq:
            async def get_daily_history(self, ticker):  # noqa: ARG002
                return None

        monkeypatch.setattr(market_data, "StooqProvider", _NoDataStooq)
        provider = market_data.MarketDataProvider()
        series = asyncio.run(provider.get_price_series("META", period="1y"))
        assert series.data == []
        assert series.current_price is None


class TestMissingPriceValuation:
    def test_valuation_marks_price_unavailable(self):
        result = ValuationEngine().build_valuation(_profile(), [], _empty_series())
        assert result.current_price is None
        assert result.primary_methodology == "Insufficient Data"
        assert result.scenarios == []


class TestMissingPriceRendering:
    def test_key_metrics_table_says_not_available(self):
        visual = VisualEngine.table_key_metrics(_profile(), [], None)
        assert "Not available" in visual.content
        assert "$0.00" not in visual.content

    def test_comprehensive_step1_says_not_available(self):
        step = get_template(ReportType.COMPREHENSIVE).steps[0]
        ctx = {
            "profile": _profile(),
            "prices": _empty_series(),
            "financials": [],
            "fundamental": None,
        }
        section, _ = ReportRenderer()._render_comprehensive_step1(step, ctx)
        assert "**Current Price:** Not available" in section.content
        assert "$0.00" not in section.content
