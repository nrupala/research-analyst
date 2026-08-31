"""Tests for the Slice A.3d currency sweep in VisualEngine (reports/visuals.py).

Every money-bearing visual method now renders in the security's own currency:
  * methods that receive ``profile`` read ``profile.currency`` internally
    (``table_key_metrics``);
  * the other seven take a ``currency: str | None = None`` keyword.
USD / None stays byte-identical to the pre-sweep output; INR localises to the
rupee symbol; CHF uses the trailing-space "CHF " form.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from research_analyst.enums import ScenarioType, SecurityType
from research_analyst.models import (
    CompanyProfile,
    Competitor,
    DividendAnalysis,
    FinancialStatement,
    ValuationRange,
    ValuationScenario,
)
from research_analyst.reports.visuals import VisualEngine

RUPEE = "\u20b9"


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


def _fin(period: str) -> FinancialStatement:
    return FinancialStatement(
        period=period,
        period_end_date=date(int(period[-4:]), 12, 31),
        revenue=Decimal("1000000000"),
        gross_profit=Decimal("400000000"),
        operating_income=Decimal("300000000"),
        net_income=Decimal("200000000"),
        free_cash_flow=Decimal("150000000"),
        gross_margin=0.40,
        operating_margin=0.30,
        net_margin=0.20,
        eps_diluted=5.0,
        roe=0.15,
        debt_to_equity=0.5,
    )


def _financials() -> list[FinancialStatement]:
    return [_fin("FY2025"), _fin("FY2024")]


def _valuation() -> ValuationRange:
    scenario = ValuationScenario(
        scenario_type=next(iter(ScenarioType)),
        label="Base Case",
        assumptions=[],
        implied_price_low=90.0,
        implied_price_high=110.0,
    )
    return ValuationRange(ticker="TEST", current_price=100.0, scenarios=[scenario])


def _div() -> DividendAnalysis:
    return DividendAnalysis(
        ticker="TEST",
        pays_dividend=True,
        annual_dividend_rate=2.5,
        current_yield=0.025,
        annual_dividends={"2023": 2.0, "2024": 2.25, "2025": 2.5},
    )


def _txt(rv) -> str:
    body = rv.content or ""
    if body.startswith("{"):
        try:
            body = json.dumps(json.loads(body), ensure_ascii=False)
        except ValueError:
            pass
    return body + "\n" + (rv.caption or "")


class TestVisualsCurrencyUSD:
    def test_financial_trends(self):
        t = _txt(VisualEngine.plotly_financial_trends(_financials(), "TEST"))
        assert "Revenue ($B)" in t
        assert "Revenue in billions USD" in t
        assert RUPEE not in t

    def test_scenario_valuation(self):
        t = _txt(VisualEngine.plotly_scenario_valuation(_valuation()))
        assert "Price ($)" in t
        assert "$90 \u2013 $110" in t  # em-dash range (Phase 3 presentation polish)
        assert "Current price: $100.00" in t
        assert RUPEE not in t

    def test_ascii_scenario(self):
        assert "Current price: $100.00." in _txt(VisualEngine.ascii_scenario_chart(_valuation()))

    def test_key_metrics(self):
        t = _txt(VisualEngine.table_key_metrics(_profile("USD"), _financials(), 100.0, 20.0))
        assert "| **Current Price** | $100.00 |" in t
        assert "$2.5B" in t
        assert RUPEE not in t

    def test_peer_comparison(self):
        peers = [Competitor(ticker="PR", name="Peer", market_cap=Decimal("5000000000"))]
        t = _txt(VisualEngine.table_peer_comparison("TEST", peers))
        assert "Mkt Cap ($B)" in t
        assert "$5.0" in t
        assert RUPEE not in t

    def test_financial_summary(self):
        t = _txt(VisualEngine.table_financial_summary(_financials()))
        assert "$1.00B" in t
        assert RUPEE not in t

    def test_dividend_summary(self):
        t = _txt(VisualEngine.table_dividend_summary(_div()))
        assert "| **Annual Rate** | $2.50/share |" in t
        assert RUPEE not in t

    def test_dividend_history(self):
        t = _txt(VisualEngine.plotly_dividend_history(_div()))
        assert "DPS ($)" in t
        assert RUPEE not in t


class TestVisualsCurrencyINR:
    def test_financial_trends(self):
        t = _txt(VisualEngine.plotly_financial_trends(_financials(), "TEST", currency="INR"))
        assert f"Revenue ({RUPEE}B)" in t
        assert "Revenue in billions INR" in t
        assert "($B)" not in t

    def test_scenario_valuation(self):
        t = _txt(VisualEngine.plotly_scenario_valuation(_valuation(), currency="INR"))
        assert f"Price ({RUPEE})" in t
        assert f"{RUPEE}90 \u2013 {RUPEE}110" in t  # em-dash range (Phase 3 polish)
        assert f"Current price: {RUPEE}100.00" in t

    def test_ascii_scenario(self):
        assert f"Current price: {RUPEE}100.00." in _txt(VisualEngine.ascii_scenario_chart(_valuation(), currency="INR"))

    def test_key_metrics(self):
        t = _txt(VisualEngine.table_key_metrics(_profile("INR"), _financials(), 100.0, 20.0))
        assert f"| **Current Price** | {RUPEE}100.00 |" in t
        assert f"{RUPEE}2.5B" in t

    def test_peer_comparison(self):
        peers = [Competitor(ticker="PR", name="Peer", market_cap=Decimal("5000000000"))]
        t = _txt(VisualEngine.table_peer_comparison("TEST", peers, currency="INR"))
        assert f"Mkt Cap ({RUPEE}B)" in t
        assert f"{RUPEE}5.0" in t

    def test_financial_summary(self):
        t = _txt(VisualEngine.table_financial_summary(_financials(), currency="INR"))
        assert f"{RUPEE}1.00B" in t

    def test_dividend_summary(self):
        t = _txt(VisualEngine.table_dividend_summary(_div(), currency="INR"))
        assert f"| **Annual Rate** | {RUPEE}2.50/share |" in t

    def test_dividend_history(self):
        t = _txt(VisualEngine.plotly_dividend_history(_div(), currency="INR"))
        assert f"DPS ({RUPEE})" in t


class TestVisualsCurrencyCHF:
    def test_chf_trailing_space(self):
        t = _txt(VisualEngine.table_key_metrics(_profile("CHF"), _financials(), 100.0, 20.0))
        assert "| **Current Price** | CHF 100.00 |" in t
