"""AIOA / OGSA agency adapter — Research Analyst as a `research-intel` agency.

This module is RA-owned and standalone: it lets an OGSA orchestrator
(AllinOneAgency or any compatible governor) drive Research Analyst as the
`research-intel` agency WITHOUT modifying AIOA. AIOA keeps dynamically
importing its own placeholder; a deployment that wants the real engine
points the `research-intel` handler at :func:`handle_ogsa_task`.

Contract (grounded in the RA product roadmap):
- Inputs: ticker/listing, report type, horizon, explicit assumptions.
- Capabilities: market read, filing read, model inference, report write.
  No ambient access — the adapter only runs the declared actions below.
- Outputs: schema_version, structured report, warnings, provenance.
- Audit: request ID, engine version, data timestamp, report hash, outcome.
- Failure: typed errors, no silent fallback, safe retry policy
  (every error carries a `retryable` flag).

OGSA wire shapes (from AllinOneAgency `program/ogsa/src/types.ts`):
- Task:   {id, sourceAgent, targetAgent, action, payload, tokenId,
            priority, createdAt}
- Result: {taskId, status: "success"|"error"|"timeout", output,
            error?, completedAt}
"""
# Module: research_analyst/agency.py | Version: 1.0 | Updated: 2026-09-25

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from . import __version__ as ENGINE_VERSION  # noqa: N812
from .api_models import SCHEMA_VERSION
from .enums import ReportType, Timeframe

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

AGENCY_ID = "research-analyst"
OGSA_CATEGORY = "research-intel"  # matches AIOA AgentCategory.RESEARCH
OGSA_CAPABILITIES = ["research:analyze", "research:compare", "research:resolve"]
ACCEPTED_TARGETS = {"research-intel", "research-analyst"}

DEFAULT_TIMEOUT_SECONDS = 300.0


# ---------------------------------------------------------------------------
# Typed errors — no silent fallback; every error names its retry policy.
# ---------------------------------------------------------------------------


class AgencyError(Exception):
    """Typed agency failure with an explicit retry policy."""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "retryable": self.retryable}


INVALID_TASK = "INVALID_TASK"  # malformed OGSA task envelope
UNKNOWN_TARGET = "UNKNOWN_TARGET"  # not addressed to this agency
UNKNOWN_ACTION = "UNKNOWN_ACTION"  # action not in OGSA_CAPABILITIES
INVALID_INPUT = "INVALID_INPUT"  # payload failed validation
RESOLUTION_FAILED = "RESOLUTION_FAILED"  # ticker/subject could not be resolved
PROVIDER_ERROR = "PROVIDER_ERROR"  # upstream market/filing data failed
TIMEOUT = "TIMEOUT"  # exceeded the task deadline
INTERNAL_ERROR = "INTERNAL_ERROR"  # unexpected failure


# ---------------------------------------------------------------------------
# Manifest — the agency's self-description for OGSA registration/discovery.
# ---------------------------------------------------------------------------


def agency_manifest() -> dict[str, Any]:
    """Return the RA agency manifest (JSON-serializable)."""
    return {
        "agency_id": AGENCY_ID,
        "ogsa_category": OGSA_CATEGORY,
        "ogsa_capabilities": list(OGSA_CAPABILITIES),
        "engine_version": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "actions": {
            "research:analyze": {
                "description": (
                    "Generate an institutional-grade research report for one "
                    "ticker (educational, non-advisory; never buy/sell/hold)."
                ),
                "inputs": {
                    "ticker": "Equity/ETF ticker symbol (required).",
                    "report_type": "comprehensive | tactical | long_term (default comprehensive).",
                    "timeframe": "1M | 3M | 6M | 1Y | 3Y | 5Y | 10Y (default 1Y).",
                    "assumptions": "Explicit assumption overrides, dict (default {}).",
                },
                "outputs": ["schema_version", "report", "warnings", "provenance", "audit"],
            },
            "research:compare": {
                "description": "Side-by-side comparison of 2-5 tickers.",
                "inputs": {
                    "tickers": "List of 2-5 ticker symbols (required).",
                    "timeframe": "1M | 3M | 6M | 1Y | 3Y | 5Y | 10Y (default 1Y).",
                },
                "outputs": ["schema_version", "comparison", "warnings", "provenance", "audit"],
            },
            "research:resolve": {
                "description": "Resolve a company/security name or query to a ticker.",
                "inputs": {"query": "Free-text query (required)."},
                "outputs": ["schema_version", "resolution", "warnings", "audit"],
            },
        },
        "capability_notes": [
            "market read (EOD quotes, previous close)",
            "filing read (SEC EDGAR company filings)",
            "model inference (valuation, risk, lens engines)",
            "report write (structured markdown/HTML/JSON)",
        ],
        "constraints": [
            "No ambient access: only the declared actions run.",
            "Educational output only: never buy/sell/hold guidance, never executes trades.",
            "Ad-free, affiliate-free output.",
            "Failures are typed with an explicit retryable flag; no silent fallback.",
        ],
        "audit_contract": [
            "request_id",
            "engine_version",
            "data_timestamp",
            "report_hash",
            "outcome",
        ],
    }


# ---------------------------------------------------------------------------
# Report hash — deterministic fingerprint of a structured report.
# ---------------------------------------------------------------------------


def report_hash(report: dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON of a structured report."""
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Task handling
# ---------------------------------------------------------------------------


def _validate_task(task: Any) -> dict[str, Any]:
    if not isinstance(task, dict):
        raise AgencyError(INVALID_TASK, "OGSA task must be a JSON object.", retryable=False)
    missing = [k for k in ("id", "targetAgent", "action", "payload") if not task.get(k)]
    if missing:
        raise AgencyError(
            INVALID_TASK,
            f"OGSA task missing required fields: {', '.join(missing)}.",
            retryable=False,
        )
    if not isinstance(task["payload"], dict):
        raise AgencyError(INVALID_TASK, "OGSA task payload must be a JSON object.", retryable=False)
    if task["targetAgent"] not in ACCEPTED_TARGETS:
        raise AgencyError(
            UNKNOWN_TARGET,
            f"Task addressed to {task['targetAgent']!r}; "
            f"this agency serves {sorted(ACCEPTED_TARGETS)}.",
            retryable=False,
        )
    if task["action"] not in OGSA_CAPABILITIES:
        raise AgencyError(
            UNKNOWN_ACTION,
            f"Unknown action {task['action']!r}; supported: {', '.join(OGSA_CAPABILITIES)}.",
            retryable=False,
        )
    return task


def _legacy_payload_mapping(payload: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """Map the legacy AIOA placeholder shape ({text, urls}) onto the contract.

    The old in-AIOA placeholder called analyze(text, urls). When a governor
    still sends that shape we map it explicitly and warn — never silently.
    """
    payload = dict(payload)
    if "ticker" not in payload and "tickers" not in payload and "query" not in payload:
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            payload["ticker"] = text.strip()
            warnings.append(
                "Mapped legacy AIOA payload field 'text' to 'ticker'; "
                "prefer the versioned contract inputs."
            )
    return payload


def _parse_report_type(value: Any) -> ReportType:
    if value is None:
        return ReportType.COMPREHENSIVE
    try:
        return ReportType(str(value).lower())
    except ValueError:
        raise AgencyError(
            INVALID_INPUT,
            f"Invalid report_type {value!r}; expected one of "
            + ", ".join(rt.value for rt in ReportType)
            + ".",
            retryable=False,
        )


def _parse_timeframe(value: Any) -> Timeframe:
    if value is None:
        return Timeframe.ONE_YEAR
    try:
        return Timeframe(str(value))
    except ValueError:
        raise AgencyError(
            INVALID_INPUT,
            f"Invalid timeframe {value!r}; expected one of "
            + ", ".join(tf.value for tf in Timeframe)
            + ".",
            retryable=False,
        )


async def _run_analyze(
    payload: dict[str, Any],
    warnings: list[str],
    orchestrator: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run research:analyze. Returns (report_dict, provenance)."""
    from .models import ResearchRequest

    ticker = payload.get("ticker")
    if not ticker or not str(ticker).strip():
        raise AgencyError(INVALID_INPUT, "research:analyze requires 'ticker'.", retryable=False)
    assumptions = payload.get("assumptions") or {}
    if not isinstance(assumptions, dict):
        raise AgencyError(INVALID_INPUT, "'assumptions' must be a JSON object.", retryable=False)

    request = ResearchRequest(
        ticker=str(ticker).strip(),
        report_types=[_parse_report_type(payload.get("report_type"))],
        timeframe=_parse_timeframe(payload.get("timeframe")),
        custom_assumptions=assumptions,
    )
    try:
        response = await orchestrator.run(request)
    except AgencyError:
        raise
    except ValueError as e:
        # The pipeline raises ValueError when the ticker cannot be resolved —
        # a client error, not something a retry would fix.
        raise AgencyError(RESOLUTION_FAILED, str(e), retryable=False)
    except Exception as e:  # upstream data failure -> typed, retryable
        raise AgencyError(PROVIDER_ERROR, f"Research pipeline failed: {e}", retryable=True)

    report = response.model_dump(mode="json")
    provenance = {
        "sources": [r.get("name") for r in report.get("metadata", {}).get("source_records", [])]
        or report.get("metadata", {}).get("data_sources", []),
        "data_as_of": report.get("metadata", {}).get("data_as_of"),
        "warnings": report.get("metadata", {}).get("warnings", []),
        "engine_version": ENGINE_VERSION,
    }
    warnings.extend(report.get("metadata", {}).get("warnings", []))
    return report, provenance


async def _run_compare(
    payload: dict[str, Any],
    warnings: list[str],
    comparative: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run research:compare. Returns (comparison_dict, provenance)."""
    tickers = payload.get("tickers")
    if not isinstance(tickers, list) or not (2 <= len(tickers) <= 5):
        raise AgencyError(
            INVALID_INPUT,
            "research:compare requires 'tickers' as a list of 2-5 symbols.",
            retryable=False,
        )
    timeframe = payload.get("timeframe") or "1Y"
    try:
        report = await comparative.run(tickers, timeframe=str(timeframe))
    except AgencyError:
        raise
    except ValueError as e:  # validation-style failure: not retryable
        raise AgencyError(INVALID_INPUT, str(e), retryable=False)
    except Exception as e:
        raise AgencyError(PROVIDER_ERROR, f"Comparison pipeline failed: {e}", retryable=True)

    comparison = report.model_dump(mode="json")
    sources: list[str] = []
    for recs in (report.source_records or {}).values():
        sources.extend(r.name for r in recs)
    provenance = {
        "sources": sorted(set(sources)),
        "engine_version": ENGINE_VERSION,
        "tickers": report.tickers,
    }
    return comparison, provenance


async def _run_resolve(
    payload: dict[str, Any],
    warnings: list[str],
    symbol_search: Callable[[str], Awaitable[list[Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run research:resolve. Returns (resolution_dict, provenance)."""
    from .resolver import resolve_subject

    query = payload.get("query")
    if not query or not str(query).strip():
        raise AgencyError(INVALID_INPUT, "research:resolve requires 'query'.", retryable=False)
    try:
        matches = await symbol_search(str(query).strip())
        res = resolve_subject(str(query).strip(), matches or [])
    except AgencyError:
        raise
    except Exception as e:
        raise AgencyError(PROVIDER_ERROR, f"Symbol search failed: {e}", retryable=True)
    if res.status in ("not_found", "no_match"):
        raise AgencyError(
            RESOLUTION_FAILED,
            f"Could not resolve {query!r} to a security.",
            retryable=False,
        )
    resolution = res.model_dump(mode="json")
    return resolution, {"engine_version": ENGINE_VERSION}


def _default_orchestrator() -> Any:
    from .orchestrator import ResearchOrchestrator

    return ResearchOrchestrator()


def _default_comparative() -> Any:
    from .comparative import ComparativeOrchestrator

    return ComparativeOrchestrator()


async def _default_symbol_search(query: str) -> list[Any]:
    from .providers.market_data import MarketDataProvider

    provider = MarketDataProvider()
    try:
        return await provider.search_symbols(query)
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result


async def handle_ogsa_task(
    task: dict[str, Any],
    *,
    orchestrator: Any | None = None,
    comparative: Any | None = None,
    symbol_search: Callable[[str], Awaitable[list[Any]]] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Handle one OGSA task and return an OGSA TaskResult dict.

    Dependencies are injectable for offline testing; defaults wire the real
    pipeline. Never raises: every failure becomes a typed TaskResult.
    """
    started = time.time()
    try:
        validated = _validate_task(task)
    except AgencyError as e:
        return _error_result(str(task.get("id")) if isinstance(task, dict) else "unknown", e)

    task_id = validated["id"]
    action = validated["action"]
    warnings: list[str] = []
    payload = _legacy_payload_mapping(validated["payload"], warnings)
    request_id = f"ogsa-{uuid.uuid4().hex[:12]}"

    async def _execute() -> dict[str, Any]:
        if action == "research:analyze":
            orch = orchestrator or _default_orchestrator()
            result, provenance = await _run_analyze(payload, warnings, orch)
            body = {"report": result}
        elif action == "research:compare":
            comp = comparative or _default_comparative()
            result, provenance = await _run_compare(payload, warnings, comp)
            body = {"comparison": result}
        else:  # research:resolve
            search = symbol_search or _default_symbol_search
            result, provenance = await _run_resolve(payload, warnings, search)
            body = {"resolution": result}

        digest = report_hash(result)
        output = {
            "schema_version": SCHEMA_VERSION,
            "agency": AGENCY_ID,
            "capability": action,
            **body,
            "warnings": warnings,
            "provenance": provenance,
            "audit": {
                "request_id": request_id,
                "task_id": task_id,
                "source_agent": validated.get("sourceAgent"),
                "engine_version": ENGINE_VERSION,
                "data_timestamp": provenance.get("data_as_of"),
                "report_hash": digest,
                "outcome": "success",
                "duration_seconds": round(time.time() - started, 3),
            },
        }
        return {
            "taskId": task_id,
            "status": "success",
            "output": output,
            "completedAt": int(time.time() * 1000),
        }

    try:
        return await asyncio.wait_for(_execute(), timeout=timeout_seconds)
    except TimeoutError:
        return _error_result(
            task_id,
            AgencyError(TIMEOUT, f"Task exceeded {timeout_seconds}s deadline.", retryable=True),
            request_id=request_id,
            status="timeout",
        )
    except AgencyError as e:
        return _error_result(task_id, e, request_id=request_id)
    except Exception as e:  # last-resort guard: never leak an exception
        logger.exception("Unhandled agency failure for task %s", task_id)
        return _error_result(
            task_id,
            AgencyError(INTERNAL_ERROR, f"Unexpected failure: {e}", retryable=False),
            request_id=request_id,
        )


def _error_result(
    task_id: str,
    error: AgencyError,
    *,
    request_id: str | None = None,
    status: str = "error",
) -> dict[str, Any]:
    return {
        "taskId": task_id,
        "status": status,
        "output": {
            "schema_version": SCHEMA_VERSION,
            "agency": AGENCY_ID,
            "engine_version": ENGINE_VERSION,
            "audit": {
                "request_id": request_id or f"ogsa-{uuid.uuid4().hex[:12]}",
                "task_id": task_id,
                "engine_version": ENGINE_VERSION,
                "outcome": status,
            },
        },
        "error": error.as_dict(),
        "completedAt": int(time.time() * 1000),
    }
