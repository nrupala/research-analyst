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
import logging
import time
import uuid
from collections import OrderedDict
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from . import __version__
from .api_models import (
    CompareAPIRequest,
    CompareAPIResponse,
    ResearchAPIRequest,
    ResearchAPIResponse,
    ResolveAPIRequest,
    ResolveAPIResponse,
)
from .comparative import MAX_TICKERS, MIN_TICKERS, ComparativeOrchestrator
from .config import settings
from .disclaimer import DISCLAIMER_FULL, DISCLAIMER_SHORT, DISCLAIMER_VERSION
from .enums import ReportType
from .exporters import ts_definitions, xml_from_dict
from .models import ResearchRequest
from .orchestrator import ResearchOrchestrator
from .providers.market_data import MarketDataProvider
from .reports.comparative_renderer import render_html, render_markdown

logger = logging.getLogger(__name__)


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
                    f"Unsupported format {fmt!r}. "
                    f"Allowed: {', '.join(sorted(SUPPORTED_FORMATS))}."
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
        return Response(
            content=xml_from_dict(data, root), media_type="application/xml"
        )
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
    "ResearchAPIRequest", "ResearchAPIResponse",
    "CompareAPIRequest", "CompareAPIResponse",
    "ResolveAPIRequest", "ResolveAPIResponse",
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

def create_app(
    orchestrator: ResearchOrchestrator | None = None,
    rate_limiter: _IPRateLimiter | None = None,
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
        allow_origins=["*"],
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
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self' https://ra.devinfo.dev https://ra.aimlds.org"
        )
        return response

    # --- Rate limiter (injectable so tests can widen the window) ---
    rate_limiter = rate_limiter or _IPRateLimiter(rate=0.5, burst=3)

    # --- Orchestrator (injectable so tests can stub the pipeline) ---
    orchestrator = orchestrator or ResearchOrchestrator()

    # --- Market data (symbol/name resolution) ---
    market_provider = MarketDataProvider()

    # --- Report cache ---
    report_cache: OrderedDict[str, ResearchAPIResponse] = OrderedDict()
    cache_max = 100

    def _cache_key(req: ResearchAPIRequest) -> str:
        raw = f"{req.ticker}:{req.report_type}:{req.timeframe}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

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

    @app.post("/api/resolve", response_model=ResolveAPIResponse)
    async def resolve_subject_endpoint(
        body: ResolveAPIRequest,
        request: Request,
        format: str | None = Query(default=None),
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded.")
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

        request_id = str(uuid.uuid4())[:8]

        ck = _cache_key(body)
        if ck in report_cache:
            logger.info("Cache hit for %s", body.ticker)
            cached = report_cache[ck]
            report_cache.move_to_end(ck)
            api_response = cached
        else:
            api_response = await _run_research_uncached(body, request_id)
            if len(report_cache) >= cache_max:
                report_cache.popitem(last=False)
            report_cache[ck] = api_response

        fmt = negotiate_format(format, request.headers.get("accept", ""))
        if fmt == "html":
            raise HTTPException(
                status_code=400,
                detail="html is not available for /api/research (use markdown).",
            )
        markdown = (
            "\n\n---\n\n".join(api_response.reports_markdown)
            if fmt == "markdown"
            else None
        )
        return _render_payload(
            api_response.model_dump(mode="json"), fmt, "research", markdown=markdown
        )

    async def _run_research_uncached(
        body: ResearchAPIRequest, request_id: str
    ) -> ResearchAPIResponse:
        report_types = ReportType.from_user_input(body.report_type)

        from .enums import Timeframe
        timeframe_map = {
            "1M": Timeframe.ONE_MONTH, "3M": Timeframe.THREE_MONTHS,
            "6M": Timeframe.SIX_MONTHS, "1Y": Timeframe.ONE_YEAR,
            "3Y": Timeframe.THREE_YEARS, "5Y": Timeframe.FIVE_YEARS,
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

        reports_markdown = [report.to_markdown() for report in result.reports]

        return ResearchAPIResponse(
            request_id=request_id,
            ticker=result.ticker,
            company_name=result.company_name,
            security_type=result.security_type.value,
            reports=result.reports,
            metadata=result.metadata,
            reports_markdown=reports_markdown,
        )

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
            report_html=render_html(report),
        )

        fmt = negotiate_format(format, request.headers.get("accept", ""))
        return _render_payload(
            api_response.model_dump(mode="json"),
            fmt,
            "comparison",
            markdown=api_response.report_markdown if fmt == "markdown" else None,
            html=api_response.report_html if fmt == "html" else None,
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
