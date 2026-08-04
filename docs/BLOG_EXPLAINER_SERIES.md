# Research Analyst × thinkwithfinance.com — Module Explainer Series (plan)

Following through on the commitment to cross-link **ra.devinfo.dev** with the **thinkwithfinance.com (twf)**
blog: one plain-English explainer post per RA module, bidirectionally linked to the report step it powers.

**Status: PLAN ONLY. Nothing built, nothing published, no links wired.** This doc defines the series,
the mapping, and the linking design for approval. Posts get authored into the twf content queue and the
report links get wired only after sign-off (phased).

## Why do this (three payoffs)
1. **Trust / credibility** — RA makes strong claims (safety scores, moat, scenario valuations). An
   explainer for each shows the method, which is exactly what a paying prosumer/advisor wants to see.
2. **SEO funnel** — each post targets a real search query ("dividend payout ratio", "how to read RSI",
   "yield-curve recession signal") → organic traffic → "run it yourself on RA" CTA.
3. **Monetization top-of-funnel** — the comparative / international / export posts double as soft sells
   for the Pro tier ("this is a Pro feature — here's how it works").

## The mapping — RA engine → report step → twf post

RA ships 7 analytical engines that map onto the 7-step comprehensive report:

| # | RA module (`engines/`) | Report step it powers | Proposed twf post (slug) | Target query / angle |
|---|---|---|---|---|
| 1 | `fundamental.py` | Step 2 — Fundamental Analysis & Financial Trajectory | `quality-of-earnings-reading-the-financials` | margins, ROE/ROIC, revenue growth, D/E, capital allocation |
| 2 | `competitor.py` | Step 3 — Competitive Position & Moat | `moats-and-market-structure` | peer sets, comparable metrics, what a moat is |
| 3 | `technical.py` | Step 4 — Technical Analysis & Price Structure | `reading-price-structure-trend-momentum-volatility` | SMA/EMA, RSI, MACD, Bollinger, ATR/ADX, composite score |
| 4 | `macro.py` | Step 5 — Macro Context & Sector Dynamics | `the-macro-backdrop-cycle-inflation-yield-curve` | CPI, real GDP, HY spread, T10Y2Y, cycle phase (FRED) |
| 5 | `risk.py` | Step 6a — Risk Assessment | `a-risk-map-not-a-risk-list` | probability × impact, duration/nature, categories |
| 6 | `valuation.py` | Step 6b — Scenario-Based Valuation | `scenario-valuation-bull-base-bear` | blended PE, DCF/WACC, terminal growth, scenarios |
| 7 | `dividend.py` | Step 2 / Long-Term Step 4 — Capital Allocation | `reading-the-dividend-payout-ratio` **(already staged)** | payout, EPS/FCF coverage, safety score, yield-trap screen |
| 8 | `comparative.py` | `/api/compare` (Pro) | `comparing-2-to-5-stocks-side-by-side` | comparative scorecard, per-dimension ranking — **Pro hook** |
| 9 | orchestrator / method | Step 1 & 7 — Context → Decision | `the-7-step-research-method` | the umbrella post; links to all others + RA About |
| 10 | `providers/` (SEC EDGAR + market data) | data layer | `where-the-numbers-come-from` | free-first data sourcing, honest degradation — trust post |

Start count: **10 posts**. #7 (dividend) is already in `queue:pending` — it becomes post #1 to publish,
so the series has continuity from what's already staged.

## Bidirectional linking design

**Blog → RA (every post):** close each explainer with a single CTA —
> *"Run this analysis on any ticker → Research Analyst"* linking to `https://ra.devinfo.dev`
(and `https://ra.aimlds.org` once the mirror is live). The umbrella post (#9) links to RA's About panel.

**RA → Blog (in the report):** add an unobtrusive **"ⓘ How this is computed"** link on each report step,
pointing at the matching `https://blog.thinkwithfinance.com/<slug>`. Two implementation options:
- **A (recommended):** a static `STEP_TITLE → learn_more_url` map in `reports/renderer.py` (or a small
  "Learn more" block in the report footer). Box-free UI/backend change, ships via Pages/box redeploy.
- **B (lighter):** a single "How RA works" link in the report meta-bar → the umbrella post, which fans
  out to the per-module posts. Less surface area, easier to keep in sync.

**404 gating:** a report link must never point at an unpublished post. Wire each RA→blog link only when
its post is live (or ship option B first — one link to the umbrella post — then add per-step links as
posts publish).

## Cross-domain / brand note
- Posts live on **blog.thinkwithfinance.com** (neutral finance-education brand) — deliberately *not* on
  the `.dev` dev-brand. This separation is good: TWF = education, RA = the tool. The cross-links tie a
  trusted educational brand to the product.
- RA app link uses the canonical RA domain. Once the **aimlds.org mirror** decision is made, use the
  canonical of {devinfo.dev, aimlds.org} in the CTA and add the mirror as a secondary.

## Sequencing (respects your twf rules)
- twf **Queue Filler is throttled 2×/week (Mon/Thu)**; **daily cron is OFF — publish is manual via
  `/run`**, with your review before anything goes public. Those rules are honored — this series just
  **prioritizes the queue**: 10 posts at 2×/week ≈ **5 weeks**, starting from the already-staged dividend
  post.
- Each post: ~800–1,200 words, one worked example (reuse RA output for a well-known ticker), the standard
  **"informational/educational only — not financial advice"** disclaimer (matches RA's own), general
  education (no specific buy/sell calls), your writing voice.

## What is NOT in scope here (future build steps, each phased)
1. Drafting the 10 posts into the twf content queue (queue additions + your review).
2. Wiring the RA→blog links (renderer/UI change → branch + PR → box redeploy for the API-rendered
   reports; Pages for the UI).
3. Any publish (`/run`) — stays manual and reviewed.

## Open decisions for you
1. **Linking depth:** Option A (per-step "How this is computed" links) or Option B (single umbrella link)?
2. **Series scope:** all 10, or start with the core 7 engines + the umbrella (skip data-sources/comparative for v1)?
3. **Canonical RA domain** in the CTA — waits on the aimlds.org mirror decision from the packaging thread.
