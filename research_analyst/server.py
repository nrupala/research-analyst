"""FastAPI web server — REST API + static file serving for the browser UI.

Security:
  - CORS restricted to configured origins
  - Input validation via Pydantic (automatic)
  - Rate limiting on research endpoints (simple token bucket)
  - Request size limits enforced by uvicorn
  - No file uploads, no arbitrary code execution
  - All error responses are structured JSON (no stack traces in production)
  - CSP headers to prevent XSS

Endpoints:
  POST /api/research         — Run research pipeline, return structured response
  GET  /api/research/{id}    — Retrieve cached report by ID (future)
  GET  /api/health           — Health check
  GET  /                     — Serve browser UI (static files)
"""
# Module: research_analyst/server.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .enums import ReportType
from .models import ResearchRequest
from .orchestrator import ResearchOrchestrator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiter (per-IP, simple token bucket)
# ---------------------------------------------------------------------------

class _IPRateLimiter:
    """Per-IP rate limiter using token bucket.

    Prevents abuse of the research endpoint which is compute-intensive.
    O(1) per check via dict lookup.
    """

    def __init__(self, rate: float = 2.0, burst: int = 5) -> None:
        self._rate = rate        # tokens per second
        self._burst = burst      # max bucket size
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self._max_ips = 10_000   # Prevent memory exhaustion

    def allow(self, ip: str) -> bool:
        """Check if request from IP is allowed."""
        now = time.monotonic()

        if ip in self._buckets:
            tokens, last = self._buckets[ip]
            elapsed = now - last
            tokens = min(self._burst, tokens + elapsed * self._rate)
            self._buckets.move_to_end(ip)
        else:
            tokens = float(self._burst)
            # Evict oldest if at capacity
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
    """API request model — slightly different from internal ResearchRequest."""

    ticker: str = Field(..., min_length=1, max_length=10, description="Ticker symbol")
    report_type: str | None = Field(
        default=None,
        description="Report type: long_term, tactical, comprehensive, or all. Default: comprehensive.",
    )
    compare_tickers: list[str] = Field(default_factory=list, max_length=5)
    timeframe: str = Field(default="1Y")
    custom_assumptions: dict[str, Any] = Field(default_factory=dict)


class ResearchAPIResponse(BaseModel):
    """Structured API response."""

    request_id: str
    ticker: str
    company_name: str
    security_type: str
    reports: list[dict[str, Any]]
    metadata: dict[str, Any]
    reports_markdown: list[str]  # Pre-rendered Markdown for each report


class ErrorResponse(BaseModel):
    """Structured error response."""

    error: str
    detail: str
    request_id: str = ""


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Research Analyst",
        description=(
            "Institutional-grade equity and ETF research agent. "
            "Produces disciplined, falsifiable, repeatable 7-step research reports."
        ),
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    # --- GZip compression (min 500 bytes) ---
    app.add_middleware(GZipMiddleware, minimum_size=500)

    # --- Security headers middleware ---
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
            "connect-src 'self'"
        )
        return response

    # --- Rate limiter ---
    rate_limiter = _IPRateLimiter(rate=0.5, burst=3)  # Max 3 burst, 0.5/sec sustained

    # --- Orchestrator (singleton for connection pooling) ---
    orchestrator = ResearchOrchestrator()

    # --- Report cache (simple in-memory, keyed by request hash) ---
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
        """Health check endpoint."""
        return {"status": "ok", "service": "research-analyst", "version": "0.1.0"}

    @app.post("/api/research", response_model=ResearchAPIResponse)
    async def run_research(body: ResearchAPIRequest, request: Request) -> ResearchAPIResponse:
        """Run the research pipeline and return structured results.

        Rate limited to prevent abuse. Returns cached results for repeat requests.
        """
        # Rate limit
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Max 3 requests per burst, 1 every 2 seconds sustained.",
            )

        request_id = str(uuid.uuid4())[:8]

        # Check cache
        ck = _cache_key(body)
        if ck in report_cache:
            logger.info("Cache hit for %s", body.ticker)
            cached = report_cache[ck]
            report_cache.move_to_end(ck)
            return cached

        # Parse report types
        report_types = ReportType.from_user_input(body.report_type)

        # Build internal request
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

        # Run pipeline
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

        # Build API response
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

        # Cache
        if len(report_cache) >= cache_max:
            report_cache.popitem(last=False)
        report_cache[ck] = api_response

        return api_response

    # ================================================================
    # Static file serving (browser UI)
    # ================================================================

    ui_dir = settings.server.static_dir

    @app.get("/", response_class=HTMLResponse)
    async def serve_index() -> HTMLResponse:
        """Serve the main UI page."""
        index_path = ui_dir / "index.html"
        if index_path.exists():
            return HTMLResponse(content=index_path.read_text())
        return HTMLResponse(
            content="<h1>Research Analyst</h1><p>UI not found. Place index.html in /ui directory.</p>",
            status_code=200,
        )

    # Mount static files for CSS, JS, manifest, icons
    if ui_dir.exists():
        app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")

    # Service worker must be served from root for PWA scope
    @app.get("/sw.js")
    async def serve_sw() -> FileResponse:
        sw_path = ui_dir / "sw.js"
        if sw_path.exists():
            return FileResponse(str(sw_path), media_type="application/javascript")
        raise HTTPException(status_code=404, detail="Service worker not found")

    @app.get("/manifest.json")
    async def serve_manifest() -> FileResponse:
        manifest_path = ui_dir / "manifest.json"
        if manifest_path.exists():
            return FileResponse(str(manifest_path), media_type="application/json")
        raise HTTPException(status_code=404, detail="Manifest not found")

    return app


# Convenience: create app instance for uvicorn
app = create_app()
