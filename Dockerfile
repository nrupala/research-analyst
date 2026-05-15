# ============================================================
# Research Analyst — Multi-stage production Docker build
#
# Stage 1: Install Python dependencies (cached layer)
# Stage 2: Copy application code + UI assets
# Result:  Minimal image, no dev deps, non-root user
#
# Build:   docker build -t research-analyst .
# Run:     docker run -p 8700:8700 research-analyst
# ============================================================

# --- Stage 1: Dependencies ---
FROM python:3.11-slim AS deps

WORKDIR /build

# System deps for numpy/scipy wheel building (if needed)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# --- Stage 2: Application ---
FROM python:3.11-slim AS runtime

# Security: non-root user
RUN groupadd -r analyst && useradd -r -g analyst -d /app -s /sbin/nologin analyst

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application code
COPY research_analyst/ ./research_analyst/
COPY ui/ ./ui/
COPY pyproject.toml README.md LICENSE ./

# Create cache and output directories
RUN mkdir -p /app/.cache/market_data /app/output && \
    chown -R analyst:analyst /app

# Switch to non-root
USER analyst

# Environment
ENV RA_SERVER_HOST=0.0.0.0 \
    RA_SERVER_PORT=8700 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8700

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8700/api/health')" || exit 1

ENTRYPOINT ["research-analyst"]
CMD ["serve"]
