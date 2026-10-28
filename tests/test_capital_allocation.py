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

"""Capital allocation engine + narrative regression tests.

Offline, deterministic. Synthetic fixtures only — no network.
"""
# Module: tests/test_capital_allocation.py | Version: 0.1.0 | Updated: 2026-09-26

from __future__ import annotations

from decimal import Decimal

import pytest

from research_analyst.engines.fundamental import FundamentalEngine
from research_analyst.models import FinancialStatement
from research_analyst.reports.renderer import ReportRenderer


def _stmt(**kw) -> FinancialStatement:
    base = dict(
        period="FY2025",
        capex=Decimal("-32100000000"),
        share_buybacks=Decimal("-39200000000"),
        dividends_paid=None,
        operating_cash_flow=Decimal("100000000000"),
        free_cash_flow=Decimal("80000000000"),
    )
    base.update(kw)
    return FinancialStatement(**base)


def test_engine_populates_shareholder_yield_and_reinvestment_rate():
    cap = FundamentalEngine._analyze_capital_allocation(
        _stmt(), ticker="META", market_cap=1_000_000_000_000.0
    )
    assert cap.ticker == "META"
    # (39.2B buybacks + 0 dividends) / 1T market cap
    assert cap.shareholder_yield == pytest.approx(0.0392, rel=1e-3)
    # 32.1B capex / 100B operating cash flow
    assert cap.reinvestment_rate == pytest.approx(0.321, rel=1e-3)


def test_engine_yields_none_without_market_cap_or_ocf():
    cap = FundamentalEngine._analyze_capital_allocation(_stmt())
    assert cap.shareholder_yield is None
    cap2 = FundamentalEngine._analyze_capital_allocation(_stmt(operating_cash_flow=None))
    assert cap2.reinvestment_rate is None


def test_narrative_renders_yield_sentences():
    note = ReportRenderer._fcf_deployment_note(
        "META", "FY2025", "USD", 80_000_000_000.0,
        [("capital expenditure", 32_100_000_000.0, 0.45),
         ("share repurchases", 39_200_000_000.0, 0.55)],
        shareholder_yield=0.0392,
        reinvestment_rate=0.321,
    )
    assert "Shareholder yield (buybacks + dividends vs market cap): 3.9%." in note
    assert "Reinvestment rate (capex vs operating cash flow): 32.1%." in note
