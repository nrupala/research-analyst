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

"""FastAPI web server - REST API + static file serving for the browser UI.

Security:
  - CORS restricted to configured origins
  - Input validation via Pydantic (automatic)
  - Rate limiting on research endpoints (simple token bucket)
  - Request size limits enforced by uvicorn
  - No file uploads, no arbitrary code execution
  - All error responses are structured JSON (no stack traces in production)
  - CSP headers to prevent XSS

Endpoints:
  POST /api/research         - Run research pipeline, return structured response
  GET  /api/health           - Health check
  GET  /                     - Serve browser UI (static files)
"""
# Module: research_analyst/server.py | Version: 0.1.1 | Updated: 2026-06-03

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from . import __version__
from .api_models import (
    CompareAPIRequest,
    CompareAPIResponse,
    QuantAPIResponse,
    QuantDupontPayload,
    QuantExpectedValuePayload,
    ResearchAPIRequest,
    ResearchAPIResponse,
    ResolveAPIRequest,
    ResolveAPIResponse,
)
from .comparative import MAX_TICKERS, MIN_TICKERS, ComparativeOrchestrator
from .config import settings
from .disclaimer import DISCLAIMER_FULL, DISCLAIMER_SHORT, DISCLAIMER_VERSION
from .entitlements import (
    RA_PRO,
    SOURCE_DATA,
    APIKeyRecord,
    KeyStore,
    MeteringRecorder,
    WhiteLabelProfile,
    has_entitlement,
)
from .enums import ReportType
from .exporters import ts_definitions, xml_from_dict
from .models import ResearchRequest
from .orchestrator import ResearchOrchestrator
from .providers.market_data import MarketDataProvider
from .reports.comparative_renderer import render_html, render_markdown
from .stripe_billing import (
    PLANS,
    GrantStore,
    claim_grant,
    create_checkout_session,
    handle_event,
    verify_signature,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deploy marker (commit identity)
# ---------------------------------------------------------------------------

_BUILD_COMMIT_CACHE: str | None = None


def _build_commit() -> str:
    """Short commit SHA of the running code, for the deploy marker.

    Resolution order: ``RA_BUILD_COMMIT`` env var (deterministic builds),
    then ``git rev-parse --short HEAD`` from the repository root, then
    ``unknown``. Best-effort and cached once per process — never raises.
    """
    global _BUILD_COMMIT_CACHE
    if _BUILD_COMMIT_CACHE is not None:
        return _BUILD_COMMIT_CACHE
    commit = os.environ.get("RA_BUILD_COMMIT")
    if not commit:
        try:
            repo_root = Path(__file__).resolve().parents[1]
            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if out.returncode == 0:
                commit = out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            commit = None
    _BUILD_COMMIT_CACHE = commit or "unknown"
    return _BUILD_COMMIT_CACHE


# ---------------------------------------------------------------------------
# Content negotiation (typed-export layer)
# ---------------------------------------------------------------------------

SUPPORTED_FORMATS = {"json", "xml", "markdown", "html", "ts"}

_ACCEPT_MAP: dict[str, str] = {
    "application/json": "json",
    "application/xml": "xml",
    "text/xml": "xml",
    "text/markdown": "markdown",
    "text/html": "html",
    "text/typescript": "ts",
    "application/typescript": "ts",
    "*/*": "json",
}


def negotiate_format(fmt: str | None, accept_header: str) -> str:
    """Resolve the output format from ?format= or the Accept header."""
    if fmt:
        f = fmt.lower()
        if f not in SUPPORTED_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported format {fmt!r}. Allowed: {', '.join(sorted(SUPPORTED_FORMATS))}."
                ),
            )
        return f
    if accept_header:
        for part in accept_header.split(","):
            media = part.split(";")[0].strip().lower()
            if media in _ACCEPT_MAP:
                return _ACCEPT_MAP[media]
    return "json"


def _render_payload(
    data: dict[str, Any],
    fmt: str,
    root: str,
    *,
    markdown: str | None = None,
    html: str | None = None,
) -> Response:
    """Render a typed payload dict in the negotiated format."""
    if fmt == "json":
        return JSONResponse(data)
    if fmt == "xml":
        return Response(content=xml_from_dict(data, root), media_type="application/xml")
    if fmt == "markdown":
        if markdown is None:
            raise HTTPException(
                status_code=400, detail="markdown is not available for this endpoint."
            )
        return Response(content=markdown, media_type="text/markdown")
    if fmt == "html":
        if html is None:
            raise HTTPException(status_code=400, detail="html is not available for this endpoint.")
        return Response(content=html, media_type="text/html")
    if fmt == "ts":
        return Response(content=ts_definitions(), media_type="text/typescript")
    raise HTTPException(status_code=400, detail=f"Unsupported format {fmt!r}.")


# ---------------------------------------------------------------------------
# Rate limiter (per-IP, simple token bucket)
# ---------------------------------------------------------------------------


class _IPRateLimiter:
    """Per-IP rate limiter using token bucket. O(1) per check."""

    def __init__(self, rate: float = 2.0, burst: int = 5) -> None:
        self._rate = rate
        self._burst = burst
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self._max_ips = 10_000

    def allow(self, ip: str) -> bool:
        now = time.monotonic()
        if ip in self._buckets:
            tokens, last = self._buckets[ip]
            elapsed = now - last
            tokens = min(self._burst, tokens + elapsed * self._rate)
            self._buckets.move_to_end(ip)
        else:
            tokens = float(self._burst)
            if len(self._buckets) >= self._max_ips:
                self._buckets.popitem(last=False)
        if tokens >= 1.0:
            self._buckets[ip] = (tokens - 1.0, now)
            return True
        self._buckets[ip] = (tokens, now)
        return False


# ---------------------------------------------------------------------------
# Response models (defined in api_models.py — the typed-export source of truth)
# ---------------------------------------------------------------------------

__all__ = [
    "ResearchAPIRequest",
    "ResearchAPIResponse",
    "CompareAPIRequest",
    "CompareAPIResponse",
    "ResolveAPIRequest",
    "ResolveAPIResponse",
]


# Lazily-built singleton so the endpoint stays cheap to import and tests can
# override it via FastAPI dependency_overrides.
_comparative_orchestrator: ComparativeOrchestrator | None = None


def get_comparative_orchestrator() -> ComparativeOrchestrator:
    """FastAPI dependency returning a shared ComparativeOrchestrator."""
    global _comparative_orchestrator
    if _comparative_orchestrator is None:
        _comparative_orchestrator = ComparativeOrchestrator()
    return _comparative_orchestrator


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _eod_cache_expiry(cached_at: datetime, ttl_seconds: int) -> datetime:
    """When a cached report stops being servable (#66 EOD cadence).

    The owner's freshness design: reports refresh on the end-of-day
    cadence — a cached entry is served only until the next US market
    close (16:00 America/New_York) after it was generated, so the first
    reader after each close gets data as of that close. The configured
    TTL remains as an outer cap, whichever boundary comes first.
    Weekends are skipped; exchange holidays are not modelled (the TTL
    cap and the report's own SLA staleness warning bound that case).
    """
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    local = cached_at.astimezone(et)
    close = local.replace(hour=16, minute=0, second=0, microsecond=0)
    if local >= close:
        close += timedelta(days=1)
    while close.weekday() >= 5:  # Saturday/Sunday -> next weekday close
        close += timedelta(days=1)
    return min(close.astimezone(UTC), cached_at + timedelta(seconds=ttl_seconds))


def stamp_cache_hit(cached: ResearchAPIResponse, cached_at: datetime) -> ResearchAPIResponse:
    """Stamp a cache hit with freshness metadata and re-render markdown (#66).

    The markdown is re-rendered so the reader-visible freshness header
    reflects the actual cache age — never the generation-time copy.
    """
    resp = cached.model_copy(deep=True)
    meta = resp.metadata
    meta.cache_hit = True
    meta.cached_at_utc = cached_at
    age_days = (datetime.now(UTC) - cached_at).total_seconds() / 86400
    # EOD data goes stale after ~2 days (weekends/holidays excepted by the
    # TTL refresh); surface it loudly instead of silently.
    if age_days > 2:
        meta.sla_state = "stale"
        meta.stale_warning = (
            f"This report was generated from data as of {meta.data_as_of or 'an unknown date'} "
            f"({age_days:.0f} days ago). Quotes may not reflect the latest trading session."
        )
    else:
        meta.sla_state = "fresh"
    resp.reports_markdown = [r.to_markdown(metadata=meta) for r in resp.reports]
    return resp


def create_app(
    orchestrator: ResearchOrchestrator | None = None,
    rate_limiter: _IPRateLimiter | None = None,
    key_store: KeyStore | None = None,
    metering: MeteringRecorder | None = None,
    grant_store: GrantStore | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Research Analyst",
        description="Institutional-grade equity and ETF research agent.",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # --- Middleware ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-RA-Key"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=500)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.plot.ly https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self' https://ra.devinfo.dev https://ra.aimlds.org"
        )
        return response

    # --- Rate limiter (injectable so tests can widen the window) ---
    rate_limiter = rate_limiter or _IPRateLimiter(rate=0.5, burst=3)

    # --- Orchestrator (injectable so tests can stub the pipeline) ---
    orchestrator = orchestrator or ResearchOrchestrator()

    # --- API keys, metering, white-label (injectable for tests) ---
    if key_store is None and settings.billing.api_keys_file:
        key_store = KeyStore(settings.billing.api_keys_file)
    if grant_store is None and settings.billing.stripe_secret_key:
        grants_path = settings.billing.stripe_grants_file
        if not grants_path and settings.billing.api_keys_file:
            grants_path = str(Path(settings.billing.api_keys_file).parent / "stripe_grants.json")
        grant_store = GrantStore(grants_path or None)
    metering = metering or MeteringRecorder()
    app.state.key_store = key_store
    app.state.grant_store = grant_store
    app.state.metering = metering
    app.state.white_label = WhiteLabelProfile(
        org_name=settings.billing.white_label_org_name,
        prepared_on_url=settings.billing.white_label_prepared_on_url,
        footer_note=settings.billing.white_label_footer_note,
        show_support_link=settings.billing.white_label_show_support_link,
        accent_color=settings.billing.white_label_accent_color,
    )

    def _key_record(request: Request) -> APIKeyRecord | None:
        """Verify X-RA-Key against the key store. Returns record or None.

        The raw key is never logged or persisted.
        """
        store = request.app.state.key_store
        if store is None:
            return None
        return cast("APIKeyRecord | None", store.verify(request.headers.get("x-ra-key", "")))

    def _meter(request: Request, endpoint: str) -> None:
        record = _key_record(request)
        key_id = record.key_id if record else "anonymous"
        request.app.state.metering.record(key_id, endpoint)

    def _require_api_key(request: Request) -> None:
        """Gate for the metered endpoints (research, resolve, compare, quant).

        These endpoints serve the free public UI, which carries no key, so
        they arm ONLY in legacy paid-keys mode (RA_BILLING_PAID_KEYS set):
        a valid X-RA-Key is then required — a legacy paid key, or a KeyStore
        key carrying the `ra.pro` entitlement (`twf.pro` unlocks it via the
        bundle map). A KeyStore file on its own arms only the paid
        source-data gate (/api/research/data) and /api/usage; configuring
        the store must never lock the free public surfaces (release-gate
        finding H2, 2026-10-15). Raises 401 otherwise.
        """
        paid_keys = settings.billing.paid_keys
        if not paid_keys:
            return
        provided = request.headers.get("x-ra-key", "")
        if provided in paid_keys:
            return
        record = _key_record(request)
        if record is not None and has_entitlement(record, RA_PRO):
            return
        raise HTTPException(
            status_code=401,
            detail="Provide a valid X-RA-Key header to use this endpoint.",
        )

    # --- Market data (symbol/name resolution) ---
    market_provider = MarketDataProvider()

    # --- Report cache (Issue #66: TTL-bound, staleness-visible) ---
    # Entries are (response, cached_at_utc). A hit past the TTL is treated
    # as a miss and regenerated — a stale report is never silently re-served.
    report_cache: OrderedDict[str, tuple[ResearchAPIResponse, datetime]] = OrderedDict()
    cache_max = settings.server.report_cache_max
    cache_ttl = settings.server.report_cache_ttl_seconds

    def _cache_key(req: ResearchAPIRequest) -> str:
        raw = f"{req.ticker}:{req.report_type}:{req.timeframe}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _cache_store(ck: str, api_response: ResearchAPIResponse) -> None:
        if len(report_cache) >= cache_max:
            report_cache.popitem(last=False)
        report_cache[ck] = (api_response, datetime.now(UTC))

    # ================================================================
    # API Endpoints
    # ================================================================

    @app.get("/api/disclaimer")
    async def get_disclaimer() -> dict[str, str]:
        return {
            "version": DISCLAIMER_VERSION,
            "full": DISCLAIMER_FULL,
            "short": DISCLAIMER_SHORT,
        }

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Health check: service is up + version + commit served (per VERSIONING.md)."""
        return {
            "status": "ok",
            "version": __version__,
            "service": "research-analyst",
            "commit": _build_commit(),
        }

    @app.post("/api/resolve", response_model=ResolveAPIResponse)
    async def resolve_subject_endpoint(
        body: ResolveAPIRequest,
        request: Request,
        format: str | None = Query(default=None),
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded.")
        _require_api_key(request)
        from .resolver import resolve_subject

        matches = await market_provider.search_symbols(body.query)
        res = resolve_subject(body.query, matches)
        api_response = ResolveAPIResponse(
            query=res.query,
            status=res.status,
            resolved=res.resolved,
            candidates=res.candidates,
            note=res.note,
        )
        fmt = negotiate_format(format, request.headers.get("accept", ""))
        if fmt in ("markdown", "html"):
            raise HTTPException(status_code=400, detail=f"{fmt} is not available for /api/resolve.")
        _meter(request, "resolve")
        return _render_payload(api_response.model_dump(mode="json"), fmt, "resolution")

    @app.post("/api/research", response_model=ResearchAPIResponse)
    async def run_research(
        body: ResearchAPIRequest,
        request: Request,
        format: str | None = Query(default=None),
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded.")
        _require_api_key(request)

        request_id = str(uuid.uuid4())[:8]

        ck = _cache_key(body)
        now = datetime.now(UTC)
        cached_entry = report_cache.get(ck)
        if cached_entry is not None:
            cached, cached_at = cached_entry
            age = (now - cached_at).total_seconds()
            if now <= _eod_cache_expiry(cached_at, cache_ttl):
                logger.info("Cache hit for %s (age %.0fs)", body.ticker, age)
                report_cache.move_to_end(ck)
                api_response = stamp_cache_hit(cached, cached_at)
            else:
                logger.info(
                    "Cache entry for %s expired (age %.0fs; EOD boundary or TTL %ds); regenerating",
                    body.ticker,
                    age,
                    cache_ttl,
                )
                del report_cache[ck]
                api_response = await _run_research_uncached(body, request_id)
                _cache_store(ck, api_response)
        else:
            api_response = await _run_research_uncached(body, request_id)
            _cache_store(ck, api_response)

        fmt = negotiate_format(format, request.headers.get("accept", ""))
        if fmt == "html":
            raise HTTPException(
                status_code=400,
                detail="html is not available for /api/research (use markdown).",
            )
        markdown = "\n\n---\n\n".join(api_response.reports_markdown) if fmt == "markdown" else None
        _meter(request, "research")
        return _render_payload(
            api_response.model_dump(mode="json"), fmt, "research", markdown=markdown
        )

    async def _run_pipeline(body: ResearchAPIRequest) -> Any:
        """Build the ResearchRequest and run the orchestrator -> typed
        ResearchResponse (shared by /api/research and the paid data endpoint)."""
        report_types = ReportType.from_user_input(body.report_type)

        from .enums import Timeframe

        timeframe_map = {
            "1M": Timeframe.ONE_MONTH,
            "3M": Timeframe.THREE_MONTHS,
            "6M": Timeframe.SIX_MONTHS,
            "1Y": Timeframe.ONE_YEAR,
            "3Y": Timeframe.THREE_YEARS,
            "5Y": Timeframe.FIVE_YEARS,
            "10Y": Timeframe.TEN_YEARS,
        }
        timeframe = timeframe_map.get(body.timeframe.upper(), Timeframe.ONE_YEAR)

        research_request = ResearchRequest(
            ticker=body.ticker.upper().strip(),
            report_types=report_types,
            compare_tickers=body.compare_tickers,
            timeframe=timeframe,
            custom_assumptions=body.custom_assumptions,
        )

        try:
            result = await orchestrator.run(research_request)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.error("Pipeline error for %s: %s", body.ticker, e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Research pipeline failed: {type(e).__name__}",
            ) from e
        return result

    async def _run_research_uncached(
        body: ResearchAPIRequest, request_id: str
    ) -> ResearchAPIResponse:
        result = await _run_pipeline(body)
        api_response = ResearchAPIResponse(
            request_id=request_id,
            ticker=result.ticker,
            company_name=result.company_name,
            security_type=result.security_type.value,
            reports=result.reports,
            metadata=result.metadata,
            reports_markdown=[],
        )
        # Render with metadata so the freshness/sources/snapshot footer (#66/#69/#74) is included.
        api_response.reports_markdown = [
            report.to_markdown(metadata=result.metadata) for report in result.reports
        ]
        return api_response

    @app.post("/api/compare", response_model=CompareAPIResponse)
    async def run_compare(
        body: CompareAPIRequest,
        request: Request,
        format: str | None = Query(default=None),
        comparative: ComparativeOrchestrator = Depends(get_comparative_orchestrator),
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded.")
        _require_api_key(request)

        request_id = str(uuid.uuid4())[:8]

        # Validate the ticker count up front with a clear message (2-5 distinct).
        distinct = ComparativeOrchestrator.normalize_tickers(body.tickers)
        if not (MIN_TICKERS <= len(distinct) <= MAX_TICKERS):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Provide between {MIN_TICKERS} and {MAX_TICKERS} distinct tickers "
                    f"(received {len(distinct)})."
                ),
            )

        try:
            report = await comparative.run(distinct, timeframe=body.timeframe)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.error("Comparative pipeline error for %s: %s", distinct, e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Comparative pipeline failed: {type(e).__name__}",
            ) from e

        api_response = CompareAPIResponse(
            request_id=request_id,
            tickers=report.tickers,
            report=report,
            report_markdown=render_markdown(report),
            report_html=render_html(report, white_label=request.app.state.white_label),
        )
        _meter(request, "compare")

        fmt = negotiate_format(format, request.headers.get("accept", ""))
        return _render_payload(
            api_response.model_dump(mode="json"),
            fmt,
            "comparison",
            markdown=api_response.report_markdown if fmt == "markdown" else None,
            html=api_response.report_html if fmt == "html" else None,
        )

    @app.get("/api/research/quant", response_model=QuantAPIResponse)
    async def get_quant(
        request: Request,
        ticker: str = Query(..., min_length=1, max_length=20),
        discount_rate: float | None = Query(default=None),
        scenarios: str | None = Query(default=None),
    ) -> QuantAPIResponse:
        """Quant engine results for a ticker (metered; X-RA-Key gate applies
        under the same activation semantics as the other data endpoints).

        Runs the ported quant engine (trends, DuPont, forensics, valuation,
        allocation) over the provider financial statements. Optional
        ``discount_rate`` query param is an analyst assumption (not observed
        data) enabling the implied-growth inversions. Optional ``scenarios``
        is a URL-encoded JSON array of {label, value, probability} for the
        expected-value computation; when absent, expected_value is null with
        a reason.
        """
        from .quant_engine.adapter import from_financial_statements
        from .quant_engine.expected import ScenarioInput, expected_value
        from .reports.quant_section import compute_quant_results

        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded.")
        _require_api_key(request)

        clean = ticker.upper().strip()

        financials_yf = await orchestrator._fetch_yf_financials(clean)
        financials_sec = await orchestrator._fetch_sec_financials(clean)
        financials = financials_yf if financials_yf else financials_sec
        if not financials:
            raise HTTPException(
                status_code=404,
                detail=f"No financial statements available for '{clean}'.",
            )

        try:
            series = from_financial_statements(financials, clean)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        if not series.periods:
            raise HTTPException(
                status_code=404,
                detail=f"No usable fiscal periods for '{clean}'.",
            )

        profile = None
        price_now: float | None = None
        try:
            profile = await market_provider.get_company_profile(clean)
        except Exception as e:
            logger.debug("Quant endpoint: profile unavailable for %s: %s", clean, e)
        try:
            prices = await market_provider.get_price_series(clean, period="1y")
            price_now = float(prices.current_price) if prices.current_price else None
        except Exception as e:
            logger.debug("Quant endpoint: price unavailable for %s: %s", clean, e)

        def _f(v: object) -> float | None:
            try:
                return float(v) if v is not None else None  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None

        latest_stmt = financials[-1] if financials else None
        market: dict[str, object] = {
            "price": price_now,
            "market_cap": _f(getattr(profile, "market_cap", None)),
            "enterprise_value": _f(getattr(profile, "enterprise_value", None)),
            "net_debt": _f(getattr(latest_stmt, "net_debt", None)),
            "currency": getattr(profile, "currency", None),
            "discount_rate": discount_rate,
        }
        if market["currency"]:
            series.currency = market["currency"]  # type: ignore[assignment]

        # Latest observed price → the most recent period's price series entry,
        # so Altman X4 (market leverage) and market-cap screens can compute.
        # Older periods keep None: their period-end prices are not recreated.
        if price_now is not None and series.periods:
            series.price[-1] = price_now

        results = compute_quant_results(series, market)

        # Optional expected value over caller-supplied scenarios.
        ev_expected: float | None = None
        ev_contribs: list[dict[str, float | str]] | None = None
        ev_reason: str | None = None
        if scenarios:
            try:
                import json as _json

                raw_scenarios = _json.loads(scenarios)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid scenarios JSON: {e}") from e
            if not isinstance(raw_scenarios, list):
                raise HTTPException(status_code=400, detail="scenarios must be a JSON array.")
            try:
                parsed = [
                    ScenarioInput(
                        label=str(s.get("label", f"scenario_{i}")),
                        value=s.get("value"),
                        probability=s.get("probability"),
                    )
                    for i, s in enumerate(raw_scenarios)
                ]
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid scenario entry: {e}") from e
            ev_result = expected_value(parsed)
            if isinstance(ev_result, dict):
                ev_reason = ev_result.get("error", "expected value failed validation")
            else:
                ev_expected = ev_result.expected
                # Engine annotates list[dict[str, float]] but emits str labels
                # at runtime ({"label": ..., "contribution": ...}); cast to the
                # API model's wider type. Engine file itself stays untouched.
                ev_contribs = ev_result.contributions
        else:
            ev_reason = "no scenarios provided"

        _meter(request, "quant")
        return QuantAPIResponse(
            ticker=clean,
            periods=[p.period for p in series.periods],
            currency=series.currency,
            generated_at=datetime.now(UTC),
            trends=results["trends"],
            dupont=QuantDupontPayload(
                rows=results["dupont"]["rows"],
                latest=results["dupont"]["latest"] or None,
                attribution=results["dupont"]["attribution"] or None,
            ),
            forensics=results["forensics"],
            valuation=results["valuation"],
            allocation=results["allocation"],
            expected_value=QuantExpectedValuePayload(
                expected=ev_expected,
                contributions=ev_contribs,
                reason=ev_reason,
            ),
            missing_inputs=results["missing_inputs"],
            assumptions=results["assumptions"],
        )

    @app.post("/api/research/data", response_model=None)
    async def source_data_download(
        body: ResearchAPIRequest,
        request: Request,
        format: str | None = Query(default=None),
    ) -> Response:
        """Paid feature (8c-2): the raw source-data bundle behind a report.

        Gated by a valid X-RA-Key header whenever any key mechanism is
        configured — RA_BILLING_PAID_KEYS or a KeyStore file (see
        BillingConfig). When neither is configured (local/demo), the
        endpoint is open. Returns JSON (canonical) or CSV.
        """
        from .data_export import build_bundle, bundle_to_csv

        # --- Paid-key gate ---
        # Legacy shared-secret keys (RA_BILLING_PAID_KEYS) keep working; hashed,
        # revocable KeyStore keys (entitlements.py) are also accepted when they
        # carry the `source.data` entitlement. Open when neither is configured.
        paid_keys = settings.billing.paid_keys
        if paid_keys or request.app.state.key_store is not None:
            provided = request.headers.get("x-ra-key", "")
            legacy_ok = bool(paid_keys) and provided in paid_keys
            record = _key_record(request)
            entitled = has_entitlement(record, SOURCE_DATA)
            if not (legacy_ok or entitled):
                raise HTTPException(
                    status_code=401,
                    detail=(
                        "This is a paid feature. Provide a valid X-RA-Key header (or "
                        "subscribe)."
                    ),
                )

        _meter(request, "source_data")

        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded.")

        # Run the pipeline and keep the typed ResearchResponse (not the API wire model)
        _result = await _run_pipeline(body)
        bundle = build_bundle(_result)

        fmt = (format or "json").lower()
        if fmt not in ("json", "csv"):
            raise HTTPException(status_code=400, detail="Supported formats: json, csv.")

        if fmt == "csv":
            csv_text = bundle_to_csv(bundle)
            return Response(
                content=csv_text,
                media_type="text/csv",
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="{body.ticker.upper()}_source_data.csv"'
                    )
                },
            )
        return Response(
            content=__import__("json").dumps(bundle, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{body.ticker.upper()}_source_data.json"'
                )
            },
        )

    @app.get("/api/usage")
    async def usage_summary(request: Request) -> JSONResponse:
        """Per-key metering summary for today (UTC).

        Requires a valid X-RA-Key header. Returns the key id, its effective
        entitlements (bundle-aware) and per-endpoint request counts. The raw
        key is never logged or returned.
        """
        record = _key_record(request)
        if record is None:
            raise HTTPException(
                status_code=401,
                detail="Provide a valid X-RA-Key header to view usage.",
            )
        from .entitlements import effective_entitlements

        metering = request.app.state.metering
        return JSONResponse(
            {
                "key_id": record.key_id,
                "label": record.label,
                "entitlements": sorted(effective_entitlements(record)),
                "day_utc": metering._today_utc(),
                "usage": metering.usage(record.key_id),
                "total_requests": metering.total_requests(record.key_id),
            }
        )

    # ================================================================
    # Stripe billing (Stream A) — dormant until configured
    # ================================================================

    @app.post("/api/billing/checkout")
    async def billing_checkout(body: dict[str, Any], request: Request) -> JSONResponse:
        """Create a Stripe Checkout Session for a paid plan.

        Dormant (503) until Stripe is configured. Card data goes to
        Stripe's hosted page only; this service receives just the plan.
        """
        billing = settings.billing
        if not billing.stripe_secret_key:
            raise HTTPException(status_code=503, detail="Billing is not configured.")
        plan = PLANS.get(str(body.get("plan", "")))
        if plan is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown plan. Choose one of: {', '.join(sorted(PLANS))}.",
            )
        price_id = str(getattr(billing, plan.price_config_attr, "") or "")
        if not price_id:
            raise HTTPException(status_code=503, detail=f"Plan {plan.name} is not priced yet.")
        try:
            session = create_checkout_session(
                plan=plan,
                price_id=price_id,
                secret_key=billing.stripe_secret_key,
                success_url=billing.stripe_success_url,
                cancel_url=billing.stripe_cancel_url,
            )
        except Exception:
            logger.exception("Stripe checkout session creation failed")
            raise HTTPException(status_code=502, detail="Payment provider unreachable.") from None
        return JSONResponse({"checkout_url": session.get("url"), "session_id": session.get("id")})

    @app.post("/api/billing/webhook")
    async def billing_webhook(request: Request) -> JSONResponse:
        """Stripe webhook: grant on payment, revoke on cancellation.

        The signature is verified before anything is acted on; key
        issuance itself happens at claim time, never here.
        """
        billing = settings.billing
        if not (billing.stripe_secret_key and billing.stripe_webhook_secret):
            raise HTTPException(status_code=503, detail="Billing is not configured.")
        key_store_state = request.app.state.key_store
        grant_store_state = request.app.state.grant_store
        if key_store_state is None or grant_store_state is None:
            raise HTTPException(status_code=503, detail="Billing storage is not configured.")
        payload = await request.body()
        signature = request.headers.get("stripe-signature", "")
        if not verify_signature(payload, signature, billing.stripe_webhook_secret):
            raise HTTPException(status_code=400, detail="Invalid signature.")
        try:
            event = json.loads(payload)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload.") from None
        price_to_plan = {
            name: str(getattr(billing, p.price_config_attr, "") or "") for name, p in PLANS.items()
        }
        outcome = handle_event(
            event,
            key_store=key_store_state,
            grant_store=grant_store_state,
            price_to_plan=price_to_plan,
        )
        return JSONResponse({"received": True, "outcome": outcome})

    @app.get("/api/billing/claim")
    async def billing_claim(request: Request, session_id: str = Query(...)) -> JSONResponse:
        """One-time key reveal for a paid checkout session.

        The raw key is returned exactly once, here; only its hash is
        ever stored. A second claim is refused (support re-issues).
        """
        key_store_state = request.app.state.key_store
        grant_store_state = request.app.state.grant_store
        if key_store_state is None or grant_store_state is None:
            raise HTTPException(status_code=503, detail="Billing is not configured.")
        try:
            claimed = claim_grant(
                session_id, key_store=key_store_state, grant_store=grant_store_state
            )
        except ValueError:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This purchase was already claimed. If you lost your key, "
                    "contact support and we will re-issue it."
                ),
            ) from None
        if claimed is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No paid checkout found for this session yet. If you just "
                    "paid, wait a few seconds and retry."
                ),
            )
        raw_key, plan_name = claimed
        return JSONResponse(
            {
                "api_key": raw_key,
                "plan": plan_name,
                "note": "Save this key now — it is shown only once and cannot be recovered.",
            }
        )

    # ================================================================
    # Static file serving - ALL UI files served from root /
    #
    # This makes the same paths work on:
    #   - Fly.io (FastAPI serves everything)
    #   - Cloudflare Pages (static hosting, root-relative paths)
    #   - Local dev (python -m uvicorn)
    #
    # The UI references /app.js, /style.css, /sw.js, /manifest.json,
    # /icons/*, /worker.js — all at root, no /static/ prefix.
    # ================================================================

    ui_dir = settings.server.static_dir

    # Explicit routes for known UI files (registered BEFORE the catch-all mount)
    # This ensures they take priority over the StaticFiles mount

    @app.get("/manifest.json")
    async def serve_manifest() -> FileResponse:
        p = ui_dir / "manifest.json"
        if p.exists():
            return FileResponse(str(p), media_type="application/json")
        raise HTTPException(status_code=404)

    @app.get("/sw.js")
    async def serve_sw() -> FileResponse:
        p = ui_dir / "sw.js"
        if p.exists():
            return FileResponse(str(p), media_type="application/javascript")
        raise HTTPException(status_code=404)

    @app.get("/worker.js")
    async def serve_worker() -> FileResponse:
        p = ui_dir / "worker.js"
        if p.exists():
            return FileResponse(str(p), media_type="application/javascript")
        raise HTTPException(status_code=404)

    @app.get("/app.js")
    async def serve_app_js() -> FileResponse:
        p = ui_dir / "app.js"
        if p.exists():
            return FileResponse(str(p), media_type="application/javascript")
        raise HTTPException(status_code=404)

    @app.get("/style.css")
    async def serve_style_css() -> FileResponse:
        p = ui_dir / "style.css"
        if p.exists():
            return FileResponse(str(p), media_type="text/css")
        raise HTTPException(status_code=404)

    # Serve /icons/* for PWA icons
    icons_dir = ui_dir / "icons"
    if icons_dir.exists():
        app.mount("/icons", StaticFiles(directory=str(icons_dir)), name="icons")

    # Serve index.html for root /
    @app.get("/", response_class=HTMLResponse)
    async def serve_index() -> HTMLResponse:
        index_path = ui_dir / "index.html"
        if index_path.exists():
            return HTMLResponse(content=index_path.read_text())
        return HTMLResponse(
            content="<h1>Research Analyst</h1><p>UI not found.</p>",
            status_code=200,
        )

    return app


# Convenience: create app instance for uvicorn
app = create_app()
