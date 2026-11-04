# Copyright (C) 2026 2351485 ALBERTA INC.
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

"""API wire models — the public REST contract for Research Analyst.

These models are the single source of truth for the API surface and are used
by the typed-export layer (JSON Schema / TypeScript / XML) so integrators can
consume the engine as a machine-readable intelligence service.

Wire-format guarantee: the public JSON payload of every endpoint is byte-for-
byte the ``model_dump(mode="json")`` of these models. Typing the nested fields
with their domain models (instead of loose dicts) changes nothing on the wire
but gives consumers exact schemas and typed client SDKs.
"""
# Module: research_analyst/api_models.py | Version: 1.0 | Updated: 2026-08-31

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .comparative import ComparativeReport
from .models import ReportOutput, ResearchMetadata, SymbolMatch

SCHEMA_VERSION = "1.0"
"""Version of the typed-export schema. Bump (major.minor) on breaking
payload changes; consumers gate integration on this string."""


class ResearchAPIRequest(BaseModel):
    # max_length 20 to admit suffixed international tickers (e.g. RELIANCE.NS);
    # mirrors models.ResearchRequest.ticker (v0.3.0 international).
    ticker: str = Field(..., min_length=1, max_length=20)
    report_type: str | None = Field(default=None)
    compare_tickers: list[str] = Field(default_factory=list, max_length=5)
    timeframe: str = Field(default="1Y")
    custom_assumptions: dict[str, Any] = Field(default_factory=dict)


class ResearchAPIResponse(BaseModel):
    schema_version: str = SCHEMA_VERSION
    request_id: str
    ticker: str
    company_name: str
    security_type: str
    # Trading currency of the report's figures (from the company
    # profile). Consumers could not learn this from the payload
    # before — added for the F1.6 exports, which must label money
    # correctly (a ₹ price stamped USD would be a fabrication).
    currency: str = "USD"
    reports: list[ReportOutput]
    metadata: ResearchMetadata
    reports_markdown: list[str]


class CompareAPIRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=1, max_length=10)
    timeframe: str = Field(default="1Y")


class CompareAPIResponse(BaseModel):
    schema_version: str = SCHEMA_VERSION
    request_id: str
    tickers: list[str]
    report: ComparativeReport
    report_markdown: str
    report_html: str


class ResolveAPIRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=64)


class ResolveAPIResponse(BaseModel):
    schema_version: str = SCHEMA_VERSION
    query: str
    status: str
    resolved: SymbolMatch | None = None
    candidates: list[SymbolMatch] = Field(default_factory=list)
    note: str = ""


# Registry consumed by the typed-export layer: endpoint path -> response model.
API_RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    "research": ResearchAPIResponse,
    "compare": CompareAPIResponse,
    "resolve": ResolveAPIResponse,
}


# ---------------------------------------------------------------------------
# Quant engine API (GET /api/research/quant)
# ---------------------------------------------------------------------------


class QuantMarginSeries(BaseModel):
    """P1-B1: per-period margin fractions, aligned to ``periods[]``."""

    gross: list[float | None] = Field(default_factory=list)
    net: list[float | None] = Field(default_factory=list)


class QuantYoySeries(BaseModel):
    """P1-B1: per-period YoY growth fractions, aligned to ``periods[]``."""

    revenue: list[float | None] = Field(default_factory=list)


class QuantTrendsPayload(BaseModel):
    revenue_cagr: float | None = None
    eps_cagr: float | None = None
    fcf_cagr: float | None = None
    yoy_revenue_growth_latest: float | None = None
    gross_margin_latest: float | None = None
    net_margin_latest: float | None = None
    # Quant Lab Phase 1 (P1-B1): additive per-period series behind the
    # scalars above — same engine calls, nulls preserved element-for-element.
    margin_series: QuantMarginSeries = Field(default_factory=QuantMarginSeries)
    yoy_series: QuantYoySeries = Field(default_factory=QuantYoySeries)


class QuantDupontRow(BaseModel):
    period: str
    roe: float | None = None
    net_margin: float | None = None
    asset_turnover: float | None = None
    leverage: float | None = None


class QuantDupontAttribution(BaseModel):
    roe_change_pp: float | None = None
    margin_contribution_pp: float | None = None
    turnover_contribution_pp: float | None = None
    leverage_contribution_pp: float | None = None


class QuantDupontPayload(BaseModel):
    rows: list[QuantDupontRow] = Field(default_factory=list)
    latest: QuantDupontRow | None = None
    attribution: QuantDupontAttribution | None = None


class QuantForensicsPayload(BaseModel):
    altman_z: float | None = None
    altman_zone: str | None = None
    altman_missing: list[str] = Field(default_factory=list)
    beneish_m: float | None = None
    beneish_flag: bool | None = None
    beneish_missing: list[str] = Field(default_factory=list)
    sloan_accruals: float | None = None
    cash_conversion: float | None = None


class QuantSensitivityAxis(BaseModel):
    label: str
    values: list[float] = Field(default_factory=list)


class QuantSensitivityBase(BaseModel):
    discount_rate: float | None = None
    perpetual_growth: float | None = None
    explicit_growth: float | None = None


class QuantSensitivityPayload(BaseModel):
    """P1-B2: DCF sensitivity grid — rows = discount rate, cols = perpetual
    growth, cell = model value per share; unevaluable cells stay null."""

    rows: QuantSensitivityAxis
    cols: QuantSensitivityAxis
    values: list[list[float | None]] = Field(default_factory=list)
    base: QuantSensitivityBase = Field(default_factory=QuantSensitivityBase)


class QuantValuationPayload(BaseModel):
    graham_number: float | None = None
    lynch_fair_value: float | None = None
    implied_explicit_stage_growth: float | None = None
    implied_perpetual_growth: float | None = None
    discount_rate_used: float | None = None
    # Quant Lab Phase 1 (P1-B2): additive sensitivity grid; null when the
    # model inputs (discount rate, FCF, implied growth, net debt, shares)
    # are not all present — the gap is named in missing_inputs instead.
    sensitivity: QuantSensitivityPayload | None = None


class QuantAllocationPayload(BaseModel):
    incremental_roic_average: float | None = None
    operating_tax_rate_latest: float | None = None
    dividend_payout_on_earnings: float | None = None
    dividend_payout_on_fcf: float | None = None
    dividend_years_grown: int = 0
    dividend_cuts: int = 0
    debt_net_debt_latest: float | None = None
    debt_net_debt_to_ebit: float | None = None
    debt_interest_coverage: float | None = None
    debt_cagr: float | None = None
    buyback_shares_cagr: float | None = None
    buyback_total_spent: float | None = None


class QuantScenarioInput(BaseModel):
    label: str
    value: float | None = None
    probability: float | None = None


class QuantExpectedValuePayload(BaseModel):
    expected: float | None = None
    contributions: list[dict[str, float | str]] | None = None
    reason: str | None = None


class QuantAPIResponse(BaseModel):
    schema_version: str = SCHEMA_VERSION
    ticker: str
    # F1.8: the Data Sources label of the statement set these results
    # were computed over — the same merged, first-source-led set the
    # research report uses (see orchestrator.fetch_merged_financials).
    statements_source: str | None = None
    periods: list[str] = Field(default_factory=list)
    currency: str | None = None
    generated_at: datetime
    trends: QuantTrendsPayload = Field(default_factory=QuantTrendsPayload)
    dupont: QuantDupontPayload = Field(default_factory=QuantDupontPayload)
    forensics: QuantForensicsPayload = Field(default_factory=QuantForensicsPayload)
    valuation: QuantValuationPayload = Field(default_factory=QuantValuationPayload)
    allocation: QuantAllocationPayload = Field(default_factory=QuantAllocationPayload)
    expected_value: QuantExpectedValuePayload = Field(default_factory=QuantExpectedValuePayload)
    missing_inputs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


API_RESPONSE_MODELS["quant"] = QuantAPIResponse
