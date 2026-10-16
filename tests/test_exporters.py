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

"""Tests for the typed-export layer (Phase 1): JSON Schema, TypeScript .d.ts,
XML serialization, content negotiation, and the format-aware API endpoints.

Offline, deterministic — the ResearchOrchestrator and ComparativeOrchestrator
are replaced with fakes; no network, no yfinance.
"""
# Module: tests/test_exporters.py | Version: 1.0 | Updated: 2026-08-31

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime

import pytest

from research_analyst.api_models import SCHEMA_VERSION
from research_analyst.enums import ReportType, SecurityType
from research_analyst.exporters import (
    json_schema_for,
    json_schemas_all,
    ts_definitions,
    xml_from_dict,
)
from research_analyst.models import (
    ReportOutput,
    ResearchMetadata,
    ResearchRequest,
    ResearchResponse,
)
from research_analyst.server import negotiate_format

# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------


def test_json_schemas_all_covers_every_endpoint():
    schemas = json_schemas_all()
    assert set(schemas) == {"research", "compare", "resolve", "quant"}
    for name, schema in schemas.items():
        assert schema["$id"] == f"https://ra.devinfo.dev/schemas/{name}.schema.json"
        assert f"schema_version: {SCHEMA_VERSION}" in schema["$comment"]
        assert "properties" in schema


def test_json_schema_typed_fields_resolved():
    from research_analyst.api_models import ResearchAPIResponse

    schema = json_schema_for(ResearchAPIResponse, "research")
    props = schema["properties"]
    assert "schema_version" in props
    assert "reports" in props
    assert props["reports"]["items"]["$ref"].endswith("ReportOutput")  # typed, not loose dict
    assert "metadata" in props


def test_json_schemas_match_wire_payload():
    schemas = json_schemas_all()
    # schema_version is part of every endpoint payload schema
    assert "schema_version" in schemas["research"]["properties"]


def test_json_schema_quant_endpoint_typed():
    schemas = json_schemas_all()
    props = schemas["quant"]["properties"]
    assert "ticker" in props
    for field in ("trends", "valuation", "forensics", "allocation", "dupont"):
        assert field in props, f"quant schema missing {field}"
    assert "schema_version" in props


# ---------------------------------------------------------------------------
# TypeScript definitions
# ---------------------------------------------------------------------------


def test_ts_definitions_core_shapes():
    ts = ts_definitions()
    assert "Auto-generated" in ts
    assert f'export const RA_SCHEMA_VERSION = "{SCHEMA_VERSION}";' in ts
    for interface in (
        "ResearchAPIResponse",
        "CompareAPIResponse",
        "ResolveAPIResponse",
        "SymbolMatch",
    ):
        assert f"export interface {interface} {{" in ts, interface


def test_ts_definitions_nested_models_and_enums():
    ts = ts_definitions()
    assert "export interface ReportOutput {" in ts  # reachable through research payload
    assert "export interface ResearchMetadata {" in ts
    # Enum literals for typed fields (ReportType is reachable via ReportOutput)
    assert '"comprehensive"' in ts


def test_ts_definitions_no_unresolved_unknown():
    """Forward refs must resolve — no field may degrade to 'unknown'."""
    ts = ts_definitions()
    for line in ts.splitlines():
        stripped = line.strip()
        if stripped.endswith(";"):
            assert ": unknown;" not in stripped, f"unresolved field: {stripped}"


def test_ts_definitions_deterministic():
    assert ts_definitions() == ts_definitions()


def test_ts_definitions_emit_file(tmp_path):
    from research_analyst.cli import _cmd_schema_export

    class _Args:
        out = str(tmp_path)

    _cmd_schema_export(_Args())  # type: ignore[arg-type]
    files = sorted(p.name for p in tmp_path.iterdir())
    expected = [
        "compare.schema.json",
        "quant.schema.json",
        "research.schema.json",
        "resolve.schema.json",
        "types.d.ts",
    ]
    assert files == expected
    assert (tmp_path / "types.d.ts").read_text().startswith("// Auto-generated")


# ---------------------------------------------------------------------------
# XML serialization
# ---------------------------------------------------------------------------


def _sample_payload() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "request_id": "r1",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "security_type": "EQUITY",
        "reports_markdown": ["# Report", ""],
        "nested": {"a": 1, "b": "x", "flag": True, "nothing": None, "items": [1, 2, 3]},
    }


def _xml_roundtrip(text: str) -> dict:
    root = ET.fromstring(text)
    out: dict = {}
    for el in root:
        out[el.tag] = _xml_value(el)
    return out


def _xml_value(el: ET.Element):
    if set(el.attrib) == {"null"} and el.attrib["null"] == "true":
        return None
    children = list(el)
    if children:
        tags = {c.tag for c in children}
        if len(tags) == 1:  # repeated element -> JSON list
            return [_xml_value(c) for c in children]
        return {c.tag: _xml_value(c) for c in children}
    text = el.text
    if text is None:
        return ""
    if text in ("true", "false"):
        return text == "true"
    if text.lstrip("-").isdigit():
        return int(text)
    return text


def test_xml_roundtrip_scalars_and_nesting():
    text = xml_from_dict(_sample_payload(), "research")
    assert text.startswith("<?xml")
    decoded = _xml_roundtrip(text)
    assert decoded["ticker"] == "AAPL"
    assert decoded["company_name"] == "Apple Inc."
    assert decoded["nested"]["a"] == 1
    assert decoded["nested"]["flag"] is True
    assert decoded["nested"]["nothing"] is None
    assert decoded["nested"]["items"] == [1, 2, 3]


def test_xml_tag_sanitization():
    text = xml_from_dict({"my field": "v", "a-b.c": 2}, "root")
    assert "my_field" in text
    assert "a-b.c" in text


# ---------------------------------------------------------------------------
# Content negotiation
# ---------------------------------------------------------------------------


def test_negotiate_format_query_priority():
    assert negotiate_format("xml", "application/json") == "xml"
    assert negotiate_format("TS", "text/html") == "ts"


def test_negotiate_format_accept_header():
    assert negotiate_format(None, "application/xml") == "xml"
    assert negotiate_format(None, "text/markdown; charset=utf-8") == "markdown"
    assert negotiate_format(None, "text/html") == "html"
    assert negotiate_format(None, "text/typescript") == "ts"
    assert negotiate_format(None, "application/json") == "json"


def test_negotiate_format_unknown_raises():
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        negotiate_format("yaml", "")


# ---------------------------------------------------------------------------
# API endpoints (stubbed pipelines)
# ---------------------------------------------------------------------------

try:
    from fastapi.testclient import TestClient

    from research_analyst.comparative import build_comparative_report
    from research_analyst.server import _IPRateLimiter, create_app

    _FASTAPI_AVAILABLE = True
except Exception:  # pragma: no cover - same pattern as test_comparative.py
    TestClient = None  # type: ignore[assignment,misc]
    create_app = None  # type: ignore[assignment]
    _IPRateLimiter = None  # type: ignore[assignment]
    build_comparative_report = None  # type: ignore[assignment]
    _FASTAPI_AVAILABLE = False

requires_fastapi = pytest.mark.skipif(
    not _FASTAPI_AVAILABLE,
    reason="fastapi/httpx not installed; endpoint tests run in CI",
)


def _stub_orchestrator() -> object:
    class StubOrchestrator:
        async def run(self, request: ResearchRequest) -> ResearchResponse:
            report = ReportOutput(
                report_type=ReportType.COMPREHENSIVE,
                ticker=request.ticker,
                title=f"{request.ticker} — Comprehensive",
                generated_at=datetime(2026, 1, 1, 12, 0, 0),
                sections=[],
            )
            return ResearchResponse(
                ticker=request.ticker,
                security_type=SecurityType.EQUITY,
                company_name="Stub Corp",
                currency="USD",
                generated_at=datetime(2026, 1, 1, 12, 0, 0),
                reports=[report],
                metadata=ResearchMetadata(data_sources=["stub"]),
            )

    return StubOrchestrator()


def _client() -> TestClient:  # type: ignore[name-defined]
    app = create_app(
        orchestrator=_stub_orchestrator(),
        rate_limiter=_IPRateLimiter(rate=1000, burst=1000),
    )
    return TestClient(app)


@requires_fastapi
def test_research_endpoint_format_json_has_schema_version():
    resp = _client().post("/api/research", json={"ticker": "AAPL"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["reports"][0]["report_type"] == "comprehensive"


@requires_fastapi
def test_research_endpoint_format_xml():
    resp = _client().post("/api/research?format=xml", json={"ticker": "AAPL"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(resp.text)
    assert root.tag == "research"
    assert root.findtext("ticker") == "AAPL"


@requires_fastapi
def test_research_endpoint_format_markdown():
    resp = _client().post("/api/research?format=markdown", json={"ticker": "AAPL"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "# AAPL — Comprehensive" in resp.text


@requires_fastapi
def test_research_endpoint_rejects_html():
    resp = _client().post("/api/research?format=html", json={"ticker": "AAPL"})
    assert resp.status_code == 400


@requires_fastapi
def test_research_endpoint_accept_header_negotiation():
    resp = _client().post(
        "/api/research", json={"ticker": "AAPL"}, headers={"Accept": "application/xml"}
    )
    assert resp.headers["content-type"].startswith("application/xml")


@requires_fastapi
def test_research_endpoint_typescript_format():
    resp = _client().post("/api/research?format=ts", json={"ticker": "AAPL"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/typescript")
    assert "export interface ResearchAPIResponse" in resp.text


@requires_fastapi
def test_compare_endpoint_formats():
    client = _client()
    resp = client.post("/api/compare?format=html", json={"tickers": ["AAPL", "MSFT"]})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    resp_md = client.post("/api/compare?format=markdown", json={"tickers": ["AAPL", "MSFT"]})
    assert resp_md.status_code == 200
    assert resp_md.headers["content-type"].startswith("text/markdown")


@requires_fastapi
def test_unknown_format_rejected():
    resp = _client().post("/api/research?format=yaml", json={"ticker": "AAPL"})
    assert resp.status_code == 400


@requires_fastapi
def test_wire_payload_unchanged_by_typing():
    """Typed response models serialize to the same JSON as the old loose dicts."""
    from research_analyst.api_models import ResearchAPIResponse

    payload = {
        "schema_version": SCHEMA_VERSION,
        "request_id": "r1",
        "ticker": "AAPL",
        "company_name": "Stub Corp",
        "security_type": "EQUITY",
        # F1.6: report currency joined the wire contract (exports must
        # label money correctly; consumers could not learn it before).
        "currency": "USD",
        "reports": [
            {
                "report_type": "comprehensive",
                "ticker": "AAPL",
                "title": "AAPL — Comprehensive",
                "generated_at": "2026-01-01T12:00:00Z",
                "sections": [],
                "valuation": None,
                "risk_matrix": None,
                "capital_allocation": None,
                "dividend": None,
                "security_type": None,
                "disclaimer": "",
                "lenses": [],
            }
        ],
        "metadata": {
            "data_sources": ["stub"],
            "data_freshness": {},
            "assumptions_used": [],
            "warnings": [],
            "processing_time_seconds": 0.0,
            # Issue #66 freshness fields now part of the typed wire contract.
            "data_as_of": None,
            "sla_state": "fresh",
            "cache_hit": False,
            "cached_at_utc": None,
            "stale_warning": None,
            # Issues #69/#74 evidence-traceability fields, also in the wire contract.
            "quotes_disclosure": (
                "Quotes are delayed to the previous trading day's close (end-of-day data)."
            ),
            "source_records": [],
            "peer_set": None,
            "input_snapshot": None,
        },
        "reports_markdown": [],
    }
    model = ResearchAPIResponse.model_validate(payload)
    assert json.loads(model.model_dump_json()) == payload
