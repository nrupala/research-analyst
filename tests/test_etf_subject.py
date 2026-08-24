"""Tests for ETF-as-subject report path."""
# Module: tests/test_etf_subject.py | Version: 0.3.0 | Updated: 2026-06-02

import pytest
from datetime import datetime

from research_analyst.models import (
    CompanyProfile,
    DividendData,
    FinancialStatement,
    ReportOutput,
    SecurityType,
)
from research_analyst.engines.etf import ETFEngine
from research_analyst.reports.renderer import ReportRenderer


def test_etf_engine_basic():
    """Test ETF engine with minimal data."""
    engine = ETFEngine()
    profile = CompanyProfile(
        ticker="SPY",
        name="SPDR S&P 500 ETF",
        security_type=SecurityType.ETF,
        market_cap=Decimal("400000000000"),
        currency="USD",
    )
    
    stmt = FinancialStatement(
        period="FY2026",
        expense_ratio=Decimal("0.0009"),
    )
    
    result = engine.analyze(profile, [stmt])
    assert "expense_ratio" in result
    assert result["expense_ratio"] == Decimal("0.0009")
    assert "aum" in result
    assert "fund_overview" not in result  # No description
    assert len(result["data_gaps"]) > 0


def test_etf_block_in_renderer():
    """Test that ETF subjects get the ETF block in reports."""
    renderer = ReportRenderer()
    profile = CompanyProfile(
        ticker="VTI",
        name="Vanguard Total Stock Market ETF",
        security_type=SecurityType.ETF,
        description="Seeks to track CRSP US Total Market Index",
        market_cap=Decimal("1200000000000"),
        currency="USD",
    )
    
    # Mock ETF engine result
    etf_analysis = {
        "expense_ratio": Decimal("0.0003"),
        "fund_overview": profile.description,
        "assumptions": [
            Assumption(
                label="Expense Ratio",
                value="0.03%",
                source="Latest financial statement",
            )
        ],
    }
    
    # Render a report (minimal inputs)
    report = renderer.render(
        report_type=ReportType.COMPREHENSIVE,
        profile=profile,
        prices=PriceSeries(ticker="VTI", current_price=210.0),
        financials=[],
        etf=etf_analysis,
    )
    
    # Verify ETF block appears
    content = report.sections[0].content
    assert "ETF Overview" in content
    assert "0.03%" in content  # Expense ratio
    
    # Non-ETF test remains unchanged
    equity_profile = CompanyProfile(
        ticker="AAPL",
        security_type=SecurityType.EQUITY,
    )
    equity_report = renderer.render(
        report_type=ReportType.COMPREHENSIVE,
        profile=equity_profile,
        prices=PriceSeries(ticker="AAPL", current_price=180.0),
        financials=[],
    )
    assert "ETF Overview" not in equity_report.sections[0].content