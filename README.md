# Research Analyst

**Institutional-grade equity and ETF research agent with disciplined 7-step methodology.**

Research Analyst is a structured, disciplined research agent designed to generate repeatable, high-quality investment analysis. It synthesizes fundamentals, technicals, macro context, competitor dynamics, and valuation frameworks into clear, actionable research reports.

> **Disclaimer:** This tool is for informational and educational purposes only. It is not financial advice, investment advice, or a recommendation to buy or sell any security. All scenario ranges are assumption-driven illustrations, not predictions.

---

## What It Does

Research Analyst produces **decision-intelligence research** comparable to top-tier sell-side and buy-side analysts (e.g., JPMorgan, BlackRock), using a **disciplined, falsifiable, repeatable methodology**.

### Supported Report Types

| Mode | Description |
|------|-------------|
| **`long_term`** | Deep, structural, timeless analysis — business model, moat, capital allocation, multi-year trajectory |
| **`tactical`** | Short-horizon, market-driven insights — technical setup, catalysts, event risk, positioning |
| **`comprehensive`** | Hybrid long-term + tactical synthesis (default) |

### Key Capabilities

- **SEC EDGAR integration** — XBRL financials, filings search, insider transactions
- **Market data ingestion** — price series, analyst estimates, institutional holdings
- **Technical analysis** — 15+ indicators computed from O(n) algorithms, pattern detection
- **Competitor auto-discovery** — sector ETF-based peer identification and ranking
- **Multi-template report generation** — exact 7-step structure, never reordered or skipped
- **Scenario-based valuation** — Bull / Base / Bear with explicit, spreadsheet-ready assumptions
- **Structured risk mapping** — Probability x Impact x Timing framework, not bullet lists
- **Visual intelligence** — Plotly codegen, Mermaid diagrams, ASCII charts, Markdown tables
- **Variant perception** — consensus vs differentiated view, mandatory in every report

### Research Standards

- Every conclusion traces to **explicit assumptions**
- If data is missing: `"Data not available; assumption used: ..."`
- **No recommendations** — frames outcomes as "favors" / "disfavors"
- **No predictions** — scenario ranges are assumption-driven illustrations
- Mandatory disclaimer on every report
- Output suitable for investment committee review, CIO/PM briefing, internal research memos

---

## Inputs — What to Enter

Research Analyst researches **one subject at a time** — a single stock or ETF. Identify it either way:

### 1. Ticker (canonical)

The unambiguous input. For **US** listings the bare symbol is enough (`AAPL`, `MSFT`, `SPY`). For **non-US** listings, append the exchange suffix (yfinance convention):

| Market | Suffix | Example |
|--------|--------|---------|
| United States | *(none)* | `AAPL` |
| Canada — TSX | `.TO` | `RY.TO` |
| United Kingdom — LSE | `.L` | `SHEL.L` |
| Germany — XETRA | `.DE` | `SAP.DE` |
| France — Euronext Paris | `.PA` | `AIR.PA` |
| Japan — TSE | `.T` | `7203.T` |
| Australia — ASX | `.AX` | `BHP.AX` |
| India — NSE / BSE | `.NS` / `.BO` | `RELIANCE.NS` |
| Hong Kong — HKEX | `.HK` | `0700.HK` |

Reports render in the security's **native currency**, with a USD-equivalent reference for non-USD names.

### 2. Company name (convenience)

Don't know the ticker? Enter a **company name** and Research Analyst resolves it to a listing, echoing exactly which one it used (e.g. `Reliance Industries` → `RELIANCE.NS`, NSE, INR).

Resolution is **safe-confirm**: an unambiguous name resolves automatically, but a name that maps to **multiple listings** (an NSE vs BSE line, or a name shared across companies) returns candidates for you to choose — it never silently guesses, because a correct report on the *wrong* listing is worse than asking.

- **Web UI** — type a name in the search box and confirm the match.
- **CLI** — `research-analyst resolve "Reliance Industries"`
- **API** — `POST /api/resolve {"query": "..."}` → `{ status, resolved, candidates }`

### ETFs

ETFs are valid research subjects, not just peer-discovery tools — enter an ETF ticker (`SPY`, `INDA`, `EWU`) exactly as you would a stock.

---

## Architecture

```
research_analyst/
├── pyproject.toml                 # Project config, dependencies
├── README.md                      # This file
├── Dockerfile                     # Multi-stage production build
├── docker-compose.yml             # One-command local development
├── capacitor.config.ts            # Mobile app (APK/IPA) via Capacitor
├── research_analyst/
│   ├── __init__.py
│   ├── config.py                  # Environment-driven settings (Pydantic)
│   ├── models.py                  # All data models (Pydantic v2, strict typing)
│   ├── enums.py                   # Report types, risk categories, domains
│   ├── cli.py                     # CLI entry point (serve / research / health)
│   ├── server.py                  # FastAPI server (REST API + static UI)
│   ├── orchestrator.py            # Main pipeline (fetch → analyze → render)
│   ├── providers/
│   │   ├── sec_edgar.py           # SEC EDGAR (rate-limited, cached, async)
│   │   ├── market_data.py         # yfinance (threaded, disk-cached)
│   │   └── technical.py           # Technical indicators (pure NumPy, O(n))
│   ├── engines/
│   │   ├── fundamental.py         # Growth, margins, balance sheet, earnings quality
│   │   ├── technical.py           # Signal scoring, regime classification
│   │   ├── macro.py               # Regime classification, sector sensitivity mapping
│   │   ├── competitor.py          # Peer ranking, moat indicators, positioning
│   │   ├── valuation.py           # Scenario builder (Bull/Base/Bear)
│   │   └── risk.py                # Structured risk (Prob x Impact x Timing)
│   └── reports/
│       ├── templates.py           # 7-step templates (all 3 modes, verbatim titles)
│       ├── visuals.py             # Plotly codegen, Mermaid, ASCII, Markdown tables
│       └── renderer.py            # Report assembler (template + analysis → Markdown)
├── ui/
│   ├── index.html                 # Single-page app (vanilla HTML)
│   ├── style.css                  # Institutional styling (CSS custom properties)
│   ├── app.js                     # Frontend logic (vanilla JS, no frameworks)
│   ├── manifest.json              # PWA manifest
│   └── sw.js                      # Service worker (offline shell, CDN caching)
├── tests/
│   └── test_models.py
├── .github/workflows/ci.yml       # GitHub Actions CI/CD
├── .gitignore
├── .editorconfig
├── LICENSE                        # AGPL-3.0
└── CONTRIBUTING.md
```

### Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Backend** | Python 3.11+, FastAPI, Pydantic v2 | Async, typed, fast serialization |
| **Data** | yfinance, SEC EDGAR (XBRL) | Free, comprehensive, no API keys required |
| **Compute** | NumPy, SciPy, Pandas | O(n) indicator algorithms, financial math |
| **Visuals** | Plotly.js, Mermaid.js | Copy-paste-ready charts, syntax-valid diagrams |
| **UI** | Vanilla HTML/CSS/JS | Zero dependencies, instant load, platform agnostic |
| **PWA** | Service worker, manifest.json | Installable, offline shell, mobile-ready |
| **Mobile** | Capacitor (optional) | APK/IPA builds from the same web codebase |
| **Deploy** | Docker, GitHub Actions | One-command deploy, automated CI/CD |

### Design Principles

1. **Clean code** — type-safe, documented, linted (ruff), tested
2. **Fast execution** — O(n) algorithms, async I/O, parallel data fetching
3. **Error handling** — every external call has retry, timeout, graceful degradation
4. **Security** — input sanitization, rate limiting, CSP headers, no eval()
5. **DSA discipline** — LRU caches (O(1)), token bucket rate limiters, sliding window indicators
6. **Platform agnostic** — browser, mobile (PWA/Capacitor), CLI, Docker

---

## Quick Start

### Prerequisites

- Python 3.11+
- pip or uv

### Install

```bash
# Clone
git clone https://github.com/nrupala/research-analyst.git
cd research-analyst

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install
pip install -e ".[dev]"
```

### Run (Web Server)

```bash
research-analyst serve
# Open http://127.0.0.1:8700
```

### Run (CLI)

```bash
# Comprehensive report (default)
research-analyst research AAPL

# All three report types
research-analyst research MSFT --report-type all

# Tactical report with 3-month timeframe
research-analyst research TSLA --report-type tactical --timeframe 3M

# Output to file
research-analyst research GOOG --output goog_report.md

# JSON output
research-analyst research AMZN --json --output amzn.json

# International listing (append the exchange suffix)
research-analyst research RELIANCE.NS

# Don't know the ticker? Resolve a company name first
research-analyst resolve "Reliance Industries"
```

### Run (Docker)

```bash
docker compose up
# Open http://127.0.0.1:8700
```

---

## API

### `POST /api/research`

Run the research pipeline.

**Request:**
```json
{
    "ticker": "AAPL",
    "report_type": "comprehensive",
    "timeframe": "1Y",
    "compare_tickers": [],
    "custom_assumptions": {}
}
```

**`report_type` values:**
- `null` or `""` — comprehensive (default)
- `"long_term"` — long-term report only
- `"tactical"` — tactical report only
- `"all"` — all three reports

**Response:** Structured JSON with `reports` (typed data), `reports_markdown` (rendered Markdown), and `metadata` (data sources, assumptions, processing time, warnings).

### `POST /api/resolve`

Resolve a company name or symbol to a listing (safe-confirm).

**Request:**
```json
{ "query": "Reliance Industries" }
```

**Response:** `{ "query", "status", "resolved", "candidates", "note" }`. `status` is one of `resolved` (use `resolved.symbol`), `ambiguous` (present `candidates` for the user to pick — never auto-selected), or `not_found`.

### `GET /api/health`

Health check. Returns `{"status": "ok"}`.

### `GET /api/docs`

Interactive Swagger UI documentation.

---

## Configuration

All settings are environment-variable driven. No `.env` file required — defaults work out of the box.

| Variable | Default | Description |
|----------|---------|-------------|
| `RA_DEBUG` | `false` | Debug logging |
| `RA_SEC_USER_AGENT` | `ResearchAnalyst/0.1 (...)` | SEC EDGAR User-Agent (required by SEC) |
| `RA_MARKET_CACHE_TTL_SECONDS` | `3600` | Market data cache TTL |
| `RA_ANALYSIS_MC_SIMULATION_PATHS` | `10000` | Monte Carlo paths |
| `RA_SERVER_HOST` | `127.0.0.1` | Server bind host |
| `RA_SERVER_PORT` | `8700` | Server bind port |

---

## PWA & Mobile

### PWA (Progressive Web App)

The browser UI is PWA-ready out of the box:
- Service worker caches static assets for offline shell
- `manifest.json` enables "Add to Home Screen" on mobile
- Responsive layout works on all screen sizes

### APK (Android) via Capacitor

```bash
# Install Capacitor
npm init -y
npm install @capacitor/core @capacitor/cli @capacitor/android

# Initialize
npx cap init "Research Analyst" "com.research.analyst" --web-dir ui

# Add Android platform
npx cap add android

# Sync web assets
npx cap sync android

# Build APK
cd android && ./gradlew assembleDebug
# APK: android/app/build/outputs/apk/debug/app-debug.apk
```

### iOS via Capacitor

```bash
npm install @capacitor/ios
npx cap add ios
npx cap sync ios
npx cap open ios  # Opens Xcode
```

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy research_analyst/

# Format
ruff format .

# Dev server with auto-reload
research-analyst serve --reload --debug
```

---

## License

AGPL-3.0 — See [LICENSE](LICENSE).

---

## Author

**Nrupal Akolkar** — nrupalakolkar@gmail.com

---

*Disciplined research. Explicit assumptions. Repeatable methodology.*
