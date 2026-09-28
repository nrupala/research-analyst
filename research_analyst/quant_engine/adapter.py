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

"""Adapter: product ``FinancialStatement`` models → quant-engine ``StatementSeries``.

Bridges the Research Analyst data layer (pydantic models from the yfinance /
SEC EDGAR providers) to the pure-function quant engine. Missing values stay
missing; outflow series are normalized to positive magnitudes per the engine's
TypeScript contract (quant/src/types.ts).

Interest expense and tax expense are NOT fetched by any provider (verified
2026-09-28: no ``interest_expense``/``tax_expense`` in models.py or the
provider payloads), so those series are left all-None. The operating tax
rate (spec amendment A1) is therefore typically unavailable — callers must
surface that in their "missing inputs" list rather than fabricate a rate.
"""
# Module: research_analyst/quant_engine/adapter.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

from ..models import FinancialStatement
from .series import FiscalPeriod, StatementSeries, assert_valid_series

__all__ = ["from_financial_statements", "MISSING_ENGINE_INPUTS"]


#: Engine series keys that the product data layer cannot supply (verified
#: against models.py + providers on 2026-09-28). Rendered in "missing inputs".
MISSING_ENGINE_INPUTS: tuple[str, ...] = (
    "interest_expense",
    "tax_expense",
)


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # NaN / infinities are not usable observations — treat as missing.
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def from_financial_statements(
    statements: list[FinancialStatement], ticker: str
) -> StatementSeries:
    """Build a :class:`StatementSeries` from product financial statements.

    Orders periods oldest → newest by ``period_end_date`` (statements without
    a date sort first, stably). Every line item is mapped Decimal → float,
    missing → None. Capex, dividends paid and share buybacks are normalized
    to positive outflow magnitudes via ``abs()`` per the engine contract.

    Raises:
        ValueError: on programmer/shape errors via :func:`assert_valid_series`.
    """
    ordered = sorted(statements, key=lambda s: s.period_end_date or date.min)

    def col(fn: Callable[[FinancialStatement], Decimal | float | int | None]) -> list[float | None]:
        return [_to_float(fn(s)) for s in ordered]

    def outflow(fn: Callable[[FinancialStatement], Decimal | float | int | None]) -> list[float | None]:
        out: list[float | None] = []
        for s in ordered:
            v = _to_float(fn(s))
            out.append(abs(v) if v is not None else None)
        return out

    def shares(s: FinancialStatement) -> float | None:
        # Diluted share count is the engine's per-share denominator.
        v = _to_float(s.shares_diluted)
        return v if v is not None else _to_float(s.shares_outstanding)

    n = len(ordered)
    blank = [None] * n  # unmapped engine keys stay all-None (never fabricated)
    series = StatementSeries(
        ticker=ticker,
        currency=None,  # set by callers that know the listing currency
        periods=[
            FiscalPeriod(
                period=s.period,
                period_end_date=s.period_end_date.isoformat() if s.period_end_date else None,
            )
            for s in ordered
        ],
        # ---- income statement ----
        revenue=col(lambda s: s.revenue),
        gross_profit=col(lambda s: s.gross_profit),
        operating_income=col(lambda s: s.operating_income),
        ebit=col(lambda s: s.ebit),
        net_income=col(lambda s: s.net_income),
        eps_diluted=col(lambda s: s.eps_diluted),
        sga_expense=list(blank),
        depreciation_amortization=list(blank),
        # ---- cash flow (outflows as positive magnitudes) ----
        operating_cash_flow=col(lambda s: s.operating_cash_flow),
        capital_expenditure=outflow(lambda s: s.capex),
        free_cash_flow=col(lambda s: s.free_cash_flow),
        dividends_paid=outflow(lambda s: s.dividends_paid),
        share_buybacks=outflow(lambda s: s.share_buybacks),
        # ---- balance sheet ----
        total_assets=col(lambda s: s.total_assets),
        total_equity=col(lambda s: s.total_equity),
        total_liabilities=col(lambda s: s.total_liabilities),
        retained_earnings=list(blank),
        ppe_net=list(blank),
        accounts_payable=list(blank),
        total_debt=col(lambda s: s.total_debt),
        cash=col(lambda s: s.cash_and_equivalents),
        current_assets=col(lambda s: s.current_assets),
        current_liabilities=col(lambda s: s.current_liabilities),
        inventory=list(blank),
        receivables=list(blank),
        # ---- other ----
        interest_expense=list(blank),
        tax_expense=list(blank),
        shares_outstanding=[shares(s) for s in ordered],
        price=list(blank),
    )
    assert_valid_series(series)
    return series