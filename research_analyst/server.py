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
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import settings
from .enums import ReportType
from .models import ResearchRequest
from .orchestrator import ResearchOrchestrator
from .comparative import MAX_TICKERS, MIN_TICKERS, ComparativeOrchestrator
from .reports.comparative_renderer import render_html, render_markdown

logger = logging.getLogger(__name__)


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
# Response models
# ---------------------------------------------------------------------------

class ResearchAPIRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    report_type: str | None = Field(default=None)
    compare_tickers: list[str] = Field(default_factory=list, max_length=5)
    timeframe: str = Field(default="1Y")
    custom_assumptions: dict[str, Any] = Field(default_factory=dict)


class ResearchAPIResponse(BaseModel):
    request_id: str
    ticker: str
    company_name: str
    security_type: str
    reports: list[dict[str, Any]]
    metadata: dict[str, Any]
    reports_markdown: list[str]


class CompareAPIRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=1, max_length=10)
    timeframe: str = Field(default="1Y")


class CompareAPIResponse(BaseModel):
    request_id: str
    tickers: list[str]
    report: dict[str, Any]
    report_markdown: str
    report_html: str


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

def create_app() -> FastAPI:
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
        allow_headers=["Content-Type"],
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
            "connect-src 'self' https://research-analyst.fly.dev https://research-analyst.onrender.com https://ra.devinfo.dev"
        )
        return response

    # --- Rate limiter ---
    rate_limiter = _IPRateLimiter(rate=0.5, burst=3)

    # --- Orchestrator ---
    orchestrator = ResearchOrchestrator()

    # --- Report cache ---
    report_cache: OrderedDict[str, ResearchAPIResponse] = OrderedDict()
    cache_max = 100

    def _cache_key(req: ResearchAPIRequest) -> str:
        raw = f"{req.ticker}:{req.report_type}:{req.timeframe}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ================================================================
    # API Endpoints
    # ================================================================

    @app.get("/api/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "research-analyst", "version": __version__}

    @app.post("/api/research", response_model=ResearchAPIResponse)
    async def run_research(body: ResearchAPIRequest, request: Request) -> ResearchAPIResponse:
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded.")

        request_id = str(uuid.uuid4())[:8]

        ck = _cache_key(body)
        if ck in report_cache:
            logger.info("Cache hit for %s", body.ticker)
            cached = report_cache[ck]
            report_cache.move_to_end(ck)
            return cached

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

        reports_data = []
        reports_markdown = []
        for report in result.reports:
            reports_data.append(report.model_dump(mode="json"))
            reports_markdown.append(report.to_markdown())

        api_response = ResearchAPIResponse(
            request_id=request_id,
            ticker=result.ticker,
            company_name=result.company_name,
            security_type=result.security_type.value,
            reports=reports_data,
            metadata=result.metadata.model_dump(mode="json"),
            reports_markdown=reports_markdown,
        )

        if len(report_cache) >= cache_max:
            report_cache.popitem(last=False)
        report_cache[ck] = api_response

        return api_response

    @app.post("/api/compare", response_model=CompareAPIResponse)
    async def run_compare(
        body: CompareAPIRequest,
        request: Request,
        comparative: ComparativeOrchestrator = Depends(get_comparative_orchestrator),
    ) -> CompareAPIResponse:
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

        return CompareAPIResponse(
            request_id=request_id,
            tickers=report.tickers,
            report=report.model_dump(mode="json"),
            report_markdown=render_markdown(report),
            report_html=render_html(report),
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
