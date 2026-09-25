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

"""Tests for the Slice A.3c currency-symbol sweep in the report renderer.

Two layers:
  * currency.py units — currency_symbol() mapping + money() formatting.
  * renderer integration — the report renderer keys money off
    CompanyProfile.currency, with USD output byte-identical to pre-sweep.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from research_analyst.enums import ReportType, SecurityType
from research_analyst.models import CompanyProfile, PriceSeries
from research_analyst.reports.currency import currency_symbol, money
from research_analyst.reports.renderer import ReportRenderer
from research_analyst.reports.templates import get_template


class TestCurrencySymbol:
    def test_dollar_family(self):
        for code in ("USD", "CAD", "AUD", "HKD", "SGD"):
            assert currency_symbol(code) == "$"

    def test_named_symbols(self):
        assert currency_symbol("EUR") == "\u20ac"
        assert currency_symbol("GBP") == "\u00a3"
        assert currency_symbol("INR") == "\u20b9"
        assert currency_symbol("JPY") == "\u00a5"
        assert currency_symbol("CNY") == "\u00a5"

    def test_chf_trailing_space(self):
        assert currency_symbol("CHF") == "CHF "

    def test_case_and_whitespace_insensitive(self):
        assert currency_symbol("inr") == "\u20b9"
        assert currency_symbol(" eur ") == "\u20ac"

    def test_unknown_code_falls_back(self):
        assert currency_symbol("SEK") == "SEK "

    def test_falsy_defaults_to_dollar(self):
        assert currency_symbol("") == "$"
        assert currency_symbol(None) == "$"


class TestMoney:
    def test_usd_byte_identical(self):
        assert money(12.3, "USD") == "$12.30"
        assert money(1234.5, "USD", 0) == "$1234"
        assert money(2.7, "USD", 1) == "$2.7"

    def test_localised(self):
        assert money(12.3, "INR") == "\u20b912.30"
        assert money(50, "EUR", 0) == "\u20ac50"
        assert money(9.9, "CHF") == "CHF 9.90"

    def test_default_currency_is_usd(self):
        assert money(1.0) == "$1.00"


def _profile(currency: str) -> CompanyProfile:
    return CompanyProfile(
        ticker="TEST",
        name="Test Co",
        security_type=SecurityType.EQUITY,
        sector="Technology",
        industry="Software",
        market_cap=Decimal("2500000000"),
        employees=1000,
        currency=currency,
        description="A test company.",
    )


def _long_term_step1(currency: str) -> str:
    step = get_template(ReportType.LONG_TERM).steps[0]
    ctx = {"profile": _profile(currency)}
    section, _ = ReportRenderer()._render_long_term_step1(step, ctx)
    return section.content


def _comp_step1(currency: str) -> str:
    prices = PriceSeries(
        ticker="TEST",
        data=[],
        period_start=date(2025, 1, 1),
        period_end=date(2026, 1, 1),
        current_price=100.0,
        price_52w_high=120.0,
        price_52w_low=80.0,
    )
    step = get_template(ReportType.COMPREHENSIVE).steps[0]
    ctx = {
        "profile": _profile(currency),
        "prices": prices,
        "financials": [],
        "fundamental": None,
    }
    section, _ = ReportRenderer()._render_comprehensive_step1(step, ctx)
    return section.content


class TestRendererCurrency:
    def test_market_cap_usd_unchanged(self):
        assert "**Market Cap:** $2.5B" in _long_term_step1("USD")

    def test_market_cap_inr_localised(self):
        content = _long_term_step1("INR")
        assert "**Market Cap:** \u20b92.5B" in content
        assert "$2.5B" not in content

    def test_price_usd_unchanged(self):
        content = _comp_step1("USD")
        assert "**Current Price:** $100.00" in content
        assert "**52-Week Range:** $80.00 - $120.00" in content

    def test_price_inr_localised(self):
        content = _comp_step1("INR")
        assert "**Current Price:** \u20b9100.00" in content
        assert "**52-Week Range:** \u20b980.00 - \u20b9120.00" in content
        assert "$100.00" not in content
