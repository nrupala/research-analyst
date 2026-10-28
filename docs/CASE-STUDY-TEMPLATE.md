<!--
Copyright (C) 2026 2351485 ALBERTA INC. — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Research Analyst — Case-Study Brief Template (Phase 9d)

For FEED/consulting pitches referencing Research Analyst + bee. Fill the
brackets; keep it evidence-first (numbers the reader can verify) and
educational-only (never investment advice).

---

## Case Study: [Client/Ticker] — [One-line outcome]

**Prepared:** [date] · **By:** [org] · **Subject:** [company/ETF, ticker]

### 1. The situation

- [Who the client is / what decision context they faced — e.g. family office
  evaluating a Canadian mid-cap energy name for the first time.]
- [Why this mattered — capital at stake, research gap, time pressure.]

### 2. What Research Analyst produced

- **7-step structured report** ([report type]) — fundamentals, competitive
  position, technicals, macro, risks, scenario valuation, thesis.
- **Typed exports** (JSON/XML/TS) + **source-data bundle** (CSV) — the client
  could pull the numbers into their own models.
- **Mental-model lenses** (educational) — Graham margin-of-safety, Greenblatt
  magic formula, Lynch PEG, Damodaran intrinsic value, Buffett owner earnings,
  Dalio regime framing, Marks cycle position.
- **Interactive views** — charts/diagrams opened on demand, zero-JS page.

### 3. How it was used

- [Analyst workflow: TUI + sync bundles overnight, PDF/HTML for the memo.]
- [Which sections drove the decision discussion — e.g. the scenario range +
  valuation-sanity playbook.]

### 4. Outcome

- [What changed — decision made, memo produced, monitoring loop set up.]
- [Verifiable result — e.g. "report generated in <X>s; data bundle <Y> rows;
  peer set <N> names; lens coverage 7/7".]

### 5. Stack (sovereign, no Docker)

- **Origin:** OCI box, native systemd, `127.0.0.1:8700`, hardened unit.
- **Web:** Cloudflare Pages PWA (`ra.devinfo.dev`, mirror `ra.aimlds.org`).
- **Data:** SEC EDGAR + market providers, disk-cached; educational-only
  disclaimer on every surface.

### 6. What bee brought

- [Bee integration: the companion agent/site element used alongside RA — keep
  to the actual scope of the FEED/consulting engagement.]

---

**Educational notice:** Research Analyst output is for educational and
informational purposes only — not investment advice or a recommendation to buy
or sell any security.