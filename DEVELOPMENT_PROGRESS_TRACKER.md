<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> - SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# DEVELOPMENT PROGRESS TRACKER

Effort: Source-Data Export Integrity & Report Clarity
Branch: `fix/source-data-export-integrity`
Base: `origin/main` @ `eeb97d8`
Plan: `BUILD_PLAN.md` · Gates: `ASFQC/GATES.md`

---

## 1. Build Phase Status

| Phase | Scope | Status | Gate evidence |
|---|---|---|---|
| P0 | Planning artifacts + branch | **DONE** | `ASFQC/GATES.md`, `BUILD_PLAN.md`, tracker written; branch cut from `eeb97d8` |
| P1 | Characterisation tests (11 defects) | **DONE** | `tests/test_export_integrity.py` — 27 tests written before any production edit, 24 observed failing against unfixed code; +4 guards added later (2 spread regression, 2 docs-vs-payload) |
| P2 | Exporter correctness | **DONE** | `data_export.py`: 8 of the 11 defects; verified against a real META bundle |
| P3 | Scenario valuation plumbing | **DONE** | `engines/valuation.py` — applied multiples published on the model |
| P4 | Presentation honesty | **DONE** | `reports/visuals.py` — 3 of the 11 defects; ruff findings 23 → 17 |
| P5 | Documentation + changelog | **DONE** | `docs/API-REFERENCE.md` bundle-schema section; `CHANGELOG.md` Unreleased entries; 2 docs-vs-payload tests |
| P6 | Gate review + merge + deploy | **IN PROGRESS** | Gates updated; awaiting commit, PR, CI, and deploy re-authorisation |

## 2. Agent Work Tracking

| Date | Phase | Work done | Verification |
|---|---|---|---|
| 2026-09-27 | P0 | Read-only exploration of the quant package and the report/export data path. Corrected several earlier hypotheses: the scenario P/E **is** computed (`valuation.py:266`) and merely dropped; `payout_ratio` and the `fcf_deployment` keys are **wrong attribute names**; `risk_score: null` is correct behaviour whose *real* cause is `metrics` last-report-wins. | Line-level source reads reported by exploration; each claim re-verified by the implementing agent before any edit |
| 2026-09-27 | P0 | User approved scope: report/export fixes first; fix scenario plumbing, keep the engine; quant port deferred. | User decision recorded in session log |
| 2026-09-27 | P0 | Created gate tracker with **honest** status: G4 FAIL (`CODE_OF_CONDUCT.md` missing), G9 NOT-STARTED, G2 flagged as changed-files-only, G8 gap for the `quant/` suite. | `Test-Path` for artifacts; gate rows carry real commands |
| 2026-09-27 | P1 | Wrote `tests/test_export_integrity.py` covering all 11 defects as **characterisation tests**: every one was observed **failing** against the unfixed code before any production edit. | First run: 24 failed / 3 passed. 21 of the 24 were genuine; 3 were my own fixture bugs (`VisualEngine` vs `VisualsBuilder`, `ReportType.TECHNICAL` which does not exist, `FinancialStatement(ticker=...)`). Corrected rather than weakened. |
| 2026-09-27 | P1 | Guarded against the misleading-fixture trap (open item 4): fixed `tests/test_data_export.py:60`, which passed `payout_ratio=0.15` into a Pydantic model with `extra='ignore'` — silently discarded, and the reason a phantom key survived review. Now passes `payout_ratio_eps` / `payout_ratio_fcf`. | `pytest tests/test_data_export.py` → 6 passed |
| 2026-09-27 | P2 | Exporter: correct dividend and FCF field names; merge `metrics` with explicit precedence instead of last-report-wins; deduplicate `scenarios` by type and `peers` by ticker; export `peer_median_yield` + `peer_yields`; split `annual_dividends` into complete vs partial years; export treasury level and spread separately with signed bps; add `risk_score_note`; emit `ev_ebitda_multiple`, `implied_upside_*` and per-scenario `assumptions`. | `tests/test_export_integrity.py` → 31 passed |
| 2026-09-27 | P3 | Engine: publish the P/E and EV/EBITDA multiple actually applied on the `ValuationScenario` model, so export, HTML report and SVG chart read the same number instead of only narrating it. | `test_scenario_carries_the_multiple_the_engine_computed` exercises `ValuationEngine._build_scenario()` directly and asserts the model field is populated |
| 2026-09-27 | P4 | Presentation: non-positive P/E renders `n/m` with a caption; all-`null` financial periods excluded and the omitted periods named; peer table gains a `Div Yield` column and full (untruncated) names; Treasury split into level + signed spread rows; partial-year dividend and singular-year grammar fixed. | Asserted on `ReportVisual.content` strings, not just non-null |
| 2026-09-27 | P5 | Documented the bundle schema (the gap that let phantom keys survive) and bumped `schema_version` 1.0 → 1.1, then bound the two together with a test. | `test_schema_version_tracks_the_documented_shape` parses the `schema_version` row out of the doc and compares it to the emitted value — this caught that I had written 1.1 in the docs while the code still said 1.0 |
| 2026-09-27 | P5 | Full-suite and lint verification, before/after compared per file. | `python -m pytest -q` → **371 passed, 2 skipped** (baseline 340 + 31 new, zero regressions). `ruff check` on the five touched files → 26 findings, **all pre-existing**: `valuation.py` 9 → 9, `visuals.py` 23 → **17**, `data_export.py` 0, `test_data_export.py` 0 |
| 2026-09-27 | P6 | Updated `ASFQC/GATES.md` with real evidence and closed G9's bundle-schema gap; raised the deprecation question and two residual-data questions as recorded open items. | G9 → PARTIAL; open items 1–11 with explicit status |

## 3. Checkpoints

| Checkpoint | When | Result |
|---|---|---|
| Root cause established for every reported symptom | P0 | DONE — 11 defects, all with file/line evidence |
| No fix lands without a test that fails first | P1–P4 | **DONE** — 27 characterisation tests were written before any production edit and 24 were observed **failing** against the unfixed code; the 3 that passed were my own fixture bugs (`VisualEngine` vs `VisualsBuilder`, non-existent `ReportType.TECHNICAL`, `FinancialStatement(ticker=…)`), corrected rather than weakened. 4 further guards were added during P4–P5, including one verified by mutation (reinstating the buggy expression fails 2 tests, 29 pass). |
| Suite green, no regressions | P5 | **DONE** — 371 passed / 2 skipped vs 340 / 2 baseline |
| `ruff` clean on changed files | P5 | **DONE** — 0 new findings; `valuation.py` unchanged at 9, `visuals.py` improved 23 → 17 |
| ASFQC GATES.md updated with real output | P6 | **DONE** — G1/G2/G6/G9 carry observed output; G4 remains an honest FAIL |
| Suite green on Linux | P6 | **PENDING** — will be observed on the CI run; Linux floor was `341 passed, 1 skipped` |
| Owner confirmation on the breaking key change | P6 | **PENDING** — see Blockers |

## 4. Open Items

| # | Item | Notes |
|---|---|---|
| 1 | **Deferred by decision:** replace hardcoded scenario constants (±3pp / ×1.2 / 0.8) with a data-derived assumption model | Gated on the `quant/` Python port so it can reuse the ported `trends` / `sensitivityGrid`. Do not implement before the port. |
| 2 | **Deferred by decision:** scenario margin effect enters EPS *multiplicatively* (`1 + margin_adj / op_margin`, `valuation.py:271`) while the displayed `operating_margin` is base + delta. Two constructions of one idea. | Same gate as #1. |
| 3 | `us_10y_yield` falls back to a hardcoded `risk_free_rate = 0.043` (`config.py:89`) rather than a live observation. | P4 now names the benchmark honestly in the table, but the *source* is still a constant — same class of problem as the old conflated row. Needs a provider decision, not a patch. ASFQC open item 7. |
| 4 | ~~P1 fixtures pass phantom kwargs into Pydantic~~ | **DONE** — `tests/test_data_export.py:60` fixed. |
| 5 | ~~Does any existing test assert the bundle's key names?~~ | **Answered: no.** The new suite plus the two docs-vs-payload tests are now the contract. |
| 6 | `quant/` (125 tests) has no CI job, no lockfile, never installed; `vitest ^5.0.2` unverified; `@vitest/coverage-v8` missing from `devDependencies` while `vitest.config.ts` requests the v8 provider. | ASFQC open item 1. |
| 7 | `CODE_OF_CONDUCT.md` missing (G4 FAIL). | Owner decision; not authored unilaterally. |
| 8 | Repo-wide `ruff` backlog; CI lint is `|| true` so G2 is not enforced pipeline-wide. | ASFQC open item 3. |
| 9 | `peer_median_yield` is computed over the whole competitor universe while `peers` ships at most 8 rows. `peer_yields` makes the median reproducible for the peers shown, but the populations still differ. | Either export the full universe or state the population in the caption. ASFQC open item 8. |
| 10 | Low-but-positive peer P/E (e.g. CHTR 2.9x) renders as a real number; only non-positive is `n/m`. | **Deferred by decision** — a genuine low multiple should stay visible; automatic outlier suppression would hide information. ASFQC open item 10. |

## 5. Blockers

None.

Two decisions were **recorded rather than blocking**, and both have now been
confirmed by the owner (2026-09-27):

- **Key rename is a customer-contract change, and the planned deprecation path
  was NOT taken.** `BUILD_PLAN.md` originally proposed keeping `payout_ratio`
  populated with the EPS-based value for one release. That was **rejected in
  implementation**: the key is now removed outright and `schema_version` is
  bumped 1.0 → 1.1, because retaining a phantom aggregate would mean shipping a
  number whose basis is ambiguous — the exact defect being fixed — and the key
  was `null` on every real bundle, so no consumer was reading a real value from
  it. **Owner confirmed: ship the clean break.** Recorded as
  `ASFQC/GATES.md` open item 11 (CLOSED) rather than merged silently.

- **Aetheris deploy is not yet re-authorised for this PR.** The user's
  approval to deploy was given for PR #81. Re-confirm before P6 completes.

