# Research Analyst — Roadmap: Sovereign Intelligence Engine (Enterprise Embedding & Monetization)

> **Source of intent:** `D:\openclawdeploy\Chat on OPENCODE OPENCLAW.docx` (the OpenClaw/OpenCode
> sovereign-ops vision), scoped to **research-analyst only**. Strategic throughline from that
> discussion: RA is not a consumer portal — it is an **embeddable, machine-consumable, sovereign
> intelligence engine** for professionals who value precision, data ownership, and zero telemetry.
>
> **Hard constraint (standing rule): NO Docker.** All packaging uses native OS features —
> Linux systemd + venv (already proven on the Aetheris OCI box), macOS launchd + venv,
> Windows NSSM/venv. Nothing containerized.
>
> **Process (phased-delivery, repo law):** every phase = feature branch + PR, tests gate CI,
> no direct-to-main, no Docker. Each phase has a verifiable exit condition.

---

## 0. Current state (verified at `b75da3d`, v0.3.0+)

| Surface | What exists today |
|---|---|
| API | `GET /api/disclaimer`, `POST /api/resolve`, `POST /api/research`, `POST /api/compare`, static UI |
| Data model | Rich Pydantic: `ResearchResponse`, `FundamentalData`, `TechnicalIndicators`, `ValuationRange`, `DividendAnalysis`, `ETFMetadata`, `ComparativeReport` (~30 typed models) |
| Exports | Markdown (default), JSON via CLI `--json`, HTML/PDF (client-side), `reports_markdown` field |
| CLI | `research-analyst serve / research / resolve / health` |
| Disclaimer | Single-source educational disclaimer (v1), rendered in all formats + UI gate |
| License | AGPL-3.0 (open-core compatible) |
| Deploy | Native systemd + venv on OCI (Aetheris) — **the no-Docker pattern to generalize** |
| Docs | MONETIZATION.md (open-core freemium, gating map, ICP), PACKAGING.md (PWA/Android/iOS) |

**Strategic gap (the ask):** the engine produces human-readable reports but not
machine-consumable, typed, embeddable data; it has no terminal surface; no educational
mental-model layer; no sovereign native packaging beyond the one box; and no revenue gate.

---

## Phase 1 — Typed Export Layer (machine-consumable data)

**Objective:** turn RA from report-generator into an embeddable intelligence engine with
deterministic, typed payloads.

- **1a. JSON Schema artifacts:** emit a canonical JSON Schema per report type
  (`research`, `compare`, `resolve`) from the Pydantic models (`pydantic` → JSON Schema generation).
- **1b. TypeScript definitions:** auto-generate `.d.ts` interfaces from the same Pydantic models
  (one source of truth → `exports/types/` committed + versioned).
- **1c. XML export:** content-negotiated XML rendering (legacy/enterprise ingestion) for the same
  payloads.
- **1d. Content-negotiated API:** `?format=json|ts|xml|markdown|html` on `/api/research`,
  `/api/compare`; `Accept`-header awareness; JSON becomes the canonical wire format (already
  returns typed JSON — formalize schema + versioning: `schema_version` field).
- **1e. End-to-end schema contract tests:** each format renders from the same typed model; JSON
  validates against the published schema; TS defs typecheck (`tsc --noEmit`) against a sample.

**Exit:** `curl /api/research?format=json` returns versioned, schema-valid payload; `.d.ts` +
`.xsd` artifacts committed; CI green.

**Effort:** ~2–3 days. **No new heavy deps** (pydantic + stdlib `xml.etree` + a small TS emit).

---

## Phase 2 — Local-First Sync CLI (sovereign batch export)

**Objective:** a user's local instance can pull fresh structured bundles overnight with zero
cloud telemetry — the "local DuckDB/PostgreSQL sync" ask.

- **2a. `research-analyst sync` command:** fetch/emit structured bundles (JSON or NDJSON) for a
  watchlist → local sink.
- **2b. Sinks:** SQLite (stdlib, zero-dep) first; optional DuckDB/Postgres via documented adapter
  (no new hard dependency).
- **2c. Scheduling hooks:** sample systemd timer / cron / launchd plist / Windows Task Scheduler
  configs (native, no Docker) for `sync` runs.
- **2d. Caching reuse:** reuse the existing `_DiskCache` so overnight syncs are incremental.

**Exit:** `sync --watchlist WATCHLIST.json --out ./data` produces typed bundles; a scheduled
(native timer) run verified on the box; tests cover incremental behavior.

**Effort:** ~1–2 days.

---

## Phase 3 — Presentation Polish (graphs, layouts, tables, exported-matter formatting)

**Objective:** make every surface — web UI, charts, tables, and all exported formats — look
institutional-grade and client-ready. This is what converts a technical engine into something a
boutique advisor or family office will hand to a client; polish is part of the product, not a
nice-to-have.

- **3a. Graph/chart upgrade (VisualEngine + Plotly):**
  - Consistent visual language: one palette, grid, font, and sizing across all charts (price,
    technical, valuation, comparative, ETF).
  - Professional axis/annotation defaults: labeled axes, clear legends, hover templates with
    currency + units, title/subtitle + source line.
  - Responsive sizing for the web UI (fluid, mobile-friendly) — extends the existing
    resolution-aware sizing work.
  - Deterministic theming (no divergent default colors between reports).
- **3b. Table + layout polish (report renderer + templates):**
  - Consistent table styling: header treatment, zebra striping, alignment (right-aligned
    numerics), units in headers (%, $, x).
  - Section layout: stable heading hierarchy, consistent spacing, "Key Metrics Summary"
    block restyle, print/export CSS for HTML/PDF so exports match the web look.
  - Comparative scorecard restyle (peer ranking table) with clear best/worst emphasis.
- **3c. Exported-matter formatting (Markdown/PDF/HTML/JSON):**
  - Publication-grade Markdown: tight tables, proper em-dash/units, consistent number
    formatting via the currency-aware `_fmt_value` path (extend to all metrics).
  - HTML/PDF export: styled CSS (matches UI), page-break rules for print, cover header +
    footer + disclaimer block (single source).
  - JSON: stable key order + pretty-print option; every human-readable surface has a
    corresponding clean machine surface (Phase 1).
- **3d. Consistency regression tests:** golden/snapshot tests for chart configs, table
  structure, and export HTML/CSS so polish doesn't rot; UI smoke tests (existing
  `ui/tests/compare.test.mjs` extended).

**Exit:** a sample report (single + comparative + ETF) renders polished charts/tables in web,
Markdown, HTML, and PDF with consistent styling; snapshot tests green.

**Effort:** ~3–4 days.

---

## Phase 4 — Educational Context Layer ("why this matters")

**Objective:** bridge "here are the numbers" → "here is how to apply them" — the educational
positioning that is also the regulatory shield (existing disclaimer pattern, extended).

- **4a. Context blocks:** per-metric "what it means / what risk it indicates" commentary injected
  into reports (deterministic templates first, model-assisted later).
- **4b. Playbook templates:** structured evaluation walkthroughs (e.g., "evaluate a mid-cap
  Canadian energy asset using debt/equity + FCF bounds") as reusable report sections.
- **4c. thinkwithfinance integration hook:** documented content-pipeline seam (content lives in
  the separate thinkwithfinance site; RA references it) — no coupling.
- **4d. Disclaimer extension:** "educational framework" language consistent with `disclaimer.py`
  (single source), versioned.

**Exit:** sample report shows context blocks + playbook section + extended disclaimer; tests
assert presence + single-source disclaimer.

**Effort:** ~2–3 days.

---

## Phase 5 — Mental-Model Filtration Matrices (original implementations)

**Objective:** the seven established lenses, implemented from first principles (public-domain
methodologies, original code, attribution phrasing — no copied text, no implied endorsement).

| Lens | Metric set (all public-domain math) |
|---|---|
| Graham | Graham Number, NCAV, margin-of-safety checks |
| Greenblatt | Magic Formula: ROIC quality + earnings yield composite |
| Lynch | PEG, GARP buckets (stalwart / fast grower / cyclical) |
| Damodaran | DCF intrinsic value, cost of capital, sanity bounds |
| Buffett | Owner's earnings, moat/quality proxy indicators |
| Dalio | Macro risk-parity framing: regime indicators, allocation levers |
| Marks | Cycle positioning: valuation vs historical extremes, "second-level" flags |

- **5a.** One engine per lens (`research_analyst/engines/lenses/`), pure computation over
  existing typed data (no new data providers).
- **5b.** Lens results as a typed section of `ResearchResponse` (+ JSON/TS/XML automatically via
  Phase 1).
- **5c.** Safe phrasing: every surface says "calculation model based on principles popularized
  by X (public methodology)" — never "endorsed by", never trademarked names as product brands;
  unit-tested copy strings.
- **5d.** Educational-only flag + disclaimer per lens output.

**Exit:** 7 lens engines with unit tests (known-value fixtures), schema-typed outputs, phrasing
tests; reports render lens sections on request.

**Effort:** ~4–6 days (largest phase).

---

## Phase 6 — Terminal Surface (TUI + programmable query)

**Objective:** the Bloomberg-style keyboard-first professional surface.

- **6a. TUI client:** `research-analyst tui` using **Textual** (pure-Python, no Docker, no GUI
  server) — ticker query, report type, compare, exports, lens toggles.
- **6b. Programmable query layer:** stabilize the JSON-RPC-ish subset (resolve/research/compare)
  as a documented query API for scripting (Excel/Python/TS integrations).
- **6c. Auth-optional local mode:** TUI/sync bind to `127.0.0.1` with no secrets by default.

**Exit:** TUI runs locally against the engine (CLI tests via scripted input); query API doc +
smoke tests.

**Effort:** ~3–4 days.

---

## Phase 7 — Sovereign Packaging (native, NO Docker)

**Objective:** one engine, native deployable anywhere — generalizing the proven Aetheris pattern.

- **7a. Linux:** systemd unit + venv install script (exists as `deploy/oci-native/` — promote to a
  generic `deploy/native/linux/` with the same hardening: user, MemoryMax, ProtectSystem).
- **7b. macOS:** launchd plist + venv (user LaunchAgent, `KeepAlive`, logging to `~/Library/Logs`).
- **7c. Windows:** NSSM service wrapper (or `pywin32` service) + venv; documented PowerShell
  install script; `127.0.0.1` bind.
- **7d. Air-gapped profile:** `--offline` mode (disk-cache only, no network providers), the
  sovereign/local-deployment story.
- **7e. Install verification scripts** per OS (health + one research call).

**Exit:** a fresh Ubuntu box, a macOS machine, and a Windows machine each run the engine via
native service with zero Docker; install scripts documented + smoke-tested.

**Effort:** ~3–4 days (Linux mostly done; macOS/Windows new).

---

## Phase 8 — Monetization & Gating (open-core freemium, extended)

**Objective:** revenue without burning runway — extends the existing MONETIZATION.md map.

- **8a. Tier gate:** Free (single-ticker, MD, rate-limited) vs Pro (compare, intl, PDF/HTML,
  typed exports) vs Advisor/Enterprise (white-label, API keys, higher volume, lens suites).
- **8b. API-key auth for B2B:** simple key issuance + per-key entitlements (no full account
  system needed to start); the existing entitlement shadow module gets teeth.
- **8c. Pricing artifacts:** per-seat tiers ($5k–15k/yr enterprise framing per the docx),
  white-label footer option (reuses watermark infra).
- **8d. Compliance:** educational-only framing enforced (disclaimer + "no prescriptive advice"
  copy audit); attribution phrasing audit (Phase 5c).

**Exit:** gated endpoints enforce tier by key; pricing doc updated; compliance copy tests green.

**Effort:** ~3–4 days.

---

## Phase 9 — Distribution & Documentation

**Objective:** make the package discoverable and credible.

- **9a.** Native package listings (Linux repo/apt-style, Homebrew-style formula, Windows
  chocolatey-style) — no container marketplace (no Docker rule).
- **9b.** Open-core README: what's free vs commercial license; contribution guide.
- **9c.** API reference (typed exports, query layer) + integration samples (Python/TS).
- **9d.** Case-study brief template (for the FEED/consulting pitch, referencing RA + bee).

**Exit:** docs complete; package paths documented; repo README updated.

**Effort:** ~2 days.

---

## Sequencing & dependencies

```
P1 (typed exports) ──▶ P2 (sync CLI) ──▶ P5 (lenses, needs typed data)
        │
        ├──▶ P3 (presentation polish) ──▶ P4 (educational) ──▶ P8 (gating builds on P1+P5)
        │
        └──▶ P6 (TUI/query) ──▶ P7 (packaging, independent after P1)
```

Recommended order: **P1 → P3 → P4 → P5 → P2 → P6 → P7 → P8 → P9.** P1 first (everything
machine-facing builds on it); P3 (presentation polish) early because it is client-facing
credibility; P7 is independent and can slot anywhere after P1.

## Cross-cutting

- **No Docker, ever** — native systemd/launchd/NSSM + venv + native schedulers only.
- **Phased-delivery:** branch + PR per phase; tests gate CI; no direct-to-main.
- **Security:** no secrets in repo/env templates; loopback binds for local modes; typed schema
  versioning; no telemetry.
- **Testing:** pytest (existing suite) + schema contract tests + `tsc --noEmit` for TS artifacts +
  snapshot tests for presentation/export formatting.
- **Decision log:** each phase recorded in `conversation_decisions.md` on completion.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Legal (advice-like output) | Educational framing + disclaimer v1 (exists), no prescriptive language, lens attribution phrasing, copy tests |
| Trademark/endorsement | Public-methodology attribution only; never "official/endorsed by" |
| Scope bloat | Each phase is a branch + PR with an exit condition; docx's aspirational items (LF/Microsoft) are explicitly out of scope |
| Revenue gate creep | Start with API keys (8b), not a full account system |
| Presentation rot | Snapshot/golden tests on charts + tables + exports so polish is regression-guarded |