# Changelog

All notable changes to Research Analyst will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.2] - 2026-07-18

### Added

- **Multi-format report export** (browser UI)
  - Export toolbar on every rendered report with three one-click downloads: Markdown (.md), self-contained HTML (.html), and PDF (via the browser print dialog)
  - HTML export is fully self-contained: inlined stylesheet and rendered charts, no external assets and no server round-trip; opens standalone and offline
  - All export generation runs client-side, with zero additional server processing
  - A report footer is appended to every format: "Report prepared on https://ra.devinfo.dev" with the generation date, plus a Buy Me a Coffee link (no page numbers, by design)
  - Buy Me a Coffee link added to the header navigation and the site footer

### Changed

- Service worker CACHE_VERSION bumped from ra-v1 to ra-v2 so returning PWA users receive the updated UI instead of a stale cached shell
- UI footer version label updated to v0.1.2

---

## [0.1.1] - 2026-06-02

### Added

- **Dividend & Yield Analysis** (all three report types)
  - New `DividendEngine` (engines/dividend.py): current (forward) + trailing yield, 1Y / 3Y CAGR / 5Y CAGR dividend growth, payout ratios (dividend / EPS and dividend / FCF), EPS and FCF coverage, consecutive-increase streak and dividend-cut detection, a 0-100 dividend safety score with letter grade, yield vs the 10Y Treasury and vs peer median, a yield attractiveness rating (including a yield-trap screen), and explicit non-payer context (buyback-focused vs growth reinvestment)
  - ETF support: distribution-yield labelling; EPS payout skipped for funds
  - New models: `DividendData`, `DividendPayment`, `DividendAnalysis`; `DividendAnalysis` attached to `ReportOutput` for API consumers
  - `MarketDataProvider.get_dividend_data()` (yfinance `.info` + `.dividends`, disk-cached, graceful); peer `dividend_yield` added to competitor discovery
  - Rendered in Comprehensive (Step 2), Long-Term (Step 4 — Capital Allocation & Shareholder Returns), and Tactical (Step 4, compact/event-focused with ex-dividend date) reports
  - New visuals: dividend & yield summary table + dividend-per-share history bar chart
  - Tests: `tests/test_dividend.py` (offline synthetic fixtures)

### Changed

- The headline yield is now computed in-engine (annual dividend rate / price) rather than trusting yfinance's inconsistently-scaled `dividendYield`; info fields are retained as cross-checks with a normalization guard

---

## [0.1.0] - 2026-05-15

### Added

- **Core Architecture**
  - Pydantic v2 data models with strict typing (models.py)
  - Environment-driven configuration via pydantic-settings (config.py)
  - Enum definitions for report types, risk categories, scenarios (enums.py)

- **Data Providers**
  - SEC EDGAR provider with token bucket rate limiter, LRU CIK cache, XBRL parsing (sec_edgar.py)
  - Market data provider via yfinance with disk-based TTL cache, async threading (market_data.py)
  - Technical indicators provider with 15+ O(n) NumPy algorithms (technical.py)

- **Analysis Engines**
  - Fundamental engine: growth rates, CAGRs, margin trends, balance sheet grading, earnings quality, capital allocation (fundamental.py)
  - Technical engine: composite scoring, regime classification, signal interpretation (technical.py)
  - Macro engine: regime classification, sector sensitivity mapping, second-order effects (macro.py)
  - Competitor engine: auto-discovery via sector ETFs, peer ranking, moat indicators (competitor.py)
  - Valuation engine: Bull/Base/Bear scenario builder with explicit assumptions (valuation.py)
  - Risk engine: structured risk by Probability x Impact x Timing, not bullet lists (risk.py)

- **Report Generation**
  - Three 7-step report templates: long_term, tactical, comprehensive (templates.py)
  - Visual intelligence: Plotly codegen, Mermaid diagrams, ASCII charts, Markdown tables (visuals.py)
  - Full report renderer assembling analysis into structured Markdown (renderer.py)

- **Server & CLI**
  - FastAPI server with CORS, CSP headers, per-IP rate limiting, report caching (server.py)
  - CLI with serve/research/health commands (cli.py)
  - Async orchestrator with parallel data fetching and graceful degradation (orchestrator.py)

- **Browser UI**
  - Vanilla HTML/CSS/JS single-page app with institutional design (ui/)
  - PWA support: service worker, manifest, offline shell caching
  - Mermaid diagram rendering, Plotly code copy-to-clipboard
  - Responsive layout, print styles, accessibility (ARIA, keyboard nav)

- **Infrastructure**
  - Multi-stage Docker build with non-root user (Dockerfile)
  - Docker Compose for local development (docker-compose.yml)
  - GitHub Actions CI/CD: lint, typecheck, test, Docker build + smoke test (ci.yml)
  - Capacitor configuration for APK/IPA mobile builds (capacitor.config.ts)
  - EditorConfig, .gitignore, CONTRIBUTING guide

- **Testing**
  - Model validation test suite covering all core data models (test_models.py)

- **Versioning**
  - Per-file version headers on all 24 Python source files
  - Semantic versioning (SemVer 2.0.0)
  - This CHANGELOG

### Security

- Input sanitization on all external-facing endpoints (ticker validation, regex)
- SEC EDGAR rate limiting (10 req/sec compliance)
- CSP headers preventing XSS
- No eval(), no raw innerHTML with user data
- Non-root Docker user
- CORS restricted to configured origins

---

## [Unreleased]

### Added

- **Multi-ticker comparative reports — backend (v0.2.0, in progress; UI + version bump to follow)**
  - New `ComparativeReport` model and cross-ticker comparison layer (`research_analyst/comparative.py`): runs the existing single-ticker orchestrator once per ticker (2-5 tickers, bounded concurrency, reusing `competitor.py` peer context), aligns the structured metrics across Valuation, Growth & Margins, Profitability & Capital Quality, Dividend & Income, and Risk, and computes a per-metric percentile rank, a min-max normalized 0-100 score, and winner flags, plus an equal-weighted scorecard roll-up
  - `ComparativeOrchestrator`: an invalid or unresolvable ticker is skipped with a recorded error instead of crashing the whole request (no-lockout rule)
  - New `POST /api/compare` route (`server.py`): accepts `{ "tickers": [...] }`, validates 2-5 distinct tickers (clear 400 otherwise), and returns the `ComparativeReport` as JSON plus rendered Markdown and self-contained HTML. Mirrors the `/api/research` conventions (rate limiting, structured JSON errors). The single-ticker `/api/research` path is left completely untouched
  - New comparative renderer (`research_analyst/reports/comparative_renderer.py`): a top scorecard (normalized 0-100 per metric) plus one side-by-side table per dimension, in Markdown and fully self-contained HTML (inline styles, no external assets, opens offline). Every rendered report carries the disclaimer and a compliance line (the tool ranks numbers; the user decides). Framing is "how they rank and what would have to be true," never buy / sell / hold
  - Provenance: every displayed number is traceable to the exact per-ticker report field it was carried from, plus each ticker's declared data sources
  - Tests: `tests/test_comparative.py` — ranking/alignment logic, the `/api/compare` endpoint for 2 and 5 tickers, an invalid ticker in the set (graceful skip), and a non-dividend name in the set
- **Multi-ticker comparative reports — browser UI (v0.2.0, in progress; version bump to follow)**
  - New Single / Compare mode toggle in the request card; the single-ticker `/api/research` flow is left fully intact (its own form, submit button, and render path are unchanged)
  - Compare mode accepts 2-5 tickers (comma- or space-separated, de-duplicated) and validates the count client-side with a clear inline error; no `/api/compare` request is fired on an invalid count (1 or 6+)
  - Calls `POST /api/compare` with `{ tickers, timeframe }` and renders the returned comparative report — top scorecard plus one side-by-side table per dimension — carrying the disclaimer and compliance line
  - Reuses the v0.1.2 export toolbar unchanged (Markdown / self-contained HTML / PDF). The comparative HTML export is self-contained (inlined stylesheet) and carries the same footer, "prepared on https://ra.devinfo.dev", and Buy Me a Coffee link as single-ticker exports (the server markdown's own prepared-on trailer is stripped so the shared UI footer is applied exactly once)
  - Side-by-side tables degrade to horizontal scroll on narrow screens; the mode toggle and compare form reuse the existing responsive patterns
  - Tests: `ui/tests/compare.test.mjs` — headless (Node `vm` + minimal DOM shim, no external deps) coverage of 2- and 5-ticker compare (scorecard + per-dimension tables + 3-button toolbar + self-contained MD/HTML exports), invalid counts (no request fired), and a single-ticker regression
  - Deferred to the full v0.2.0 slice: the package version bump and `sw.js` CACHE_VERSION bump (handled at the gated release/merge step), and structured technical/momentum + macro/sector cross-ticker metrics (still narrative-only in the per-ticker reports)

### Planned

- FRED API integration for official macro data
- Quarterly (10-Q) financial statement support
- Interactive Plotly rendering in browser UI
- Comparative reports UI (multi-ticker input + side-by-side render)
- WebSocket for real-time research progress
- Background task queue for long-running research

---

[0.1.0]: https://github.com/nrupala/research-analyst/releases/tag/v0.1.0
[Unreleased]: https://github.com/nrupala/research-analyst/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/nrupala/research-analyst/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/nrupala/research-analyst/compare/v0.1.0...v0.1.1
