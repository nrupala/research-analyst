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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""Ticker validation — international suffixes must survive the provider.

Regression (found live 2026-10-15): the API layer admits tickers up to
20 chars (api_models, raised for suffixed international symbols), but
the market-data provider's _sanitize_ticker still capped at 10 — so
RELIANCE.NS (11) and TATAMOTORS.NS (13) died with "Invalid ticker"
while INFY.NS (7) served. The cap is now 20 in both layers; the
charset guard (alphanumeric + dot/hyphen) is unchanged.
"""
# Module: tests/test_ticker_validation.py

from datetime import UTC, datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from research_analyst.enums import ReportType, ScenarioType, SecurityType
from research_analyst.models import (
    CapitalAllocation,
    DividendAnalysis,
    ReportOutput,
    ResearchMetadata,
    ResearchResponse,
    RiskMatrix,
    ValuationRange,
    ValuationScenario,
)
from research_analyst.providers.market_data import MarketDataProvider, _sanitize_ticker
from research_analyst.server import create_app


@pytest.mark.parametrize(
    "ticker",
    [
        "AAPL",          # US plain
        "SHOP.TO",       # Canada
        "INFY.NS",       # India, short symbol
        "RELIANCE.NS",   # India, 11 chars — the regression case
        "TATAMOTORS.NS", # India, 13 chars
        "RELIANCE.BO",   # India (BSE)
        "600519.SS",     # China
        "SAP.DE",        # Germany
        "MC.PA",         # France
        "7203.T",        # Japan
        "D05.SI",        # Singapore
        "9988.HK",       # Hong Kong
        "BRK-B",         # hyphenated class share
    ],
)
def test_valid_tickers_accepted(ticker):
    assert _sanitize_ticker(ticker) == ticker
    assert _sanitize_ticker(ticker.lower()) == ticker  # case-normalized


@pytest.mark.parametrize(
    "ticker",
    [
        "",
        "A" * 21,             # over the 20-char cap
        "RELIANCE.NS EXTRA",  # spaces are not ticker chars
        "AA$",                # punctuation outside dot/hyphen
        "AA/BB",              # path separator
    ],
)
def test_invalid_tickers_rejected(ticker):
    with pytest.raises(ValueError):
        _sanitize_ticker(ticker)


class _NullCache:
    def get(self, key):  # noqa: ARG002
        return None

    def set(self, key, value):  # noqa: ARG002
        return None


async def test_price_series_reaches_cascade_for_long_india_ticker(monkeypatch):
    """RELIANCE.NS must get past validation to the cascade (which may
    legitimately return empty in a stubbed test — the defect was the
    ValueError before any source was tried)."""
    provider = MarketDataProvider()
    monkeypatch.setattr(provider, "_cache", _NullCache())

    async def _empty_cascade(ticker, period="1y", interval="1d"):
        return pd.DataFrame(), ""

    monkeypatch.setattr(provider, "_cascade_download", _empty_cascade)
    series = await provider.get_price_series("RELIANCE.NS", period="3mo")
    assert series.ticker == "RELIANCE.NS"
    assert series.data == []


# ---------------------------------------------------------------------------
# End-to-end: the cap existed in THREE layers (API model / provider /
# ResearchRequest). The first fix aligned two and RELIANCE.NS still 500'd
# live on the third — these tests pin the whole path through the server.
# ---------------------------------------------------------------------------


def _make_response(ticker: str) -> ResearchResponse:
    scenario = ValuationScenario(
        scenario_type=ScenarioType.BASE,
        label="Base Case",
        assumptions=[],
        revenue_growth=0.08,
        operating_margin=0.25,
        implied_price_low=110.0,
        implied_price_high=110.0,
        implied_upside_low=0.10,
        implied_upside_high=0.10,
    )
    report = ReportOutput(
        report_type=ReportType.COMPREHENSIVE,
        ticker=ticker,
        title=f"{ticker} — Comprehensive 7-Step Research Report",
        generated_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        sections=[],
        valuation=ValuationRange(
            ticker=ticker,
            current_price=100.0,
            scenarios=[scenario],
            primary_methodology="Hybrid (PE + EV/EBITDA)",
        ),
        risk_matrix=RiskMatrix(ticker=ticker, overall_risk_score=4.0),
        capital_allocation=CapitalAllocation(
            ticker=ticker, period="TTM", roic=0.15,
            roic_minus_wacc=0.06, shareholder_yield=0.03,
        ),
        dividend=DividendAnalysis(
            ticker=ticker, pays_dividend=False,
            no_dividend_context="No dividend currently paid.",
        ),
    )
    return ResearchResponse(
        ticker=ticker,
        security_type=SecurityType.EQUITY,
        company_name=f"{ticker} Inc.",
        generated_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
        reports=[report],
        metadata=ResearchMetadata(data_sources=["Yahoo Finance (price data)"]),
    )


class _EchoOrchestrator:
    """Returns a canned response; records the ticker it was handed."""

    def __init__(self):
        self.seen: list[str] = []

    async def run(self, request):
        self.seen.append(request.ticker)
        return _make_response(request.ticker)


def test_research_endpoint_serves_long_india_ticker():
    orch = _EchoOrchestrator()
    client = TestClient(create_app(orchestrator=orch), raise_server_exceptions=False)
    resp = client.post("/api/research", json={"ticker": "RELIANCE.NS"})
    assert resp.status_code == 200
    assert orch.seen == ["RELIANCE.NS"]


def test_research_endpoint_rejects_overlong_ticker_cleanly():
    orch = _EchoOrchestrator()
    client = TestClient(create_app(orchestrator=orch), raise_server_exceptions=False)
    resp = client.post("/api/research", json={"ticker": "A" * 21})
    assert resp.status_code == 422  # API-layer validation, not a 500
    assert orch.seen == []
