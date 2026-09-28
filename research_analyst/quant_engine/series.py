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

"""StatementSeries data contract shared by the Python quant engine.

A StatementSeries is the only input shape the engine understands: one
ticker, N fiscal periods, and every line item as an aligned
``list[float | None]``. Missing data is ``None``, never 0 — 0 is a number
and would corrupt ratios.

SIGN CONVENTION (the one rule): cash-flow outflows — capital expenditure,
share buybacks, dividends paid — are POSITIVE MAGNITUDES. An outflow of
$32.1B is the number 32100000000, not -32100000000.

UNITS: plain numbers in the statement currency. No cents/millions scaling
inside the engine — scale at the boundary, document at the call site.

ORDER: periods run oldest → newest (index 0 is the earliest period).
The engine never assumes provider order; the caller sorts by period end
date before building the series.

Ported from quant/src/types.ts. Pure data + validation; no I/O.
"""
# Module: research_analyst/quant_engine/series.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

from dataclasses import dataclass, field

#: A single aligned line-item series. ``None`` means missing — never 0.
Series = list["float | None"]


@dataclass
class FiscalPeriod:
    """One fiscal period label."""

    #: Human label, e.g. "FY2025".
    period: str
    #: ISO-8601 end date, e.g. "2025-12-31". None when unknown.
    period_end_date: str | None = None


@dataclass
class StatementSeries:
    """One ticker, N fiscal periods, every line item an aligned series."""

    ticker: str
    currency: str | None
    #: Oldest → newest. Every series below has exactly this length.
    periods: list[FiscalPeriod]

    # ---- income statement ----
    revenue: Series = field(default_factory=list)
    gross_profit: Series = field(default_factory=list)
    operating_income: Series = field(default_factory=list)
    ebit: Series = field(default_factory=list)
    net_income: Series = field(default_factory=list)
    eps_diluted: Series = field(default_factory=list)
    sga_expense: Series = field(default_factory=list)  # positive magnitude
    depreciation_amortization: Series = field(default_factory=list)  # positive magnitude

    # ---- cash flow statement (outflows as POSITIVE magnitudes) ----
    operating_cash_flow: Series = field(default_factory=list)
    capital_expenditure: Series = field(default_factory=list)
    free_cash_flow: Series = field(default_factory=list)
    dividends_paid: Series = field(default_factory=list)
    share_buybacks: Series = field(default_factory=list)

    # ---- balance sheet ----
    total_assets: Series = field(default_factory=list)
    total_equity: Series = field(default_factory=list)
    total_liabilities: Series = field(default_factory=list)
    retained_earnings: Series = field(default_factory=list)
    ppe_net: Series = field(default_factory=list)
    accounts_payable: Series = field(default_factory=list)
    total_debt: Series = field(default_factory=list)
    cash: Series = field(default_factory=list)
    current_assets: Series = field(default_factory=list)
    current_liabilities: Series = field(default_factory=list)
    inventory: Series = field(default_factory=list)
    receivables: Series = field(default_factory=list)

    # ---- other ----
    interest_expense: Series = field(default_factory=list)  # positive magnitude
    tax_expense: Series = field(default_factory=list)  # positive magnitude
    shares_outstanding: Series = field(default_factory=list)  # diluted, in shares
    price: Series = field(default_factory=list)  # period-end close, statement currency


#: Names of every numeric series on StatementSeries (for validation).
SERIES_KEYS: tuple[str, ...] = (
    "revenue",
    "gross_profit",
    "operating_income",
    "ebit",
    "net_income",
    "eps_diluted",
    "sga_expense",
    "depreciation_amortization",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
    "dividends_paid",
    "share_buybacks",
    "total_assets",
    "total_equity",
    "total_liabilities",
    "retained_earnings",
    "ppe_net",
    "accounts_payable",
    "total_debt",
    "cash",
    "current_assets",
    "current_liabilities",
    "inventory",
    "receivables",
    "interest_expense",
    "tax_expense",
    "shares_outstanding",
    "price",
)


def assert_valid_series(s: StatementSeries) -> None:
    """Validate that every series matches ``len(s.periods)``.

    Raises on programmer error (never on data gaps — gaps are None).
    Mirrors ``assertValidSeries`` in quant/src/types.ts.
    """
    n = len(s.periods)
    for key in SERIES_KEYS:
        values = getattr(s, key)
        if len(values) != n:
            raise ValueError(
                f"quant_engine: series {key!r} has length {len(values)}, "
                f"expected {n} (len(periods)) for {s.ticker}"
            )