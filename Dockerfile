# ============================================================
# Research Analyst - Multi-stage production Docker build
#
# Stage 1: Install Python dependencies (cached layer)
# Stage 2: Copy app code, set PYTHONPATH, run uvicorn directly
# Result:  Minimal image, non-root user, works on Fly.io + Render + OCI
#
# Build:   docker build -t research-analyst .
# Run:     docker run -p 8700:8700 research-analyst
# ============================================================

# --- Stage 1: Dependencies ---
FROM python:3.11-slim AS deps

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Install all runtime dependencies (no package install, just deps)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "pydantic>=2.7" \
    "pydantic-settings>=2.3" \
    "httpx>=0.27" \
    "yfinance>=0.2.40" \
    "pandas>=2.2" \
    "numpy>=1.26" \
    "scipy>=1.12" \
    "plotly>=5.22" \
    "jinja2>=3.1" \
    "python-dateutil>=2.9" \
    "aiofiles>=24.1" \
    "beautifulsoup4>=4.12" \
    "lxml>=5.2"

# --- Stage 2: Application ---
FROM python:3.11-slim AS runtime

RUN groupadd -r analyst && useradd -r -g analyst -d /app -s /sbin/nologin analyst

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application code
COPY research_analyst/ ./research_analyst/
COPY ui/ ./ui/
COPY pyproject.toml README.md LICENSE ./

# Create cache and output directories writable by non-root user
RUN mkdir -p /app/.cache/market_data /app/output && \
    chown -R analyst:analyst /app

USER analyst

# PYTHONPATH ensures 'import research_analyst' works from /app
# No pip install needed - the source is right here
ENV PYTHONPATH=/app \
    RA_SERVER_HOST=0.0.0.0 \
    RA_SERVER_PORT=8700 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8700

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8700/api/health')" || exit 1

# Run uvicorn directly - no entry point scripts, no pip install, no editable mode
# This is the most reliable approach across all hosting platforms
CMD ["python", "-m", "uvicorn", "research_analyst.server:app", "--host", "0.0.0.0", "--port", "8700"]
