# Codetopo Profile — Research Analyst (nrupala/research-analyst)

**What this is.** The agent-facing map of this repository, generated with
Codetopo 0.9.1 (local engine) — topology, trust boundaries, money
surface — with the graph snapshot beside it (`snapshot.json`,
`stats.json`) as the measured evidence.

- **Repo:** nrupala/research-analyst (public)
- **Commit profiled:** `b6dcbd3f2bef2ab1b0cc626e8dd4e187942d55dc` (main)
- **Engine:** codetopo 0.9.1 · index run 2026-11-18
- **Graph:** 231 files walked · 6,097 nodes · 26,092 edges · audit chain valid
- **Nodes by kind:** function 1,381 · method 680 · class 293 · interface 36 · variable 584 · module 231 · file 231 · doc 36 · external 2,623 · package 2
- **Edges by kind:** calls 9,169 · reads 9,132 · contains 3,472 · defines 2,006 · imports 1,221 · writes 1,089 · inherits 3

## Coverage honesty

Extracted at symbol level: Python (149 `.py` — the engine) and
TypeScript/JavaScript (36 `.ts` + JS — the web/app surfaces), Markdown
as Doc nodes. Not parsed: JSON/TOML config, shell deploy scripts, CSV
data fixtures. Symbol coverage of the code is complete for the
languages present.

## Topology

An institutional-grade stock-research engine (the RA tool; canonical
front door aimlds.org). The Python package `research_analyst/` is the
hub of the graph:

- `orchestrator.py` — the run pipeline that ties a report together.
- `engines/` + `quant_engine/` + `quant.py` — the analysis engines
  (fundamental, technical, quantitative; the moat logic lives here).
- `providers/` — market-data providers. **Stooq is the declared
  production price source**; yfinance is development-only, never a
  silent production fallback (house data doctrine).
- `server.py` — the HTTP/API surface; `cli.py` the command line;
  `api_models.py` / `models.py` / `enums.py` the data model.
- `entitlements.py` — who may run what (see Money surface).
- `exporters.py` / `report_export.py` — report rendering (HTML/reports);
  `disclaimer.py` — the compliance wording carried on outputs.
- `deploy/` — deployment assets; `ASFQC/` — quality-control records.

## Trust boundaries

- **Data truth boundary:** production prices come from Stooq only;
  a provider failure must surface, never silently substitute another
  source (the graph's provider imports show exactly which modules can
  fetch data — audit changes there first).
- **Entitlement boundary:** `entitlements.py` gates paid capability;
  `config.py` holds provider/billing configuration **by name** —
  credential values live in the environment/vault, never in this repo,
  and none appear in this profile.
- **Advice boundary:** outputs are analysis, not personal financial
  advice; `disclaimer.py` wording ships with reports by design.
- **Blast radius:** `orchestrator.py`, `models.py` and the provider
  layer concentrate the 9,169 call edges — a change there alters every
  report the engine produces.

## Money surface

RA is a sold product (licences; see `COMMERCIAL-LICENSE.md` /
`TERMS.md`): `entitlements.py` + `server.py` + `config.py` reference
the Stripe-backed entitlement flow — payment is taken by Stripe, and
this code grants/revokes capability from entitlement state. No card
data touches this repo; billing secrets are environment-held, by name
only. The engine itself spends on data only through its configured
providers.

## How an agent should approach

1. Read `README.md`, `SECURITY.md`, `TERMS.md`, then this profile.
2. Query the graph before touching `providers/`, `entitlements.py` or
   `orchestrator.py`.
3. Never wire a new data source into production paths without the
   doctrine check (Stooq = production truth).
4. Regenerate this profile at every release.

## Regeneration

`docs/codetopo-profile/refresh.sh` (in this pack) re-fetches the repo
at a named ref, re-runs the index, and rewrites `snapshot.json`,
`stats.json` and `verify.txt`.

## Standing-condition lines for this change

- Documentation at par: this pack is the documentation change, same PR;
  no behaviour changed.
- Release gate: NOT RUN for this profile PR · Guardian Mesh approval:
  NOT RUN. Merging is not "shipped"; the pack enters the gate queue in
  the Stage-1 evidence pack.
- OpenSSF Best Practices: no project registered for this repo on
  bestpractices.dev (checked 2026-11-18) — a named gap; this additive
  docs change does not degrade any criterion.
