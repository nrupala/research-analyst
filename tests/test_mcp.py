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

"""MCP surface — POST /mcp (streamable HTTP, JSON-RPC 2.0).

Semantics under test:
- The endpoint exists for POST (GET stays 405: no server stream).
- Auth rides the REST components: the same KeyStore.verify, reached
  via X-RA-Key (REST's header) or Authorization: Bearer (the MCP
  client convention). With a key store configured a valid key is
  required; app-only keys get 403; the keyed lane's rate cap and
  monthly allowance apply to tools/call with REST's wording.
- The protocol subset Sail's raclient speaks: initialize ->
  notifications/initialized -> tools/call {name, arguments:{ticker}},
  plus ping and tools/list. Stateless: no session id is issued.
- The research tool returns the REST /api/research payload verbatim
  (structuredContent + a JSON text block + the markdown), and the
  quant tool returns the /api/research/quant payload verbatim —
  both are the shared _serve_* pipelines, not MCP-only computation.
- Successful tools/call invocations meter under the "mcp" label in
  the same MeteringRecorder (visible via /api/usage); failures —
  auth, limits, tool errors — are never metered.
- Tool descriptions carry the constitution: research and education
  only, no advice, no recommendation language.
"""
# Module: tests/test_mcp.py

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from research_analyst import server as server_mod
from research_analyst.entitlements import API_ACCESS, RA_PRO, KeyStore, MeteringRecorder
from research_analyst.enums import ReportType, SecurityType
from research_analyst.models import (
    CompanyProfile,
    FinancialStatement,
    ReportOutput,
    ResearchMetadata,
    ResearchResponse,
)
from research_analyst.server import _IPRateLimiter, create_app


class _StubOrchestrator:
    """A research pipeline that answers with a minimal real report."""

    async def run(self, request):  # noqa: ANN001, ANN202
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


class _BoomOrchestrator:
    async def run(self, request):  # noqa: ARG002
        raise RuntimeError("STOP — pipeline must not run in gate tests")


def _client(store=None, metering=None, orchestrator=None):  # noqa: ANN001, ANN202
    app = create_app(
        orchestrator=orchestrator or _StubOrchestrator(),
        rate_limiter=_IPRateLimiter(rate=1000, burst=1000),
        key_store=store,
        metering=metering,
    )
    return TestClient(app, raise_server_exceptions=False)


def _issue(store, entitlements=None, **kwargs):  # noqa: ANN001, ANN202
    return store.create("mcp-test", entitlements or {API_ACCESS}, **kwargs)


def _rpc(client, payload, raw=None, via="bearer", path="/mcp"):  # noqa: ANN001, ANN202
    headers = {}
    if raw:
        if via == "bearer":
            headers["Authorization"] = f"Bearer {raw}"
        else:
            headers["x-ra-key"] = raw
    return client.post(path, json=payload, headers=headers)


def _initialize(client, raw=None, version="2025-03-26", via="bearer", path="/mcp"):  # noqa: ANN001, ANN202
    return _rpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "sail", "version": "0.14.0"},
            },
        },
        raw=raw,
        via=via,
        path=path,
    )


def _call(client, name, arguments, raw=None, req_id=2, path="/mcp"):  # noqa: ANN001, ANN202
    return _rpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        raw=raw,
        path=path,
    )


# ---------------------------------------------------------------------------
# Transport shape
# ---------------------------------------------------------------------------


def test_mcp_post_answers_and_get_is_405():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    assert _initialize(client, raw).status_code == 200
    assert client.get("/mcp").status_code == 405


def test_mcp_notification_is_tolerated_with_202():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    r = _rpc(client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, raw=raw)
    assert r.status_code == 202
    assert r.content == b""


def test_mcp_ping():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    r = _rpc(client, {"jsonrpc": "2.0", "id": 7, "method": "ping"}, raw=raw)
    assert r.status_code == 200
    assert r.json() == {"jsonrpc": "2.0", "id": 7, "result": {}}


def test_mcp_parse_error_is_jsonrpc_32700():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    r = client.post(
        "/mcp",
        content="not json",
        headers={"Authorization": f"Bearer {raw}", "Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == -32700


def test_mcp_invalid_request_shape_is_32600():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    r = _rpc(client, [1, 2, 3], raw=raw)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == -32600
    r = _rpc(client, {"jsonrpc": "1.0", "id": 1, "method": "ping"}, raw=raw)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == -32600


def test_mcp_unknown_method_is_32601():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    r = _rpc(client, {"jsonrpc": "2.0", "id": 9, "method": "resources/list"}, raw=raw)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 9
    assert body["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# Auth — the REST key store, both headers, keyed-lane semantics
# ---------------------------------------------------------------------------


def test_mcp_missing_key_rejected_when_store_configured():
    client = _client(store=KeyStore())
    r = _initialize(client)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == -32001


def test_mcp_invalid_key_rejected_and_never_metered():
    store = KeyStore()
    _issue(store)
    metering = MeteringRecorder()
    client = _client(store=store, metering=metering)
    r = _call(client, "research", {"ticker": "AAA"}, raw="ra_live_not_a_real_key")
    assert r.status_code == 401
    assert metering.total_requests("anonymous") == 0
    assert metering._counts == {}


def test_mcp_revoked_key_rejected():
    store = KeyStore()
    record, raw = _issue(store)
    store.revoke(record.key_id)
    client = _client(store=store)
    assert _initialize(client, raw).status_code == 401


def test_mcp_app_only_key_gets_403():
    store = KeyStore()
    _, raw = _issue(store, {RA_PRO})
    client = _client(store=store)
    r = _initialize(client, raw)
    assert r.status_code == 403
    assert "API access" in r.json()["error"]["message"]


def test_mcp_bearer_and_x_ra_key_both_verify():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    for via in ("bearer", "x-ra-key"):
        r = _initialize(client, raw, via=via)
        assert r.status_code == 200
        result = r.json()["result"]
        assert result["serverInfo"]["name"] == "research-analyst"
        assert result["protocolVersion"] == "2025-03-26"
        # Stateless: the server issues no session id for the client to echo.
        assert "mcp-session-id" not in r.headers


def test_mcp_initialize_negotiates_a_supported_version():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    r = _initialize(client, raw, version="2025-06-18")
    assert r.json()["result"]["protocolVersion"] == "2025-06-18"
    r = _initialize(client, raw, version="1999-01-01")
    assert r.json()["result"]["protocolVersion"] == "2025-03-26"


def test_mcp_legacy_paid_key_accepted(monkeypatch):
    monkeypatch.setattr(server_mod.settings.billing, "paid_keys", ["legacy-1"])
    client = _client(store=None)
    assert _initialize(client, "legacy-1").status_code == 200
    assert _initialize(client).status_code == 401
    assert _initialize(client, "legacy-2").status_code == 401


def test_mcp_open_when_nothing_configured_matches_rest_dev_posture():
    client = _client(store=None)
    assert _initialize(client).status_code == 200


def test_mcp_allowance_exhausted_gets_429():
    store = KeyStore()
    record, raw = _issue(store, plan="api_pro", monthly_call_allowance=1)
    metering = MeteringRecorder()
    metering.record(record.key_id, "research")  # 1 served call this month
    client = _client(store=store, metering=metering)
    r = _call(client, "research", {"ticker": "AAA"}, raw=raw)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == -32002
    assert "allowance" in r.json()["error"]["message"]


def test_mcp_rate_cap_gets_429(monkeypatch):
    monkeypatch.setitem(server_mod._PLAN_RATE_CAPS_PER_MIN, "api_pro", 1)
    store = KeyStore()
    _, raw = _issue(store, plan="api_pro")
    client = _client(store=store)
    assert _call(client, "research", {"ticker": "AAA"}, raw=raw).status_code == 200
    r = _call(client, "research", {"ticker": "AAA"}, raw=raw)
    assert r.status_code == 429
    assert "Rate limit" in r.json()["error"]["message"]


# ---------------------------------------------------------------------------
# tools/list — the published contract, constitution included
# ---------------------------------------------------------------------------


def test_mcp_tools_list_publishes_research_and_quant():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    r = _rpc(client, {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, raw=raw)
    tools = r.json()["result"]["tools"]
    assert [t["name"] for t in tools] == ["research", "quant"]
    for tool in tools:
        assert tool["inputSchema"]["required"] == ["ticker"]
        description = tool["description"]
        assert "Research and education only" in description
        assert "not investment advice" in description
        # The constitution binds tool descriptions too: no advice verbs.
        assert not re.search(r"\b(buy|sell|hold)\b", description, re.IGNORECASE)


def test_mcp_unknown_tool_is_32601():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    r = _call(client, "valuation", {"ticker": "AAA"}, raw=raw)
    assert r.status_code == 200
    assert r.json()["error"]["code"] == -32601


def test_mcp_bad_params_are_32602():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    cases = [
        ("research", {}),  # ticker missing
        ("research", {"ticker": ""}),  # empty
        ("research", {"ticker": "X" * 21}),  # too long (REST caps at 20)
        ("research", {"ticker": 42}),  # not a string
        ("quant", {"ticker": "AAA", "discount_rate": "high"}),
        ("quant", {"ticker": "AAA", "scenarios": {"label": "x"}}),
    ]
    for name, arguments in cases:
        r = _call(client, name, arguments, raw=raw)
        assert r.json()["error"]["code"] == -32602, (name, arguments, r.json())
    r = _rpc(
        client,
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "research"}},
        raw=raw,
    )
    assert r.json()["error"]["code"] == -32602  # arguments absent entirely
    r = _rpc(
        client,
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"arguments": {"ticker": "AAA"}},
        },
        raw=raw,
    )
    assert r.json()["error"]["code"] == -32602  # tool name absent


# ---------------------------------------------------------------------------
# tools/call — research (the Sail sequence) and quant
# ---------------------------------------------------------------------------


def test_mcp_sail_sequence_research_success_and_metering():
    store = KeyStore()
    record, raw = _issue(store, plan="api_pro", monthly_call_allowance=100_000)
    metering = MeteringRecorder()
    client = _client(store=store, metering=metering)

    # The exact sequence Sail's raclient performs.
    init = _initialize(client, raw)
    assert init.status_code == 200
    note = _rpc(client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, raw=raw)
    assert note.status_code == 202
    r = _call(client, "research", {"ticker": "AAPL"}, raw=raw)
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is False

    # structuredContent is the REST payload verbatim.
    payload = result["structuredContent"]
    assert payload["ticker"] == "AAPL"
    assert payload["schema_version"] == "1.0"
    assert payload["company_name"] == "Stub Corp"
    # Sail's summary fallback: reports[0].title in the REST shape.
    assert payload["reports"][0]["title"] == "AAPL — Comprehensive"
    # A JSON text block carries the same payload for text-only clients.
    texts = [c["text"] for c in result["content"] if c["type"] == "text"]
    parsed = [json.loads(t) for t in texts if t.lstrip().startswith("{")]
    assert parsed and parsed[0]["ticker"] == "AAPL"

    # Metered once, under the distinct "mcp" label, visible via /api/usage.
    assert metering.usage(record.key_id) == {"mcp": 1}
    usage = client.get("/api/usage", headers={"x-ra-key": raw})
    assert usage.status_code == 200
    assert usage.json()["monthly_usage"] == {"mcp": 1}


def test_mcp_research_pipeline_failure_is_error_result_and_not_metered():
    store = KeyStore()
    record, raw = _issue(store)
    metering = MeteringRecorder()
    client = _client(store=store, metering=metering, orchestrator=_BoomOrchestrator())
    r = _call(client, "research", {"ticker": "AAA"}, raw=raw)
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "Research pipeline failed" in text
    assert "Traceback" not in text  # no stack traces, ever
    assert metering.usage(record.key_id) == {}


def _stmt(year: int) -> FinancialStatement:
    return FinancialStatement(
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


def _quant_client(store, metering, stmts):  # noqa: ANN001, ANN202
    from research_analyst.orchestrator import FinancialsBundle

    orch = AsyncMock()
    orch.fetch_merged_financials = AsyncMock(
        return_value=FinancialsBundle(
            financials=stmts, lead="yfinance", yf=stmts, sec=[], cvm=[], edinet=[]
        )
    )
    profile = CompanyProfile(
        ticker="TST",
        name="Test Inc",
        security_type=SecurityType.EQUITY,
        currency="USD",
        enterprise_value=5000.0,
    )
    mp = AsyncMock()
    mp.get_company_profile = AsyncMock(return_value=profile)
    mp.get_price_series = AsyncMock(side_effect=Exception("no prices"))
    with patch("research_analyst.server.MarketDataProvider", return_value=mp):
        app = create_app(
            orchestrator=orch,
            rate_limiter=_IPRateLimiter(rate=1000, burst=1000),
            key_store=store,
            metering=metering,
        )
    return TestClient(app, raise_server_exceptions=False)


def test_mcp_quant_tool_returns_rest_payload_and_meters():
    store = KeyStore()
    record, raw = _issue(store)
    metering = MeteringRecorder()
    client = _quant_client(store, metering, [_stmt(2021 + i) for i in range(4)])
    r = _call(client, "quant", {"ticker": "TST"}, raw=raw)
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is False
    payload = result["structuredContent"]
    assert payload["ticker"] == "TST"
    assert payload["periods"] == ["FY2021", "FY2022", "FY2023", "FY2024"]
    # Same honesty as REST: absent scenarios -> null expected value + reason.
    assert payload["expected_value"]["expected"] is None
    assert payload["expected_value"]["reason"] == "no scenarios provided"
    assert metering.usage(record.key_id) == {"mcp": 1}


def test_mcp_quant_tool_with_scenarios_computes_expected_value():
    store = KeyStore()
    _, raw = _issue(store)
    client = _quant_client(store, MeteringRecorder(), [_stmt(2021 + i) for i in range(4)])
    r = _call(
        client,
        "quant",
        {
            "ticker": "TST",
            "scenarios": [
                {"label": "up", "value": 120.0, "probability": 0.5},
                {"label": "down", "value": 80.0, "probability": 0.5},
            ],
        },
        raw=raw,
    )
    payload = r.json()["result"]["structuredContent"]
    assert payload["expected_value"]["expected"] == 100.0


def test_mcp_quant_no_statements_is_error_result():
    store = KeyStore()
    _, raw = _issue(store)
    client = _quant_client(store, MeteringRecorder(), [])
    r = _call(client, "quant", {"ticker": "ZZZ"}, raw=raw)
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is True
    assert "No financial statements available for 'ZZZ'" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# /api/mcp alias — the same handler behind the /api/* Worker routes
# (the public hosts proxy only /api/* to the origin, so /mcp alone
# is unreachable there; the alias is the published endpoint)
# ---------------------------------------------------------------------------


def test_mcp_api_alias_initialize_and_tools_list():
    store = KeyStore()
    _, raw = _issue(store)
    client = _client(store=store)
    r = _initialize(client, raw, path="/api/mcp")
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["serverInfo"]["name"] == "research-analyst"
    assert result["protocolVersion"] == "2025-03-26"
    r = _rpc(
        client,
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        raw=raw,
        path="/api/mcp",
    )
    tools = r.json()["result"]["tools"]
    assert [t["name"] for t in tools] == ["research", "quant"]


def test_mcp_api_alias_tools_call_research():
    store = KeyStore()
    record, raw = _issue(store)
    metering = MeteringRecorder()
    client = _client(store=store, metering=metering)
    r = _call(client, "research", {"ticker": "AAPL"}, raw=raw, path="/api/mcp")
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["ticker"] == "AAPL"
    # The alias is the same handler: metering lands under "mcp" too.
    assert metering.usage(record.key_id) == {"mcp": 1}


def test_mcp_api_alias_missing_key_is_32001():
    client = _client(store=KeyStore())
    r = _initialize(client, path="/api/mcp")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == -32001
