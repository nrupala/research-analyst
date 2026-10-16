<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Changelog

All notable changes to Research Analyst are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses [Semantic Versioning](https://semver.org/).
Releases are cut by tagging the repo (see `docs/VERSIONING.md`); GitHub auto-generates the per-release notes from merged PRs.

## [Unreleased]
### Removed
- **Paid source-data download retired (owner ruling, 2026-10-15).** `POST /api/research/data`, the `source.data` entitlement, the TWF bundle's source-data unlock, the web UI's *Download data* button, and the bundle exporter (`research_analyst/data_export.py`) are removed. Data RA consumes under license is never sold or redistributed in any format; the paid API sells metered access to RA's own analysis only. The TWF Pro bundle now unlocks RA Pro + `api.access`.

### Changed
- **License split (owner decision, 2026-10-11).** The repo's uniform AGPL-3.0 is restructured into a component split: the core engine (`research_analyst/`, `quant/`, engine tests) stays AGPL-3.0, while scaffolding (`deploy/`, `scripts/`, CI, docs) and the UI (`ui/`) move to Apache 2.0. Root `LICENSE` is now a pointer; the full AGPL text — with the project's no-financial-advice additional notice — is preserved verbatim at `LICENSES/AGPL-3.0.txt`, and the Apache text sits at `LICENSES/Apache-2.0.txt`. Commercial licensing still covers the core (see `COMMERCIAL-LICENSE.md`). Source-file header realignment to the split follows in a separate pass.

- **License boundary clarification (owner, 2026-10-11).** The TUI (`research_analyst/tui.py`, `tui_app.py`) and the core — including reports and their templates (`research_analyst/reports/`) — are confirmed AGPL-3.0. HTML code and web layout are Apache 2.0 wherever they live; a full-tree scan confirms every standalone HTML/CSS file already sits under `ui/`, so no file changes license under this clarification. HTML embedded as strings inside code files stays under the containing code's license.

- **Source-header realignment to the license split.** Per-file headers now state the license of the component they sit in. The 27 files on the Apache side of the split (`ui/` incl. `ui/tests/`, `scripts/`, `deploy/`, `workers/api-proxy/`, `workers/backup-cron/`, `capacitor.config.js`) that still carried AGPL-3.0 headers now carry Apache-2.0 headers in the same block format; the AGPL-only commercial-license sentence is dropped from those files, as the commercial license covers the AGPL core. Headers were added to the two headerless files whose sibling files carry them: `tests/test_provider_quant_fields.py` (AGPL-3.0) and `quant/vitest.config.ts` (AGPL-3.0). Left without headers, following the repo's existing convention (no same-type sibling carries one): the workflow/config YAML files and `ui/style.css`. No code changed.

### Added
- **Portfolio certification rollout (PR-flow + signed deploys + ASF docs + license, 2026-10-05).** `CONTRIBUTING.md` now states the standing PR-flow discipline (no direct pushes to `main`; draft PR → checks green → owner merges; CHANGELOG entry under Unreleased + semver bump per PR; releases tagged `vX.Y.Z`). Version bumped 0.4.0 → 0.4.1 (patch, chore) in `pyproject.toml` and `package.json`. New `NOTICE.md` attribution file. New `deploy/deploy-workers-signed.py` gives the two Cloudflare Workers (`research-analyst-api`, `backup-cron`) a signed manual-deploy path via the site-integrity signed-deploy wrapper — added, not behavior-verified.

### Fixed
- **Forensics on `/api/research/quant` was hollow for real tickers.** 16 `missing_inputs` on first release — `interest_expense`/`tax_expense` were fetched by no provider, and all six Altman Z fields plus all five Beneish-M inputs were unpopulated, so Altman Z, Beneish M and `allocation.incremental_roic` could not compute on shipped data. The yfinance (primary) and SEC EDGAR companyfacts (fallback) providers now map every missing engine input — `ebit`, interest/tax/SGA/EBITDA-D&A, current assets/liabilities, retained earnings, net PP&E, receivables, shares outstanding (basic and diluted) — with a single-fetch companyfacts cache on the SEC path. Expense lines are normalized to positive magnitudes at the provider boundary so both providers agree with the engine's `StatementSeries` contract. No value is ever fabricated: any key still absent from both providers is disclosed by name in `missing_inputs` (e.g. `altman_z: price` when no price is available).
- **The quant section's missing-inputs line named the same key twice instead of listing each unpopulated input.** The adapter now reports exactly which engine key (e.g. `interest_expense`, `shares_outstanding`, `price`) has no data, one entry per key.

- **Paid source-data bundle exported real values as `null`.** Three separate causes, all verified against a real downloaded bundle (META, 2026-09-27):
  - `metrics.payout_ratio` was read from a `DividendAnalysis` field that does not exist, so it could only ever be `null`. The real values — `payout_ratio_eps` and `payout_ratio_fcf` — were computed and already visible in the report table, but never exported. Both are now emitted. There is deliberately no combined `payout_ratio`: the two figures are on different bases and collapsing them hides which one produced the number.
  - `metrics.fcf_deployment` read `capex_pct` / `buyback_pct` / `dividend_pct`; the model fields are `capex_pct_of_fcf` / `buyback_pct_of_fcf` / `dividend_pct_of_fcf`. All three sub-keys were permanently `null`.
  - Each scenario's P/E and EV/EBITDA multiples were computed correctly, then discarded by the engine (`pe_multiple=None  # Set in assumptions`) and exported as `null`. The applied multiples are now published on the model, so the export, the HTML report and the SVG chart all read the same number instead of only narrating it in prose. Each scenario also exports its `assumptions` array, so provenance travels with the number.
- **`metrics` were last-report-wins while `tables` accumulated.** On any multi-report request a later sparse report erased metrics an earlier one computed — `risk_score` disappeared while the risk table remained. Metrics now merge with an explicit precedence rule (a populated value is never overwritten by a null), documented in the API reference and covered by tests.
- **`scenarios` and `peers` were duplicated once per report.** Both are now deduplicated by scenario type and ticker respectively.
- **Peer names were truncated to 20 characters, and the truncation reached the customer.** The export re-parses the rendered markdown table, so `Charter Communicatio` shipped in the paid CSV. Full names now render, and the table gained a `Div Yield` column.
- **`peer_median_yield` was never exported at all.** It is now emitted, together with `peer_yields` (per-peer trailing yields). The median is computed over the whole competitor universe, which is a different population from the eight exported peer rows, so without the per-peer values the figure could not be reproduced or checked by the customer.
- **The in-progress dividend year shipped unmarked.** `annual_dividends` mixed a part-year total (2026: 1.575) in with completed years. It is now split into `annual_dividends_complete_years` and `annual_dividends_partial`, and the report caption states that the current year is partial and excluded from growth rates.
- **A financial period with no data rendered as an all-`N/A` column**, reading as a data outage. All-null periods are now excluded, and the caption names each omitted period and why — silently dropping a year would be its own form of dishonesty.
- **The `vs 10Y Treasury` row conflated two different numbers.** Its value was the *Treasury's* own yield under a label that invites reading it as the company's. The arithmetic was always correct and is unchanged; it is now split into a `10Y Treasury Yield` level row and a signed `Spread vs 10Y Treasury` row, and the caption identifies the benchmark explicitly. During verification the first implementation of the split was caught printing `-490 bps (0.28% below 10Y)` — the parenthetical used the company's yield instead of the spread magnitude, re-creating the very conflation being removed, and crashing when a yield was absent but a spread present. Both are fixed and pinned by tests.
- **A non-positive peer P/E rendered as a plain number** (e.g. `-45.0x`), inviting the reader to treat a symptom of negative earnings as an extreme valuation. Non-positive P/E now renders `n/m`, and the caption states the count and that those values are excluded from peer-multiple medians.
- **`peer_yields` keys shipped markdown emphasis.** The peer table bolds the ticker (`| **VZ** |`) and the exporter stripped only the leading `*` run, so the paid bundle exposed `"VZ**"` as a programmatic dict key (and used the same polluted string for peer dedupe across reports). Found by inspecting the live Aetheris download, not by the unit tests: the fixture already contained `| **CHTR** |` rows, but no test asserted on the *keys*. Emphasis is now stripped from both ends, and two tests pin it - one asserting clean keys, one asserting each yield matches the `Div Yield` cell of the row it is keyed by.
- **`1 yrs`** grammar in the dividend summary (`Consecutive Increases`).

### Changed
- **`/api/health` now returns a `commit` field** — the exact build being served (`RA_BUILD_COMMIT` env when set, else the repo `git rev-parse --short HEAD` at the served source path, `"unknown"` as a documented fallback). The `version` string stays `0.4.0`, so this is a deterministic deploy marker rather than a version bump; health-gated deploys can assert the served SHA matches the box `git HEAD`.
- **`/api/research/data` bundle `schema_version` is now `1.1`** (was `1.0`). Removing `metrics.payout_ratio` is a breaking key change; a deprecation path was considered and rejected — see the note below.
- **`risk_score: null` is now accompanied by `risk_score_note`.** The null itself is unchanged and correct: no score is published when no material risks are identified, because a 1–10 composite over an empty risk set would be arbitrary. The note states the reason instead of leaving a bare null.
- ASFQC gate compliance is now tracked in-repo: `ASFQC/GATES.md`, with `BUILD_PLAN.md` and `DEVELOPMENT_PROGRESS_TRACKER.md`. G4 (Contribution docs) is recorded **FAIL** — `CODE_OF_CONDUCT.md` is missing and is an owner decision, not something to author unilaterally. G9 (documentation) is recorded NOT-STARTED.

### Added
- **SEC provider mappings for every quant engine input** (`research_analyst/providers/sec_edgar.py`): 11 new `CompanyFacts` concepts (shares outstanding, EBIT, interest expense, income tax, SGA, D&A, retained earnings, current assets/liabilities, net PP&E, receivables) plus an `ebit` fallback to `operating_income` when EBIT is not reported as its own line.
- **Step 7 Decision Framework enrichment:** 'How to Read This Framework' description (net assessment with favor/disfavor counts and tilt, strongest factor each side, catalyst role, falsifiability pointer), a server-rendered Thesis Balance SVG, and a near-term vs structural Catalyst Watchlist D2 diagram - in comprehensive, tactical, and long-term Step 7.
- **Business Model Overview enrichment:** full overview block (company description, sector/industry/market-cap/employees, a 'How It Makes Money' economics paragraph from real revenue and margins, and a Unit Economics margin-bars SVG) in comprehensive Step 7; the same unit-economics block added to long-term Step 1. All new content is derived from the report's own data.
- **Bundle schema documented** in `docs/API-REFERENCE.md`: every top-level key, the `metrics` precedence rule, which `null` values are legitimate and why, and the field-name traps (`payout_ratio_eps` vs `_fcf`, complete vs partial dividend years, why `peer_yields` must ship with `peer_median_yield`). The key names were previously undocumented, which is part of why the phantom-key defects survived; two tests now assert the docs and the produced bundle agree.

### Deferred
- Replacing the hardcoded scenario assumption constants (±3pp margin, ×1.2/0.8 multiple) with a data-derived model is **not** in this change. It is gated on the `quant/` Python port so it can reuse the ported `trends` and `sensitivityGrid` rather than being written twice.
- Flagging low-but-positive peer P/E values (e.g. CHTR 2.9x) as outliers is recorded as a design decision, not implemented here. Only non-positive P/E is treated as not-meaningful; a real low multiple stays visible.
- `us_10y_yield` still falls back to a hardcoded `risk_free_rate` rather than a live observation. Presenting a constant as an observation is the same class of problem as the Treasury row, so this needs a provider decision rather than a patch.
- **`scenario.ev_ebitda_multiple` is still `null` for every live ticker checked (AAPL, bull/base/bear).** Publishing the field is correct, but it is only ever populated when `ValuationEngine` reaches `engines/valuation.py:295` (`if ebitda and ebitda > 0 and shares and shares > 0`); when EBITDA or share count is absent from the upstream data the field stays `None` and the EV/EBITDA valuation path is skipped silently. The unit test that covers this key sets `ev_ebitda_multiple=19.1` on a hand-built scenario, so it proves the *export* copies the field but never proves the *engine* fills it - that gap is now known rather than assumed. Root cause needs a data-availability fix, not an export change; tracked as a follow-up.

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
