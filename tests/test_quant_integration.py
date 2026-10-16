"""F1.8 — report ↔ quant integration: ONE merged statements path.

Before F1.8 the quant endpoint fetched statements on its own
(yfinance, else SEC) while the research pipeline merged four sources
behind a completeness floor (CVM → EDINET → yfinance → SEC). For a
CVM-led ticker the report and the quant tab could compute over
different statements. These tests pin the shared path:

- ``fetch_merged_financials`` applies the floor and lead order.
- The quant endpoint consumes the bundle and declares its source.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from research_analyst.models import FinancialStatement
from research_analyst.orchestrator import (
    FinancialsBundle,
    ResearchOrchestrator,
    statement_lead_label,
)


def _stmt(year: int, revenue: str | None = "1000", net: str | None = "100"):
    return FinancialStatement(
        period=f"FY{year}",
        period_end_date=date(year, 12, 31),
        revenue=Decimal(revenue) if revenue is not None else None,
        net_income=Decimal(net) if net is not None else None,
        total_assets=Decimal("2000"),
        total_equity=Decimal("1200"),
    )


def _orch(yf=(), sec=(), cvm=(), edinet=()):
    orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
    orch._fetch_yf_financials = AsyncMock(return_value=list(yf))
    orch._fetch_sec_financials = AsyncMock(return_value=list(sec))
    orch._fetch_cvm_financials = AsyncMock(return_value=list(cvm))
    orch._fetch_edinet_financials = AsyncMock(return_value=list(edinet))
    return orch


def _bundle(orch) -> FinancialsBundle:
    return asyncio.run(orch.fetch_merged_financials("X", "Name", []))


def test_cvm_complete_leads_over_yfinance():
    cvm = [_stmt(2025), _stmt(2024)]
    yf = [_stmt(2025, revenue="9999")]
    b = _bundle(_orch(yf=yf, cvm=cvm))
    assert b.lead == "cvm"
    assert b.financials is b.cvm
    assert statement_lead_label(b.lead).startswith("CVM (financial statements")


def test_cvm_incomplete_falls_back_to_yfinance():
    # Newest CVM statement missing net income -> below the floor.
    cvm = [_stmt(2025, net=None)]
    yf = [_stmt(2025)]
    b = _bundle(_orch(yf=yf, cvm=cvm))
    assert b.lead == "yfinance"
    assert b.financials is b.yf


def test_edinet_leads_when_cvm_absent():
    edinet = [_stmt(2025)]
    b = _bundle(_orch(yf=[_stmt(2025, revenue="1")], edinet=edinet))
    assert b.lead == "edinet"
    assert b.financials is b.edinet


def test_sec_is_the_final_fallback():
    sec = [_stmt(2025)]
    b = _bundle(_orch(sec=sec))
    assert b.lead == "sec"
    assert b.financials is b.sec
    assert statement_lead_label("sec") == "SEC EDGAR XBRL (financial statements)"


def test_fetcher_exception_degrades_to_empty():
    orch = _orch(yf=[_stmt(2025)])
    orch._fetch_cvm_financials = AsyncMock(side_effect=RuntimeError("boom"))
    warnings: list[str] = []
    b = asyncio.run(orch.fetch_merged_financials("X", "Name", warnings))
    assert b.cvm == []
    assert b.lead == "yfinance"
    assert any("CVM financials unavailable" in w for w in warnings)


def test_quant_endpoint_declares_cvm_and_uses_its_statements():
    from starlette.testclient import TestClient

    from research_analyst.enums import SecurityType
    from research_analyst.models import CompanyProfile, PriceSeries
    from research_analyst.server import create_app

    cvm = [_stmt(2022 + i, revenue=str(1000 + i)) for i in range(4)]
    yf = [_stmt(2022 + i, revenue="777777") for i in range(4)]
    orch = AsyncMock()
    orch.fetch_merged_financials = AsyncMock(
        return_value=FinancialsBundle(
            financials=cvm, lead="cvm", yf=yf, sec=[], cvm=cvm, edinet=[]
        )
    )
    profile = CompanyProfile(
        ticker="PETR4.SA",
        name="Petroleo Brasileiro SA",
        security_type=SecurityType.EQUITY,
        currency="BRL",
    )
    mp = AsyncMock()
    mp.get_company_profile = AsyncMock(return_value=profile)
    mp.get_price_series = AsyncMock(
        return_value=PriceSeries(
            ticker="PETR4.SA",
            data=[],
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            current_price=40.0,
        )
    )
    with patch("research_analyst.server.MarketDataProvider", return_value=mp):
        client = TestClient(create_app(orchestrator=orch))
    r = client.get("/api/research/quant", params={"ticker": "PETR4.SA"})
    assert r.status_code == 200
    body = r.json()
    assert body["statements_source"].startswith("CVM (financial statements")
    # The CVM statements' revenue path (1000..1003) drives the trends —
    # not the yfinance decoy revenue (777777 flat).
    assert body["trends"]["revenue_cagr"] is not None
    assert body["trends"]["revenue_cagr"] > 0
