<!--
SPDX-FileCopyrightText: 2026 2351485 ALBERTA INC.

SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Skill: research-analyst — equity research with provenance, for agents

Use this skill when you are an AI agent and you need **researched facts
about a listed company or ETF** — fundamentals, filings coverage,
valuation inputs — each with its source named, before you summarize,
compare, or brief a human.

## The boundary (read first)

Research Analyst is **research and education only**. Its outputs are
decision intelligence with provenance for the reader's own decision —
never investment advice, never a recommendation, and it never tells
anyone to buy, sell, or hold anything. Keep that boundary in your own
answer: report what the record shows, name the source, and leave the
decision to the reader.

## Connect

- Endpoint: `POST https://analyst.thinkvalue.org/api/mcp` — streamable
  HTTP, JSON-RPC 2.0, stateless. Methods: `initialize`, `ping`,
  `tools/list`, `tools/call`. (GET is not offered; it answers 405.)
- Auth: an API key is required. Send it as `Authorization: Bearer <key>`
  or in the `X-RA-Key` header — the same key the REST API takes; it
  must carry API access. Keys come with the product's paid plans; the
  checkout claim flow reveals the key exactly once, so store it then.
- Limits: a per-key rate cap (60/min on API Pro, 300/min on API Team)
  and a monthly call allowance apply to `tools/call`. Successful calls
  meter against the key; failed calls never do.

## The tools (3: two pipelines, one composite)

| Question | Tool |
|---|---|
| What does the filing record actually contain for X — and what is missing? | `filing_picture` |
| Give me the full research report on X | `research` |
| Give me the quantitative study on X | `quant` |

- `filing_picture` `{ticker}` — the composite. One call over SEC EDGAR
  returns three named buckets: `filings_found` (counts by core form —
  10-K, 10-Q, 8-K — with filing dates), `periods_covered` (the
  standardized financial statements the EDGAR data supports), and
  `not_covered_named` (every gap, named: a core form with no filings,
  a core line item absent from every returned statement, and the
  declared scope limits of the search itself).
- `research` `{ticker}` — the full pipeline: fundamentals, technicals,
  macro context, competitor dynamics, and valuation, each with named
  sources and stated assumptions. Returns the rendered markdown plus
  the structured payload — the same payload REST `POST /api/research`
  returns, verbatim.
- `quant` `{ticker, discount_rate?, scenarios?}` — growth trends,
  DuPont decomposition, forensic screens, valuation models, and
  capital allocation, computed from the same merged statements as the
  research report, with the statement source declared.
  `discount_rate` is an analyst assumption, not observed data; it
  enables the implied-growth inversions.

## The workflow (coverage first, conclusions last)

1. **Start with `filing_picture`.** Before you interpret anything,
   learn what the record holds and what it does not. If
   `not_covered_named` names the very thing your task needs, say so —
   do not route around the gap silently.
2. **Then `research`** for the report, **`quant`** when the question is
   numeric. Both read the same underlying data the picture described.
3. **Read the metadata before you quote a number.** Every payload
   carries its sources and its `data_as_of`. A report served from
   cache is stamped with its cache state; a report stamped **stale**
   (data older than ~2 days) must be flagged as stale in your answer,
   never presented as current.
4. **Carry the gaps into your answer.** `not_covered_named` is part of
   the result, not fine print. Relay it with the findings.

## Rules of the house

- **Provenance on every number.** If you state a figure, name where it
  came from (the payload's sources, its `data_as_of`). A number
  without a source is a defect in your answer.
- **Missing stays missing.** RA reports absent inputs as absent — a
  line item that is not in the statements, a period with no filing.
  Never estimate, interpolate, or zero-fill what RA reported missing.
- **Uncertainty is displayed, not smoothed.** Scope limits (for
  example: the filing search window starts 2020-01-01; Form 4 insider
  filings and DEF 14A proxies sit outside `filing_picture`'s core form
  set) are stated in the output itself. Repeat them when they bear on
  the answer.
- **Freshness is end-of-day, on demand.** Reports regenerate on the
  first request after each US market close and are never served past
  a 24-hour cap; there is no background refresh timer. The measured
  record is in the README ("Data freshness — how refresh actually
  works, measured").
- **Same answers on every surface.** The MCP tools serve the same
  pipelines as REST — pick whichever surface your host gives you; the
  payload is identical by construction.

---

*Agentic Packaging Standard conformance (2026-11-18): explicit
uncertainty — met (`not_covered_named` is a first-class bucket;
missing inputs are reported as missing; stale reports are stamped,
not silently served); composite task tools — met by `filing_picture`
over the EDGAR provider (`research` and `quant` remain the two
underlying pipelines); agent onboarding — met by this file;
zero-compile install — met by construction (a hosted endpoint;
nothing to install); measured traces — met in part (the README
freshness measurement of 2026-11-18; a public tool-call/token
comparison trace is still open); terminal-story docs — open (no
captured agent session published yet).*
