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

"""Tests for the AIOA/OGSA agency adapter (research_analyst/agency.py).

All offline: the orchestrator, comparative runner and symbol search are
injected fakes — no network, no paid services.
"""
# Module: tests/test_agency.py | Version: 1.0 | Updated: 2026-09-25

from __future__ import annotations

import asyncio
import json

import pytest

from research_analyst import agency
from research_analyst.agency import (
    AGENCY_ID,
    OGSA_CAPABILITIES,
    OGSA_CATEGORY,
    AgencyError,
    handle_ogsa_task,
    report_hash,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeMetadata:
    data_sources = ["yfinance (company profile)"]
    source_records = [
        {"name": "yfinance (company profile)", "url": "https://finance.yahoo.com/quote/AAA"}
    ]
    data_as_of = "2026-09-24"
    warnings = ["fake warning"]


class _FakeResponse:
    def model_dump(self, mode="json"):  # noqa: ARG002
        return {
            "ticker": "AAA",
            "reports": [{"title": "AAA report"}],
            "metadata": {
                "data_sources": list(_FakeMetadata.data_sources),
                "source_records": [dict(r) for r in _FakeMetadata.source_records],
                "data_as_of": _FakeMetadata.data_as_of,
                "warnings": list(_FakeMetadata.warnings),
            },
        }


class _FakeOrchestrator:
    def __init__(self, fail_with=None):
        self.fail_with = fail_with
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        if self.fail_with:
            raise self.fail_with
        return _FakeResponse()


class _FakeComparison:
    tickers = ["AAA", "BBB"]
    source_records = {}

    def model_dump(self, mode="json"):  # noqa: ARG002
        return {"tickers": list(self.tickers), "source_records": {}}


class _FakeComparative:
    def __init__(self, fail_with=None):
        self.fail_with = fail_with

    async def run(self, tickers, timeframe="1Y"):  # noqa: ARG002
        if self.fail_with:
            raise self.fail_with
        return _FakeComparison()


def _task(**kw):
    base = {
        "id": "task-1",
        "sourceAgent": "ogsa",
        "targetAgent": "research-intel",
        "action": "research:analyze",
        "payload": {"ticker": "AAA"},
        "tokenId": "tok",
        "priority": 1,
        "createdAt": 1_000,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def test_manifest_contract():
    m = agency.agency_manifest()
    assert m["agency_id"] == AGENCY_ID
    assert m["ogsa_category"] == OGSA_CATEGORY == "research-intel"
    assert set(m["ogsa_capabilities"]) == set(OGSA_CAPABILITIES)
    assert "research:analyze" in m["actions"]
    assert "research:compare" in m["actions"]
    assert "research:resolve" in m["actions"]
    for key in ("request_id", "engine_version", "data_timestamp", "report_hash", "outcome"):
        assert key in m["audit_contract"]
    json.dumps(m)  # JSON-serializable


def test_report_hash_deterministic():
    h1 = report_hash({"b": 2, "a": 1})
    h2 = report_hash({"a": 1, "b": 2})
    assert h1 == h2
    assert len(h1) == 64
    assert report_hash({"a": 2}) != h1


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_success_envelope():
    orch = _FakeOrchestrator()
    result = await handle_ogsa_task(_task(), orchestrator=orch)
    assert result["taskId"] == "task-1"
    assert result["status"] == "success"
    assert "error" not in result
    out = result["output"]
    assert out["schema_version"] == "1.0"
    assert out["agency"] == AGENCY_ID
    assert out["capability"] == "research:analyze"
    assert out["report"]["ticker"] == "AAA"
    assert out["warnings"] == ["fake warning"]
    assert out["provenance"]["data_as_of"] == "2026-09-24"
    assert out["provenance"]["engine_version"] == agency.ENGINE_VERSION
    audit = out["audit"]
    assert audit["outcome"] == "success"
    assert audit["engine_version"] == agency.ENGINE_VERSION
    assert len(audit["report_hash"]) == 64
    assert audit["request_id"].startswith("ogsa-")
    assert isinstance(result["completedAt"], int)
    # The request was translated onto the versioned contract.
    assert orch.requests[0].ticker == "AAA"


@pytest.mark.asyncio
async def test_analyze_with_report_type_timeframe_assumptions():
    orch = _FakeOrchestrator()
    await handle_ogsa_task(
        _task(
            payload={
                "ticker": "bbb",
                "report_type": "tactical",
                "timeframe": "3M",
                "assumptions": {"wacc": 0.09},
            }
        ),
        orchestrator=orch,
    )
    req = orch.requests[0]
    assert req.ticker == "BBB"  # normalized
    assert req.report_types[0].value == "tactical"
    assert req.timeframe.value == "3M"
    assert req.custom_assumptions == {"wacc": 0.09}


@pytest.mark.asyncio
async def test_legacy_text_payload_mapped_with_warning():
    orch = _FakeOrchestrator()
    result = await handle_ogsa_task(_task(payload={"text": "AAPL", "urls": []}), orchestrator=orch)
    assert result["status"] == "success"
    assert orch.requests[0].ticker == "AAPL"
    assert any("legacy" in w.lower() for w in result["output"]["warnings"])


@pytest.mark.asyncio
async def test_compare_success():
    result = await handle_ogsa_task(
        _task(action="research:compare", payload={"tickers": ["AAA", "BBB"]}),
        comparative=_FakeComparative(),
    )
    assert result["status"] == "success"
    assert result["output"]["capability"] == "research:compare"
    assert result["output"]["audit"]["outcome"] == "success"


@pytest.mark.asyncio
async def test_resolve_success():
    import research_analyst.resolver as resolver_mod
    from research_analyst.models import SubjectResolution, SymbolMatch

    real = resolver_mod.resolve_subject
    try:
        resolver_mod.resolve_subject = lambda q, matches: SubjectResolution(  # noqa: E731
            query=q,
            status="resolved",
            resolved=SymbolMatch(
                symbol="AAA", market="US", market_name="United States", currency="USD"
            ),
            candidates=[],
            note="",
        )

        async def fake_search(q):  # noqa: ARG001
            return []

        result = await handle_ogsa_task(
            _task(action="research:resolve", payload={"query": "Acme Corp"}),
            symbol_search=fake_search,
        )
    finally:
        resolver_mod.resolve_subject = real
    assert result["status"] == "success"
    assert result["output"]["resolution"]["resolved"]["symbol"] == "AAA"


# ---------------------------------------------------------------------------
# Typed failures — no silent fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_task_typed_error():
    result = await handle_ogsa_task({"id": "t9"})  # missing fields
    assert result["status"] == "error"
    assert result["error"]["code"] == "INVALID_TASK"
    assert result["error"]["retryable"] is False


def test_empty_payload_passes_field_validation():
    # A legal empty payload is present, not missing (regression: truthiness check).
    task = _task(payload={})
    assert agency._validate_task(task) is task


@pytest.mark.asyncio
async def test_unknown_action_typed_error():
    result = await handle_ogsa_task(_task(action="research:fly"))
    assert result["status"] == "error"
    assert result["error"]["code"] == "UNKNOWN_ACTION"
    assert result["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_wrong_target_rejected():
    result = await handle_ogsa_task(_task(targetAgent="travel"))
    assert result["error"]["code"] == "UNKNOWN_TARGET"


@pytest.mark.asyncio
async def test_missing_ticker_invalid_input():
    result = await handle_ogsa_task(
        _task(payload={"report_type": "tactical"}), orchestrator=_FakeOrchestrator()
    )
    assert result["error"]["code"] == "INVALID_INPUT"
    assert result["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_bad_report_type_invalid_input():
    result = await handle_ogsa_task(
        _task(payload={"ticker": "AAA", "report_type": "yolo"}), orchestrator=_FakeOrchestrator()
    )
    assert result["error"]["code"] == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_unresolvable_ticker_not_retryable():
    orch = _FakeOrchestrator(fail_with=ValueError("Cannot resolve ticker 'ZZZ'."))
    result = await handle_ogsa_task(_task(payload={"ticker": "ZZZ"}), orchestrator=orch)
    assert result["status"] == "error"
    assert result["error"]["code"] == "RESOLUTION_FAILED"
    assert result["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_provider_error_is_retryable():
    orch = _FakeOrchestrator(fail_with=RuntimeError("yfinance 429"))
    result = await handle_ogsa_task(_task(), orchestrator=orch)
    assert result["error"]["code"] == "PROVIDER_ERROR"
    assert result["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_timeout_status():
    async def slow(request):  # noqa: ARG001
        await asyncio.sleep(5)
        return _FakeResponse()

    class SlowOrch:
        async def run(self, request):
            return await slow(request)

    result = await handle_ogsa_task(_task(), orchestrator=SlowOrch(), timeout_seconds=0.05)
    assert result["status"] == "timeout"
    assert result["error"]["code"] == "TIMEOUT"
    assert result["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_error_result_still_carries_audit():
    result = await handle_ogsa_task(_task(action="research:fly"))
    audit = result["output"]["audit"]
    assert audit["outcome"] == "error"
    assert audit["engine_version"] == agency.ENGINE_VERSION


def test_agency_error_as_dict():
    e = AgencyError("X", "boom", retryable=True)
    assert e.as_dict() == {"code": "X", "message": "boom", "retryable": True}
