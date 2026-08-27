"""Tests for core data models — validates typing, serialization, and edge cases.

Every model used in the pipeline must:
  - Serialize to JSON (for API responses)
  - Deserialize from JSON (for caching)
  - Handle None/missing fields gracefully
  - Validate inputs (reject bad data, don't silently accept)
"""
# Module: tests/test_models.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from research_analyst.enums import (
    ReportType,
    RiskCategory,
    RiskDuration,
    RiskNature,
    ScenarioType,
    SecurityType,
)
from research_analyst.models import (
    Assumption,
    CompanyProfile,
    Competitor,
    FinancialStatement,
    PriceData,
    PriceSeries,
    ReportOutput,
    ReportSection,
    ResearchRequest,
    RiskMatrix,
    StructuredRisk,
    TechnicalIndicators,
    ValuationRange,
    ValuationScenario,
    VariantPerception,
)


# ---------------------------------------------------------------------------
# ResearchRequest
# ---------------------------------------------------------------------------

class TestResearchRequest:
    """Test ResearchRequest validation and defaults."""

    def test_basic_creation(self) -> None:
        req = ResearchRequest(ticker="AAPL")
        assert req.ticker == "AAPL"
        assert req.report_types == [ReportType.COMPREHENSIVE]
        assert req.compare_tickers == []

    def test_ticker_uppercase(self) -> None:
        req = ResearchRequest(ticker="aapl")
        assert req.ticker == "AAPL"

    def test_ticker_strip(self) -> None:
        req = ResearchRequest(ticker="  msft  ")
        assert req.ticker == "MSFT"

    def test_ticker_too_long(self) -> None:
        with pytest.raises(Exception):
            ResearchRequest(ticker="A" * 11)

    def test_ticker_empty(self) -> None:
        with pytest.raises(Exception):
            ResearchRequest(ticker="")

    def test_compare_tickers_uppercase(self) -> None:
        req = ResearchRequest(ticker="AAPL", compare_tickers=["msft", "goog"])
        assert req.compare_tickers == ["MSFT", "GOOG"]

    def test_custom_report_types(self) -> None:
        req = ResearchRequest(
            ticker="AAPL",
            report_types=[ReportType.LONG_TERM, ReportType.TACTICAL],
        )
        assert len(req.report_types) == 2


# ---------------------------------------------------------------------------
# ReportType parsing
# ---------------------------------------------------------------------------

class TestReportType:
    """Test ReportType.from_user_input parsing."""

    def test_none_default(self) -> None:
        assert ReportType.from_user_input(None) == [ReportType.COMPREHENSIVE]

    def test_empty_default(self) -> None:
        assert ReportType.from_user_input("") == [ReportType.COMPREHENSIVE]

    def test_all(self) -> None:
        result = ReportType.from_user_input("all")
        assert ReportType.LONG_TERM in result
        assert ReportType.TACTICAL in result
        assert ReportType.COMPREHENSIVE in result

    def test_full_package(self) -> None:
        result = ReportType.from_user_input("full package")
        assert len(result) == 3

    def test_institutional(self) -> None:
        result = ReportType.from_user_input("institutional")
        assert len(result) == 3

    def test_long_term(self) -> None:
        assert ReportType.from_user_input("long_term") == [ReportType.LONG_TERM]

    def test_tactical(self) -> None:
        assert ReportType.from_user_input("tactical") == [ReportType.TACTICAL]

    def test_comprehensive(self) -> None:
        assert ReportType.from_user_input("comprehensive") == [ReportType.COMPREHENSIVE]

    def test_unknown_falls_back(self) -> None:
        assert ReportType.from_user_input("garbage") == [ReportType.COMPREHENSIVE]


# ---------------------------------------------------------------------------
# CompanyProfile
# ---------------------------------------------------------------------------

class TestCompanyProfile:
    """Test CompanyProfile creation and serialization."""

    def test_basic(self) -> None:
        p = CompanyProfile(
            ticker="AAPL",
            name="Apple Inc.",
            security_type=SecurityType.EQUITY,
            sector="Technology",
            market_cap=Decimal("3000000000000"),
        )
        assert p.ticker == "AAPL"
        assert p.security_type == SecurityType.EQUITY
        assert p.market_cap == Decimal("3000000000000")

    def test_json_roundtrip(self) -> None:
        p = CompanyProfile(
            ticker="SPY",
            name="SPDR S&P 500 ETF",
            security_type=SecurityType.ETF,
        )
        data = p.model_dump(mode="json")
        p2 = CompanyProfile.model_validate(data)
        assert p2.ticker == "SPY"
        assert p2.security_type == SecurityType.ETF


# ---------------------------------------------------------------------------
# FinancialStatement
# ---------------------------------------------------------------------------

class TestFinancialStatement:
    """Test FinancialStatement with typical and edge-case data."""

    def test_all_none(self) -> None:
        """All optional fields default to None without crashing."""
        fs = FinancialStatement(period="FY2025")
        assert fs.revenue is None
        assert fs.gross_margin is None

    def test_with_data(self) -> None:
        fs = FinancialStatement(
            period="FY2025",
            period_end_date=date(2025, 12, 31),
            revenue=Decimal("400000000000"),
            net_income=Decimal("100000000000"),
            gross_margin=0.45,
            operating_margin=0.30,
            roe=0.15,
        )
        assert fs.revenue == Decimal("400000000000")
        assert fs.gross_margin == 0.45


# ---------------------------------------------------------------------------
# PriceSeries
# ---------------------------------------------------------------------------

class TestPriceSeries:
    """Test PriceSeries with empty and populated data."""

    def test_empty(self) -> None:
        ps = PriceSeries(
            ticker="TEST",
            data=[],
            period_start=date.today(),
            period_end=date.today(),
        )
        assert ps.data == []
        assert ps.current_price == 0.0

    def test_with_data(self) -> None:
        pd1 = PriceData(
            date=date(2025, 1, 2), open=150.0, high=155.0,
            low=149.0, close=154.0, adj_close=154.0, volume=1000000,
        )
        ps = PriceSeries(
            ticker="TEST",
            data=[pd1],
            period_start=pd1.date,
            period_end=pd1.date,
            current_price=154.0,
        )
        assert ps.current_price == 154.0
        assert len(ps.data) == 1


# ---------------------------------------------------------------------------
# ValuationRange
# ---------------------------------------------------------------------------

class TestValuationRange:
    """Test ValuationRange and ASCII chart generation."""

    def test_ascii_chart(self) -> None:
        vr = ValuationRange(
            ticker="TEST",
            current_price=200.0,
            scenarios=[
                ValuationScenario(
                    scenario_type=ScenarioType.BULL, label="Bull Case",
                    assumptions=[], implied_price_low=240.0, implied_price_high=260.0,
                ),
                ValuationScenario(
                    scenario_type=ScenarioType.BASE, label="Base Case",
                    assumptions=[], implied_price_low=190.0, implied_price_high=210.0,
                ),
                ValuationScenario(
                    scenario_type=ScenarioType.BEAR, label="Bear Case",
                    assumptions=[], implied_price_low=140.0, implied_price_high=160.0,
                ),
            ],
        )
        chart = vr.ascii_chart()
        assert "Bull Case" in chart
        assert "Base Case" in chart
        assert "Bear Case" in chart
        assert "$240" in chart
        assert "$160" in chart

    def test_empty_scenarios(self) -> None:
        vr = ValuationRange(ticker="TEST", current_price=100.0, scenarios=[])
        assert vr.ascii_chart() == ""


# ---------------------------------------------------------------------------
# StructuredRisk
# ---------------------------------------------------------------------------

class TestStructuredRisk:
    """Test StructuredRisk model."""

    def test_creation(self) -> None:
        risk = StructuredRisk(
            title="Test Risk",
            description="A test risk for validation.",
            category=RiskCategory.OPERATIONAL,
            probability="Medium (20-50%)",
            impact="High",
            timing=RiskDuration.NEAR_TERM,
            nature=RiskNature.TRANSITORY,
        )
        assert risk.title == "Test Risk"
        assert risk.category == RiskCategory.OPERATIONAL
        assert risk.mitigants == []
        assert risk.second_order_effects == []


# ---------------------------------------------------------------------------
# ReportOutput
# ---------------------------------------------------------------------------

class TestReportOutput:
    """Test ReportOutput Markdown rendering."""

    def test_to_markdown(self) -> None:
        report = ReportOutput(
            report_type=ReportType.COMPREHENSIVE,
            ticker="AAPL",
            title="AAPL - Comprehensive Research Report",
            generated_at=datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc),
            sections=[
                ReportSection(
                    step_number=1,
                    title="Executive Summary",
                    content="Apple is a technology company.",
                ),
            ],
        )
        md = report.to_markdown()
        assert "AAPL" in md
        assert "Executive Summary" in md
        assert "Step 1" in md
        assert "Disclaimer" in md

    def test_disclaimer_always_present(self) -> None:
        report = ReportOutput(
            report_type=ReportType.TACTICAL,
            ticker="TEST",
            title="Test",
            generated_at=datetime.now(timezone.utc),
            sections=[],
        )
        md = report.to_markdown()
        assert "informational purposes only" in md.lower()


# ---------------------------------------------------------------------------
# TechnicalIndicators
# ---------------------------------------------------------------------------

class TestTechnicalIndicators:
    """Test TechnicalIndicators defaults and edge cases."""

    def test_defaults(self) -> None:
        ti = TechnicalIndicators(ticker="TEST", as_of_date=date.today())
        assert ti.rsi_14 is None
        assert ti.macd is None
        assert ti.support_levels == []
        assert ti.patterns_detected == []


# ---------------------------------------------------------------------------
# Assumption
# ---------------------------------------------------------------------------

class TestAssumption:
    """Test Assumption model."""

    def test_basic(self) -> None:
        a = Assumption(
            label="Revenue Growth",
            value="8.5%",
            source="Historical 3Y CAGR",
            confidence="Medium",
        )
        assert a.label == "Revenue Growth"
        assert a.confidence == "Medium"

    def test_data_gap_assumption(self) -> None:
        a = Assumption(
            label="WACC",
            value="9.0%",
            source="Data not available; assumption used: industry average",
            confidence="Low",
        )
        assert "Data not available" in a.source
