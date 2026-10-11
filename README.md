<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

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
├── pyproject.toml                 # Project config, dependencies
├── README.md                      # This file
├── deploy/native/                 # Native installs: systemd / launchd / NSSM (no Docker)
├── capacitor.config.ts            # Mobile app (APK/IPA) via Capacitor
├── research_analyst/
│   ├── __init__.py
│   ├── config.py                  # Environment-driven settings (Pydantic)
│   ├── models.py                  # All data models (Pydantic v2, strict typing)
│   ├── enums.py                   # Report types, risk categories, domains
│   ├── cli.py                     # CLI entry (serve / research / sync / tui / billing)
│   ├── server.py                  # FastAPI server (REST API + static UI)
│   ├── orchestrator.py            # Main pipeline (fetch → analyze → render)
│   ├── data_export.py             # Paid source-data bundle (CSV/JSON)
│   ├── sync.py                    # Local-first batch sync (SQLite + NDJSON)
│   ├── tui.py / tui_app.py        # Terminal interface (Textual, keyboard-first)
│   ├── engines/
│   │   ├── lenses/                # 7 mental-model lenses (Graham..Marks, typed)
│   │   ├── fundamental.py         # Growth, margins, balance sheet, earnings quality
│   │   ├── technical.py           # Signal scoring, regime classification
│   │   ├── macro.py               # Regime classification, sector sensitivity mapping
│   │   ├── competitor.py          # Peer ranking, moat indicators, positioning
│   │   ├── valuation.py           # Scenario builder (Bull/Base/Bear)
│   │   └── risk.py                # Structured risk (Prob x Impact x Timing)
│   └── reports/
│       ├── templates.py           # 7-step templates (all 3 modes, verbatim titles)
│       ├── visuals.py             # SVG charts (matplotlib) + D2 diagrams + Markdown tables
│       ├── svg_charts.py          # Server-rendered SVG charts (institutional theme)
│       ├── diagrams.py            # Server-rendered D2 diagrams
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
└── CONTRIBUTING.md
```

### Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Backend** | Python 3.11+, FastAPI, Pydantic v2 | Async, typed, fast serialization |
| **Data** | yfinance, SEC EDGAR (XBRL) | Free, comprehensive, no API keys required |
| **Compute** | NumPy, SciPy, Pandas | O(n) indicator algorithms, financial math |
| **Visuals** | matplotlib SVG + D2 (server-rendered), Markdown tables | Zero chart JS on the page, crisp vector in print/PDF |
| **UI** | Vanilla HTML/CSS/JS | Zero dependencies, instant load, platform agnostic |
| **PWA** | Service worker, manifest.json | Installable, offline shell, mobile-ready |
| **Mobile** | Capacitor (optional) | APK/IPA builds from the same web codebase |
| **Deploy** | Native services (systemd/launchd/NSSM), GitHub Actions | No Docker — OS-native + automated CI/CD |

### Design Principles

1. **Clean code** — type-safe, documented, linted (ruff), tested
2. **Fast execution** — O(n) algorithms, async I/O, parallel data fetching
3. **Error handling** — every external call has retry, timeout, graceful degradation
4. **Security** — input sanitization, rate limiting, CSP headers, no eval()
5. **DSA discipline** — LRU caches (O(1)), token bucket rate limiters, sliding window indicators
6. **Platform agnostic** - browser, mobile (PWA/Capacitor), CLI/TUI, native services

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

# Terminal (keyboard-first TUI) — or headless to stdout
research-analyst tui
research-analyst tui --query AAPL

# Local-first batch sync (SQLite + NDJSON bundles, incremental)
research-analyst sync watchlist.json --out ./data

# Typed schemas (JSON Schema + TypeScript .d.ts)
research-analyst schema-export --out exports/

# Paid API keys (operator)
research-analyst billing generate-key
```

### Run natively (no Docker)

```bash
uvicorn research_analyst.server:app --host 127.0.0.1 --port 8700
# Open http://127.0.0.1:8700
```

Production installs use the OS's native service manager — see
`deploy/native/` (systemd on Linux, launchd on macOS, NSSM on Windows) and
`docs/DISTRIBUTION.md`. **No containers anywhere.**

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

Mixed licensing — see [LICENSE](LICENSE) for the component mapping.
The engine, the TUI, and the core — including reports
(`research_analyst/`, `quant/`, engine tests) — are
**AGPL-3.0** (full text: `LICENSES/AGPL-3.0.txt`). HTML code and web
layout are **Apache 2.0**, as is the scaffolding (`deploy/`,
`scripts/`, CI, docs); every standalone HTML/CSS file lives in the
web/PWA UI (`ui/`) (full text: `LICENSES/Apache-2.0.txt`). A separate
commercial license is available for uses of the core incompatible
with the AGPL-3.0 — see [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

### Open-Core Model

The engine is **open source (AGPL-3.0)** and free: all research reports, the
web/PWA app, CLI, TUI, sync, and typed-export layer are open. Under the
license split, the engine and report pipeline are AGPL-3.0 while the
web/PWA app itself is Apache 2.0 — see [LICENSE](LICENSE).

**Commercial (paid) surfaces** are separate entitlements, not binaries:
- **Source-data downloads** — the raw CSV/JSON bundle behind any report
  (`POST /api/research/data`, X-RA-Key gate) for all paid customers.
- **API keys / higher volume** — per-key entitlements for B2B integration.
- **White-label** — branded reports for advisor/enterprise use.

See `docs/MONETIZATION.md` + `docs/API-REFERENCE.md` for the mapping.
Nothing in the free tier is paywalled; the paid tiers add convenience and
workflow features on top of the same engine.

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). All changes flow through
**feature branches + PRs** (phased-delivery): tests gate CI (pytest + headless
UI suites), no direct-to-main, each PR is revertible.

---

## Author

**Nrupal Akolkar** — nrupalakolkar@gmail.com

---

*Disciplined research. Explicit assumptions. Repeatable methodology.*
