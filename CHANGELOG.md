# Changelog

All notable changes to Research Analyst are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses [Semantic Versioning](https://semver.org/).
Releases are cut by tagging the repo (see `docs/VERSIONING.md`); GitHub auto-generates the per-release notes from merged PRs.

## [Unreleased]

## [0.4.0] - 2026-09-02
### Added
- **Typed export layer (Phase 1):** machine-consumable payloads — JSON Schema (draft 2020-12, `$id`-versioned) + TypeScript `.d.ts` + XML per endpoint; `?format=json|xml|markdown|html|ts` + Accept-header negotiation on `/api/research`, `/api/compare`, `/api/resolve`; `schema_version` on every response; `research-analyst schema-export` CLI writes the artifacts. (PR #40)
- **thinkwithfinance cross-references:** per-section explainer links — every 7-step section maps to a fixed article topic (the report format is fixed, so the article set is fixed); links render only when content ships (`crossref_index.json` additive load, no code release needed); 12-topic index with shipped default paths. (PRs #41, #43, #44)
- **Presentation overhaul (server-rendered graphics):** Plotly + Mermaid client libraries dropped — charts now render server-side as static, fluid SVG via matplotlib (institutional theme: navy/steel/green/amber/violet; financial trends, scenario range bars, peer comparison, risk heatmap, dividend history) and diagrams via D2 (business model, capital allocation, decision framework). Zero chart/diagram JavaScript on the page — ~30x faster load (~97ms), no layout instability, crisp vector in print/PDF. (PRs #53–#56)
- **On-demand interactive chart views:** each chart keeps a lazy "Interactive view ↗" button — Plotly loads only on click (modal); the main page stays zero-JS. (PR #57)
- **Collapsible report sections:** each step is a `<details>` card (open by default; beforeprint + export force-open) — analyst-grade navigation. (PR #50)
- **Clickable markdown links** in the report renderer (`[text](url)` → `<a>`, thinkwithfinance crossrefs now link out). (PR #49)
- **UI polish batch:** chart cards + print pagination + anchor scroll margins (PR #51); humanized report tabs, mobile tab scroll, styled empty-state (PR #52); fluid tables (`.table-scroll`) matching the top-menu breakpoint (PR #41).
- **Enterprise embedding roadmap** (9 phases, no-Docker native packaging, monetization incl. paid source-data download). (PRs #39, #58)
### Fixed
- **Plotly charts dead on ra.devinfo.dev** — the `data-plotly` attribute was single-quoted and the JSON carried literal quotes (font family), truncating the payload ("Unterminated string"); base64-encoded + then fully replaced by server-rendered SVG. (PRs #48, #53)
- **Report truncation after Step 2** — the chart-preserve regex in `mdToHTML` dropped sections after `<extra>`-bearing charts (Milo #45/#46/#47) and the mermaid init race (#42); now guarded by 6 headless UI test suites in CI.
- **Disclaimer gate dead button** — box API was behind the UI; `/api/disclaimer` endpoint + box deploy resolved it; gate made dismissible + app.js loaded reliably. (PR #45)
- **Version drift on the Python side** — `bump-version.mjs` now stamps `pyproject.toml` + `research_analyst/__init__.py` (`__version__`), so the API version always matches the release tag. (this release)
### CI
- Six headless UI test suites now gate on `ubuntu-latest` (chart preservation, markdown links, collapsible sections, compare, disclaimer gate, tabs+empty-state, interactive charts). (PRs #47, #49, #50, #52, #57)

## [0.3.0] - 2026-08-27
### Added
- First-use disclaimer acknowledgment gate in the UI: on first load fetches `GET /api/disclaimer` and shows the full disclaimer; acknowledgment persists in `localStorage` (`ra_disclaimer_ack`) per version. Fail-open on error, fail-safe `hidden` baseline. (PR #35)
- `GET /api/disclaimer` endpoint returning `{version, full, short}`. (PR #34)
- India ticker resolver: curated NSE alias map resolved first (e.g. `ICICI -> ICICIBANK.NS`) plus a safe "did you mean `X.NS`?" suggestion for bare, suffix-less symbols that return no search match. (PR #34)
### Fixed
- Report disclaimers unified to a single source of truth (`research_analyst/disclaimer.py`); generic, non-jurisdiction copy across text/markdown/HTML. (PR #34)
- Markdown reports rendered a `**Disclaimer:**` header with an empty body; the body now renders from the single source. (PR #34)
### CI
- Headless UI tests now gate on `ubuntu-latest`: `ui/tests/compare.test.mjs` and the new `ui/tests/disclaimer_gate.test.mjs`.

## [0.2.2] - 2026-08-11
### Added
- Standardized version automation: a single-source version bump (`scripts/bump-version.mjs`) propagates one version across `package.json`, the on-page footer, the PWA manifest, and the service-worker cache; CI stamps Android `versionName`/`versionCode` (and iOS `CFBundleShortVersionString`/`CFBundleVersion` when present) from the release tag (`scripts/stamp-app-version.sh`). Full standard in `docs/VERSIONING.md`.
- Fluid, resolution-aware UI sizing and crisper responsive Plotly charts + Mermaid diagrams (PR #20).

## [0.2.1]
Baseline: institutional research UI (single + comparative modes), Markdown/HTML/PDF export, installable offline-capable PWA, Android APK (Capacitor WebView), and the aimlds.org mirror.
