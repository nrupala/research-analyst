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

"""Wiring tests: adapter, quant report section, and quant API response model.

Covers the product integration of the ported quant engine — not the engine
math itself (that is tests/test_quant_engine_parity.py).
"""
# Module: tests/test_quant_wiring.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

from datetime import date
from decimal import Decimal

from research_analyst.api_models import QuantAPIResponse
from research_analyst.models import FinancialStatement
from research_analyst.quant_engine.adapter import (
    from_financial_statements,
    missing_series_inputs,
)
from research_analyst.reports.quant_section import (
    QUANT_SECTION_TITLE,
    compute_quant_results,
    render_quant_section,
)


def _stmt(year: int, **kw) -> FinancialStatement:
    base = dict(
        period=f"FY{year}",
        period_end_date=date(year, 12, 31),
        revenue=Decimal("1000"),
        gross_profit=Decimal("400"),
        net_income=Decimal("100"),
        total_assets=Decimal("2000"),
        total_equity=Decimal("1200"),
        operating_cash_flow=Decimal("150"),
        eps_diluted=2.0,
        shares_outstanding=500,
    )
    base.update(kw)
    return FinancialStatement(**base)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def test_adapter_orders_oldest_to_newest():
    stmts = [_stmt(2024), _stmt(2022), _stmt(2023)]  # scrambled input
    s = from_financial_statements(stmts, "TST")
    assert [p.period for p in s.periods] == ["FY2022", "FY2023", "FY2024"]
    # Aligned: revenue follows the period order, not the input order.
    assert s.revenue == [1000.0, 1000.0, 1000.0]


def test_adapter_normalizes_outflow_signs_to_positive_magnitudes():
    stmts = [
        _stmt(
            2023, capex=Decimal("-80"), dividends_paid=Decimal("-20"), share_buybacks=Decimal("-10")
        ),
        _stmt(2024, capex=Decimal("-90"), dividends_paid=Decimal("-25"), share_buybacks=None),
    ]
    s = from_financial_statements(stmts, "TST")
    assert s.capital_expenditure == [80.0, 90.0]
    assert s.dividends_paid == [20.0, 25.0]
    assert s.share_buybacks == [10.0, None]  # missing stays missing


def test_adapter_maps_decimal_to_float_and_missing_to_none():
    stmts = [_stmt(2024, ebit=None, total_debt=Decimal("300"))]
    s = from_financial_statements(stmts, "TST")
    assert s.ebit == [None]
    assert s.total_debt == [300.0]
    assert isinstance(s.revenue[0], float)


def test_adapter_maps_interest_tax_and_balance_sheet_fields():
    stmts = [
        _stmt(
            2024,
            ebit=Decimal("250"),
            interest_expense=Decimal("-30"),
            tax_expense=Decimal("-40"),
            sga_expense=Decimal("-120"),
            depreciation_amortization=Decimal("-35"),
            retained_earnings=Decimal("500"),
            ppe_net=Decimal("300"),
            receivables=Decimal("90"),
        )
    ]
    s = from_financial_statements(stmts, "TST")
    assert s.ebit == [250.0]
    # Expense-outflow series normalize to positive magnitudes.
    assert s.interest_expense == [30.0]
    assert s.tax_expense == [40.0]
    assert s.sga_expense == [120.0]
    assert s.depreciation_amortization == [35.0]
    assert s.retained_earnings == [500.0]
    assert s.ppe_net == [300.0]
    assert s.receivables == [90.0]


def test_missing_series_inputs_lists_only_entirely_absent_engine_inputs():
    # Sparse statements carry only the trend line items the fixture provides.
    s = from_financial_statements([_stmt(2023), _stmt(2024)], "TST")
    gaps = missing_series_inputs(s)
    assert "interest_expense" in gaps
    assert "tax_expense" in gaps
    assert "current_assets" in gaps
    assert "retained_earnings" in gaps
    assert "receivables" in gaps
    assert "price" in gaps  # price is only supplied by the server boundary
    assert "net_income" not in gaps  # present in the fixture


def test_missing_series_inputs_empty_when_every_key_wired():
    stmts = [
        _stmt(
            2024,
            ebit=Decimal("250"),
            interest_expense=Decimal("-30"),
            tax_expense=Decimal("-40"),
            sga_expense=Decimal("-120"),
            depreciation_amortization=Decimal("-35"),
            retained_earnings=Decimal("500"),
            ppe_net=Decimal("300"),
            receivables=Decimal("90"),
            current_assets=Decimal("600"),
            current_liabilities=Decimal("400"),
        )
    ]
    s = from_financial_statements(stmts, "TST")
    s.price[-1] = 100.0  # what the server does with the latest observed price
    assert missing_series_inputs(s) == []


def test_adapter_prefers_diluted_shares():
    stmts = [_stmt(2024, shares_outstanding=500, shares_diluted=520)]
    s = from_financial_statements(stmts, "TST")
    assert s.shares_outstanding == [520.0]


# ---------------------------------------------------------------------------
# Quant report section
# ---------------------------------------------------------------------------


def test_section_returns_none_without_periods():
    s = from_financial_statements([], "TST")
    assert render_quant_section(s, {}) is None


def test_section_renders_with_missing_input_disclosure_on_sparse_data():
    # Sparse: revenue/net income only — forensics/valuation/allocation
    # inputs are absent.
    stmts = [
        FinancialStatement(
            period=f"FY{2022 + i}",
            period_end_date=date(2022 + i, 12, 31),
            revenue=Decimal(str(1000 + i * 100)),
            net_income=Decimal(str(100 + i * 10)),
        )
        for i in range(3)
    ]
    s = from_financial_statements(stmts, "SPARSE")
    sec = render_quant_section(s, {"currency": "USD"})
    assert sec is not None
    assert sec.step_number == 0  # never a fake "Step 8"
    assert sec.title == QUANT_SECTION_TITLE
    # Missing-input disclosure is present and names the gaps.
    gaps = " ".join(sec.data_gaps)
    assert "interest_expense" in gaps
    assert "altman_z" in gaps or "dupont_inputs" in gaps
    # Altman/Beneish framed as screens, not verdicts.
    assert "screens, not verdicts" in sec.content
    # No buy/sell/hold language.
    for word in ("buy ", "sell ", "hold ", "Buy-rated", "Strong Buy"):
        assert word not in sec.content


def test_section_shows_both_implied_growth_models_separately():
    stmts = [
        _stmt(
            2022 + i,
            revenue=Decimal(str(1000 * (1.1**i))),
            net_income=Decimal(str(100 * (1.1**i))),
            free_cash_flow=Decimal(str(80 * (1.1**i))),
        )
        for i in range(5)
    ]
    s = from_financial_statements(stmts, "GROW")
    sec = render_quant_section(
        s,
        {"enterprise_value": 5000.0, "currency": "USD", "discount_rate": 0.09},
    )
    assert sec is not None
    assert "Implied explicit-stage growth" in sec.content
    assert "Implied perpetual growth" in sec.content
    # The discount-rate assumption is disclosed.
    assert any(a.label == "Discount rate" for a in sec.assumptions)


def test_section_title_renders_without_step_number_in_markdown():
    stmts = [_stmt(2023), _stmt(2024)]
    s = from_financial_statements(stmts, "TST")
    sec = render_quant_section(s, {})
    assert sec is not None
    from research_analyst.enums import ReportType
    from research_analyst.models import ReportOutput

    out = ReportOutput(
        report_type=ReportType.COMPREHENSIVE,
        ticker="TST",
        title="TST report",
        generated_at="2026-09-28T00:00:00Z",
        sections=[sec],
    )
    md = out.to_markdown()
    assert "## Quantitative Engine" in md
    assert "## Step 8" not in md
    assert "## Step 0" not in md


# ---------------------------------------------------------------------------
# API response model
# ---------------------------------------------------------------------------


def test_quant_api_response_serializes_with_nulls_intact():
    stmts = [_stmt(2023), _stmt(2024)]
    s = from_financial_statements(stmts, "TST")
    results = compute_quant_results(s, {"currency": "USD"})
    resp = QuantAPIResponse(
        ticker="TST",
        periods=[p.period for p in s.periods],
        currency="USD",
        generated_at="2026-09-28T00:00:00Z",
        trends=results["trends"],
        dupont={
            "rows": results["dupont"]["rows"],
            "latest": results["dupont"]["latest"],
            "attribution": results["dupont"]["attribution"],
        },
        forensics=results["forensics"],
        valuation=results["valuation"],
        allocation=results["allocation"],
        expected_value={"reason": "no scenarios provided"},
        missing_inputs=results["missing_inputs"],
        assumptions=results["assumptions"],
    )
    dumped = resp.model_dump(mode="json")
    # Nulls stay null on the wire; keys carry no markdown emphasis.
    assert dumped["trends"]["fcf_cagr"] is None
    assert dumped["valuation"]["implied_explicit_stage_growth"] is None
    assert dumped["expected_value"]["reason"] == "no scenarios provided"
    assert dumped["expected_value"]["expected"] is None
    for key in dumped:
        assert "**" not in key and "*" not in key
    assert dumped["ticker"] == "TST"
    assert dumped["periods"] == ["FY2023", "FY2024"]


def test_quant_api_response_expected_value_payload():
    resp = QuantAPIResponse(
        ticker="TST",
        generated_at="2026-09-28T00:00:00Z",
        expected_value={"expected": 42.5, "contributions": [{"a": 42.5}], "reason": None},
    )
    dumped = resp.model_dump(mode="json")
    assert dumped["expected_value"]["expected"] == 42.5


# ---------------------------------------------------------------------------
# Renderer integration
# ---------------------------------------------------------------------------
def test_renderer_appends_quant_section_after_seven_steps():
    from research_analyst.enums import ReportType, SecurityType
    from research_analyst.models import CompanyProfile, PriceSeries
    from research_analyst.reports.renderer import ReportRenderer

    profile = CompanyProfile(
        ticker="TST",
        name="Test Inc",
        security_type=SecurityType.EQUITY,
        currency="USD",
    )
    prices = PriceSeries(
        ticker="TST",
        data=[],
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        current_price=50.0,
    )
    stmts = [_stmt(2021 + i) for i in range(4)]
    out = ReportRenderer().render(ReportType.COMPREHENSIVE, profile, prices, stmts)

    steps = [s.step_number for s in out.sections]
    assert steps[:7] == [1, 2, 3, 4, 5, 6, 7]  # template untouched
    assert out.sections[-1].step_number == 0
    assert out.sections[-1].title == QUANT_SECTION_TITLE

    md = out.to_markdown()
    assert "## Quantitative Engine" in md
    assert "## Step 8" not in md
    assert "## Step 0" not in md


# ---------------------------------------------------------------------------
# API endpoint (TestClient, stubbed providers)
# ---------------------------------------------------------------------------


def _quant_client(stmts, price: float | None = None):
    """Build a TestClient for /api/research/quant with stubbed providers."""
    try:
        from starlette.testclient import TestClient
    except Exception:
        return None
    from unittest.mock import AsyncMock, patch

    from research_analyst.enums import SecurityType
    from research_analyst.models import CompanyProfile, PriceSeries
    from research_analyst.server import create_app

    orch = AsyncMock()
    orch._fetch_yf_financials = AsyncMock(return_value=stmts)
    orch._fetch_sec_financials = AsyncMock(return_value=[])
    profile = CompanyProfile(
        ticker="TST",
        name="Test Inc",
        security_type=SecurityType.EQUITY,
        currency="USD",
        enterprise_value=5000.0,
    )
    mp = AsyncMock()
    mp.get_company_profile = AsyncMock(return_value=profile)
    if price is not None:
        prices = PriceSeries(
            ticker="TST",
            data=[],
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            current_price=price,
        )
        mp.get_price_series = AsyncMock(return_value=prices)
    else:
        mp.get_price_series = AsyncMock(side_effect=Exception("no prices"))
    with patch("research_analyst.server.MarketDataProvider", return_value=mp):
        return TestClient(create_app(orchestrator=orch))


def test_quant_endpoint_no_scenarios_returns_null_expected_value():
    client = _quant_client([_stmt(2021 + i) for i in range(4)])
    if client is None:
        return
    r = client.get("/api/research/quant?ticker=tst")
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "TST"
    assert d["periods"] == ["FY2021", "FY2022", "FY2023", "FY2024"]
    assert d["expected_value"]["expected"] is None
    assert d["expected_value"]["reason"] == "no scenarios provided"
    # Nulls preserved on the wire.
    assert d["trends"]["fcf_cagr"] is None
    assert "interest_expense (no data from providers)" in d["missing_inputs"]
    # No price injected (mock raises) → the price gap is surfaced, not hidden.
    assert "price (no data from providers)" in d["missing_inputs"]


def _wired_stmt(year: int) -> FinancialStatement:
    """A statement carrying every forensics/allocation input."""
    return _stmt(
        year,
        ebit=Decimal("250"),
        interest_expense=Decimal("-30"),
        tax_expense=Decimal("-40"),
        sga_expense=Decimal("-120"),
        depreciation_amortization=Decimal("-35"),
        retained_earnings=Decimal("500"),
        ppe_net=Decimal("300"),
        receivables=Decimal("90"),
        current_assets=Decimal("600"),
        current_liabilities=Decimal("400"),
        total_liabilities=Decimal("800"),
        total_debt=Decimal("200"),
    )


def test_quant_endpoint_wires_latest_price_into_series():
    client = _quant_client([_wired_stmt(2021 + i) for i in range(4)], price=150.0)
    if client is None:
        return
    r = client.get("/api/research/quant?ticker=tst")
    assert r.status_code == 200
    d = r.json()
    gaps = "\n".join(d["missing_inputs"])
    # Full wiring + latest price → Altman Z and Beneish M compute (screens run).
    assert "price" not in gaps
    assert "altman_z: " not in gaps
    assert "beneish_m: " not in gaps
    f = d["forensics"]
    assert f["altman_z"] is not None
    assert f["beneish_m"] is not None
    assert f["altman_missing"] == []


def test_quant_endpoint_price_gap_surfaces_altman_x4_missing():
    # No price → Altman X4 must be named, never fabricated.
    client = _quant_client([_wired_stmt(2021 + i) for i in range(4)])
    if client is None:
        return
    d = client.get("/api/research/quant?ticker=tst").json()
    assert "price (no data from providers)" in d["missing_inputs"]
    assert any("altman_z: price" in g for g in d["missing_inputs"])


def test_health_reports_commit_marker():
    client = _quant_client([_wired_stmt(2024)], price=150.0)
    if client is None:
        return
    d = client.get("/api/health")
    assert d.status_code == 200
    body = d.json()
    assert body["status"] == "ok"
    assert body["service"] == "research-analyst"
    assert isinstance(body["commit"], str) and body["commit"]


def test_quant_endpoint_scenarios_expected_value():
    import json
    import urllib.parse

    client = _quant_client([_stmt(2021 + i) for i in range(4)])
    if client is None:
        return
    sc = urllib.parse.quote(json.dumps([{"label": "base", "value": 100.0, "probability": 1.0}]))
    r = client.get(f"/api/research/quant?ticker=tst&scenarios={sc}")
    assert r.status_code == 200
    ev = r.json()["expected_value"]
    assert ev["expected"] == 100.0
    assert ev["contributions"] == [{"label": "base", "contribution": 100.0}]
    assert ev["reason"] is None


def test_quant_endpoint_discount_rate_enables_implied_growth():
    client = _quant_client(
        [
            _stmt(
                2021 + i,
                revenue=Decimal(str(1000 * (1.1**i))),
                net_income=Decimal(str(100 * (1.1**i))),
                free_cash_flow=Decimal(str(80 * (1.1**i))),
            )
            for i in range(5)
        ]
    )
    if client is None:
        return
    r = client.get("/api/research/quant?ticker=tst")
    assert r.json()["valuation"]["implied_explicit_stage_growth"] is None
    r = client.get("/api/research/quant?ticker=tst&discount_rate=0.09")
    assert r.status_code == 200
    v = r.json()["valuation"]
    assert v["discount_rate_used"] == 0.09
    # FCF series present now, so the inversion resolves.
    assert v["implied_explicit_stage_growth"] is not None


def test_quant_endpoint_404_without_statements():
    client = _quant_client([])
    if client is None:
        return
    r = client.get("/api/research/quant?ticker=zzz")
    assert r.status_code == 404
