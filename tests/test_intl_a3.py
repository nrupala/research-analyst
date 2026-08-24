"""Slice A.3 tests: currency-aware valuation output + intl ticker gate (offline)."""
from datetime import datetime
from research_analyst.models import (
    ResearchRequest, ValuationRange, ValuationScenario, ReportOutput, currency_symbol,
)
from research_analyst.enums import ScenarioType, ReportType


def test_currency_symbol():
    assert currency_symbol("USD") == "$"
    assert currency_symbol("INR") == "\u20b9"
    assert currency_symbol("GBP") == "\u00a3"
    assert currency_symbol("gbp") == "\u00a3"
    assert currency_symbol("GBp").strip() == "GBp"   # pence: labeled, not mis-symbolled
    assert currency_symbol("XYZ") == "XYZ "
    assert currency_symbol(None) == "$"


def test_ticker_accepts_intl_suffix():
    assert ResearchRequest(ticker="reliance.ns").ticker == "RELIANCE.NS"   # 11 chars, was rejected
    assert ResearchRequest(ticker="0700.hk").ticker == "0700.HK"


def test_valuation_ascii_uses_currency():
    vr = ValuationRange(
        ticker="RELIANCE.NS", current_price=1400.0, currency="INR",
        scenarios=[ValuationScenario(scenario_type=ScenarioType.BASE, label="Base Case",
                   assumptions=[], implied_price_low=1300.0, implied_price_high=1600.0)],
    )
    chart = vr.ascii_chart()
    assert "\u20b9" in chart and "$" not in chart


def test_report_markdown_currency_and_usd():
    vr = ValuationRange(ticker="RELIANCE.NS", current_price=1400.0, currency="INR",
                        current_price_usd=16.8, scenarios=[])
    rpt = ReportOutput(report_type=ReportType.COMPREHENSIVE, ticker="RELIANCE.NS",
                       title="X", generated_at=datetime.now(), sections=[], valuation=vr)
    md = rpt.to_markdown()
    assert "\u20b9" in md and "USD" in md
