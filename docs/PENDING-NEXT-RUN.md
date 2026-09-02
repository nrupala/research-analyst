# Research Analyst — Pending Tasks (next run)

Durable handoff log. Each item has an owner, a status, and a verifiable exit
condition. Append-only: completed items move to the section below, never
deleted. **Session closed:** 2026-09-02 (roadmap P1–P9 complete).

---

## Open items

### 1. Activate paid keys (monetization go-live)
- **Owner:** user decision (then operator on box)
- **What:** set `RA_BILLING_PAID_KEYS=<key1,key2>` in `/etc/research-analyst/ra.env`
  (mint keys with `research-analyst billing generate-key`), restart `ra`.
  The `/api/research/data` endpoint + UI button switch from OPEN to key-gated.
- **Exit:** `billing list-keys` shows N keys; a request without `X-RA-Key` → 401.

### 2. Live-test the UI source-data download flow on ra.devinfo.dev
- **Owner:** agent (puppeteer) — was built + unit-tested, not yet clicked live
- **What:** run a report → click "Download data (CSV/JSON)" → confirm JSON
  downloads; then `?format=csv` variant; 401→prompt→retry path with a test key.
- **Exit:** both formats download correct content in the browser.

### 3. Native verify on a real macOS / Windows host
- **Owner:** when a host is available
- **What:** `bash deploy/native/verify/verify.sh` (macOS launchd) and the NSSM
  steps in `deploy/native/windows/README.md`; fix whatever surfaces.
- **Exit:** health + research + formats + schema-export pass on each OS.

### 4. Dormant second mdToHTML in ui/worker.js (Milo-flagged)
- **Owner:** next build when worker.js is touched
- **What:** `ui/worker.js` has an older mdToHTML with no chart-preserve
  mechanism — if ever wired to chart reports it reintroduces the truncation
  bug class (#46/#47 guarded the main path only).
- **Exit:** worker.js mdToHTML either removed or brought under the preserve
  contract + a headless test.

### 5. Cloudflare proxy Worker drift (KNOWN GAP — oci-native README §KNOWN GAP)
- **Owner:** agent + user (dashboard access for read of live code)
- **What:** live `research-analyst-api` Worker (route `ra.devinfo.dev/api/*`)
  was last edited in the CF dashboard; body hardcodes the Fly URL and is not
  mirrored in `workers/api-proxy/`. Drift-cleanup: copy live code → make
  env-driven (`env.BACKEND_PRIMARY || default`) → fix wrangler.toml name +
  AI binding → deploy via wrangler so cutovers are config-only.
- **Exit:** repo `workers/api-proxy/` == live worker; env-driven backends.

### 6. thinkwithfinance crossref content (Milo/content side)
- **Owner:** Milo/content team; RA side is done (12-topic `_SECTION_TOPICS` +
  additive `crossref_index.json` load — links appear when paths exist)
- **What:** publish articles; add paths to `crossref_index.json`
  (`settings.market.cache_dir/crossref_index.json` or in-code defaults).
- **Exit:** a live report shows "Learn more — thinkwithfinance" links per
  section that resolve to real articles.

### 7. Full tier gating beyond source-data (P8 completion)
- **Owner:** next monetization build
- **What:** MONETIZATION.md maps Free (single-ticker/MD/rate-limited) vs Pro
  (compare, intl, HTML/PDF, typed exports) vs Advisor/Enterprise (white-label,
  keys, volume, lenses). Today only source-data is gated. Add per-entitlement
  checks (compare/intl/PDF) keyed off the same X-RA-Key list.
- **Exit:** tier matrix enforced per endpoint; docs updated.

### 8. Install the nightly sync timer on the box
- **Owner:** agent (box)
- **What:** `deploy/native/sync-schedulers.txt` documents the systemd timer;
  the box does not run it yet. Create watchlist + enable `ra-sync.timer`.
- **Exit:** `systemctl list-timers` shows ra-sync; bundles appear in /data.

### 9. Next release cut (versioning discipline)
- **Owner:** agent per VERSIONING.md
- **What:** when the next feature batch lands, run
  `node scripts/bump-version.mjs <X.Y.Z>` → PR → tag → GitHub Release
  (v0.4.0 is current; pyproject/__version__/package.json/footer/manifest/SW
  all stamp together — Python side fixed this session).
- **Exit:** API `/api/health` version == tag == package.json.

---

## Completed (this session — context for continuity)

- P1 typed exports · P2 sync CLI · P3 presentation (SVG/D2, no Plotly/Mermaid
  client JS) · P4 education · P5 7 lenses · P6 TUI · P7 native packaging ·
  P8 billing keys + paid data · P9 distribution/docs
- v0.4.0 released (tag + GitHub Release + box deploy); health endpoint added
- Docker artifacts purged repo-wide (no-Docker standing rule)
- Interactive chart views (lazy Plotly modal), collapsible sections, clickable
  crossref links, humanized tabs, empty-state
- Box: MPLCONFIGDIR set; llama.cpp + d2 + matplotlib installed; all 12 services
  green; box HEAD == origin/main
- oc-bridge/opencode infra: gh wired with Aetheris PAT; OpenRouter key → env

## Standing rules (unchanged)
No Docker · phased-delivery (branch + PR, tests gate CI) · educational-only
framing · no secrets in repo · decision log appended every session ·
registries consulted before new code.