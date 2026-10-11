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

"""Provider wiring tests: yfinance / SEC XBRL → quant Forensics inputs.

These prove the label mappings added on 2026-09-29 (provider side of the
quant-input wiring): interest/tax expense, SGA, depreciation & amortization,
retained earnings, net PPE, current assets/liabilities, receivables, EBIT
and share counts survive both providers' builders. Synthetic DataFrames and
a synthetic XBRL companyfacts doc — no live network.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

import pandas as pd

from research_analyst.providers.market_data import MarketDataProvider
from research_analyst.providers.sec_edgar import SECEdgarProvider


class _FakeTicker:
    def __init__(self, income, balance, cashflow) -> None:
        self.financials = income
        self.balance_sheet = balance
        self.cashflow = cashflow


def _yf_frames(alt_labels: bool = False):
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31")]
    if alt_labels:
        income_rows = [
            "Total Revenue", "Gross Profit", "Operating Income", "EBIT", "Net Income",
            "Diluted EPS", "Interest Expense", "Income Tax Expense",
            "Selling, General and Administrative", "Depreciation & Amortization",
            "Basic Shares Outstanding", "Diluted Shares Outstanding",
        ]
        balance_rows = [
            "Total Assets", "Total Liabilities Net Minority Interest", "Stockholders Equity",
            "Cash And Cash Equivalents", "Total Debt", "Current Assets", "Current Liabilities",
            "Retained Earnings", "Net Property, Plant & Equipment", "Accounts Receivable",
        ]
    else:
        income_rows = [
            "Total Revenue", "Gross Profit", "Operating Income", "EBIT", "Net Income",
            "Diluted EPS", "Interest Expense", "Tax Provision",
            "Selling General And Administrative", "Depreciation And Amortization",
            "Basic Average Shares", "Diluted Average Shares",
        ]
        balance_rows = [
            "Total Assets", "Total Liabilities Net Minority Interest", "Stockholders Equity",
            "Cash And Cash Equivalents", "Total Debt", "Total Current Assets",
            "Total Current Liabilities", "Retained Earnings", "Net PPE", "Net Receivables",
        ]
    cashflow_rows = [
        "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
        "Cash Dividends Paid", "Repurchase Of Capital Stock",
        "Depreciation And Amortization",
    ]
    income = pd.DataFrame(
        index=income_rows,
        data={
            cols[0]: [100000, 40000, 25000, 25000, 20000, 2.0, -3000, -4000,
                      -15000, -6000, 1_500_000_000, 1_510_000_000],
            cols[1]: [90000, 36000, 22000, 22000, 18000, 1.8, -2500, -3500,
                      -13500, -5000, 1_480_000_000, 1_490_000_000],
        },
    )
    balance = pd.DataFrame(
        index=balance_rows,
        data={
            cols[0]: [200000, 80000, 120000, 10000, 30000, 60000, 40000,
                      50000, 30000, 12000],
            cols[1]: [180000, 70000, 110000, 9000, 28000, 55000, 37000,
                      46000, 27000, 11000],
        },
    )
    cashflow = pd.DataFrame(
        index=cashflow_rows,
        data={
            cols[0]: [22000, -5000, 17000, -3000, -2000, 6000],
            cols[1]: [20000, -4500, 15500, -2800, -1800, 5000],
        },
    )
    return income, balance, cashflow


def _assert_quant_fields(stmt) -> None:
    assert stmt.period == "FY2024"
    assert stmt.ebit == 25000
    assert stmt.interest_expense == 3000
    assert stmt.tax_expense == 4000
    assert stmt.sga_expense == 15000
    assert stmt.depreciation_amortization == 6000
    assert stmt.current_assets == 60000
    assert stmt.current_liabilities == 40000
    assert stmt.retained_earnings == 50000
    assert stmt.ppe_net == 30000
    assert stmt.receivables == 12000
    assert stmt.shares_outstanding == 1_500_000_000
    assert stmt.shares_diluted == 1_510_000_000


def _provider_with_fake_yf(monkeypatch, income, balance, cashflow) -> MarketDataProvider:
    """MarketDataProvider whose yfinance ticker is a synthetic stub."""
    provider = MarketDataProvider()
    fake = _FakeTicker(income, balance, cashflow)

    async def _fake_yf_ticker(ticker: str):
        return fake

    monkeypatch.setattr(MarketDataProvider, "_yf_ticker", staticmethod(_fake_yf_ticker))
    return provider


def _run(coro):
    return asyncio.run(coro)


def test_yfinance_builder_maps_quant_fields(monkeypatch):
    income, balance, cashflow = _yf_frames(alt_labels=False)
    provider = _provider_with_fake_yf(monkeypatch, income, balance, cashflow)
    with TemporaryDirectory() as tmp:
        from research_analyst.providers.market_data import _DiskCache

        provider._cache = _DiskCache(cache_dir=Path(tmp), ttl_seconds=0)
        stmts = _run(provider.get_financials("TEST"))
    assert len(stmts) == 2
    _assert_quant_fields(stmts[0])


def test_yfinance_builder_accepts_alias_row_labels(monkeypatch):
    income, balance, cashflow = _yf_frames(alt_labels=True)
    provider = _provider_with_fake_yf(monkeypatch, income, balance, cashflow)
    with TemporaryDirectory() as tmp:
        from research_analyst.providers.market_data import _DiskCache

        provider._cache = _DiskCache(cache_dir=Path(tmp), ttl_seconds=0)
        stmts = _run(provider.get_financials("TEST"))
    assert len(stmts) == 2
    _assert_quant_fields(stmts[0])


def test_yfinance_builder_ebit_falls_back_to_operating_income(monkeypatch):
    income, balance, cashflow = _yf_frames(alt_labels=False)
    income = income.drop(index=["EBIT"])
    assert "EBIT" not in income.index
    provider = _provider_with_fake_yf(monkeypatch, income, balance, cashflow)
    with TemporaryDirectory() as tmp:
        from research_analyst.providers.market_data import _DiskCache

        provider._cache = _DiskCache(cache_dir=Path(tmp), ttl_seconds=0)
        stmts = _run(provider.get_financials("TEST"))
    assert stmts[0].ebit == 25000  # == operating income


def _sec_companyfacts() -> dict:
    """Minimal companyfacts doc covering the quant-wiring concepts."""

    def unit(v):
        return {
            "units": {
                "USD": [
                    {"form": "10-K", "end": "2024-12-31", "val": v},
                    {"form": "10-K", "end": "2023-12-31", "val": v},
                ]
            }
        }

    def share_unit(v):
        return {
            "units": {
                "shares": [
                    {"form": "10-K", "end": "2024-12-31", "val": v},
                    {"form": "10-K", "end": "2023-12-31", "val": v},
                ]
            }
        }

    return {
        "facts": {
            "us-gaap": {
                "Revenues": unit(100000),
                "NetIncomeLoss": unit(20000),
                "Assets": unit(200000),
                "Liabilities": unit(80000),
                "StockholdersEquity": unit(120000),
                "OperatingIncomeLoss": unit(25000),
                "GrossProfit": unit(40000),
                "EarningsBeforeInterestAndTaxesItem": unit(26000),
                "CashAndCashEquivalentsAtCarryingValue": unit(10000),
                "LongTermDebt": unit(30000),
                "NetCashProvidedByOperatingActivities": unit(22000),
                "PaymentsToAcquirePropertyPlantAndEquipment": unit(5000),
                "EarningsPerShareDiluted": unit(2.0),
                "WeightedAverageNumberOfDilutedSharesOutstanding": share_unit(1_510_000_000),
                "CommonStockSharesOutstanding": share_unit(1_500_000_000),
                "InterestExpense": unit(3000),
                "IncomeTaxExpenseBenefit": unit(4000),
                "SellingGeneralAndAdministrativeExpense": unit(15000),
                "DepreciationDepletionAndAmortization": unit(6000),
                "RetainedEarningsAccumulatedDeficit": unit(50000),
                "AssetsCurrent": unit(60000),
                "LiabilitiesCurrent": unit(40000),
                "PropertyPlantAndEquipmentNet": unit(30000),
                "AccountsReceivableNetCurrent": unit(12000),
            }
        }
    }


async def _sec_financials():
    provider = SECEdgarProvider()
    provider._resolve_cik = AsyncMock(return_value="320193")
    provider._get = AsyncMock(return_value=_sec_companyfacts())
    return await provider.get_financials("AAPL"), provider


def test_sec_builder_maps_quant_fields():
    stmts, provider = _run(_sec_financials())
    assert len(stmts) == 2
    s = stmts[0]
    assert s.period == "FY2024"
    assert s.ebit == 26000
    assert s.interest_expense == 3000
    assert s.tax_expense == 4000
    assert s.sga_expense == 15000
    assert s.depreciation_amortization == 6000
    assert s.retained_earnings == 50000
    assert s.current_assets == 60000
    assert s.current_liabilities == 40000
    assert s.ppe_net == 30000
    assert s.receivables == 12000
    assert s.shares_outstanding == 1_500_000_000
    assert s.shares_diluted == 1_510_000_000


def test_sec_builder_fetches_companyfacts_once_for_all_concepts():
    stmts, provider = _run(_sec_financials())
    assert len(stmts) == 2
    assert provider._get.await_count == 1


def test_sec_builder_ebit_falls_back_to_operating_income():
    facts = _sec_companyfacts()
    del facts["facts"]["us-gaap"]["EarningsBeforeInterestAndTaxesItem"]

    async def _run_():
        provider = SECEdgarProvider()
        provider._resolve_cik = AsyncMock(return_value="320193")
        provider._get = AsyncMock(return_value=facts)
        return await provider.get_financials("AAPL")

    stmts = _run(_run_())
    assert stmts[0].ebit == 25000  # == operating income
