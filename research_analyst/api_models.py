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
