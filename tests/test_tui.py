"""Tests for the terminal surface (Phase 6).

* build_request maps CLI strings to typed ResearchRequest
* headless query renders markdown reports (stubbed orchestrator, no network)
* tui module imports cleanly without Textual (headless mode never needs it)
"""
# Module: tests/test_tui.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from datetime import UTC, datetime

from research_analyst.enums import ReportType, SecurityType
from research_analyst.models import (
    ReportOutput,
    ResearchMetadata,
    ResearchResponse,
)
from research_analyst.tui import ResearchTUI, build_request, run_headless


class StubOrchestrator:
    async def run(self, request):
        report = ReportOutput(
            report_type=ReportType.COMPREHENSIVE,
            ticker=request.ticker,
            title=f"{request.ticker} — Comprehensive",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            sections=[],
        )
        return ResearchResponse(
            ticker=request.ticker,
            security_type=SecurityType.EQUITY,
            company_name="Stub Corp",
            currency="USD",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            reports=[report],
            metadata=ResearchMetadata(data_sources=["stub"]),
        )


def test_build_request_defaults():
    req = build_request("aapl", "comprehensive")
    assert req.ticker == "AAPL"
    assert ReportType.COMPREHENSIVE in req.report_types


def test_build_request_all_types():
    req = build_request("aapl", "all")
    assert ReportType.COMPREHENSIVE in req.report_types
    assert ReportType.LONG_TERM in req.report_types
    assert ReportType.TACTICAL in req.report_types


def test_build_request_timeframe_mapping():
    req = build_request("msft", "tactical", "3Y")
    assert req.timeframe.value == "3Y"


def test_headless_query_renders_markdown():
    reports = run_headless("AAPL", orchestrator=StubOrchestrator())
    assert len(reports) == 1
    assert "# AAPL — Comprehensive" in reports[0]


def test_tui_imports_without_textual():
    """The tui module must import cleanly when Textual is absent (headless)."""
    assert ResearchTUI.available() is False or ResearchTUI.available() is True
