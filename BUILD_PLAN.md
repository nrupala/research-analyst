<!--
Copyright (C) 2026 2351485 ALBERTA INC. - SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# BUILD PLAN — Source-Data Export Integrity & Report Clarity

Plan for correcting the confirmed defects behind the unclear/unauditable items
observed in the META `source_data` bundle, and for making the exported
scenario valuation self-describing.

Branch: `fix/source-data-export-integrity`
Created: 2026-09-27
Gate tracker: `ASFQC/GATES.md`
Progress log: `DEVELOPMENT_PROGRESS_TRACKER.md`

---

## 1. Executive Summary

**What.** A paid, customer-facing JSON/CSV download
(`POST /api/research/data`) contains eleven confirmed defects: three are wrong
attribute names that make real computed values export as `null`, one is an
aggregation rule that deletes keys, one truncates data in the export path, one
admits implausible values as fact, and several are labels that misrepresent
what the number actually is.

**Why.** The bundle is a paid artifact that customers ingest programmatically.
Silent `null`s are worse than absent keys: a consumer cannot distinguish "not
computed" from "computed but dropped by a typo". Two of the defects
(`payout_ratio`, `fcf_deployment`) are a single class of bug — an exporter
reading attribute names that do not exist on the model — and one
(`scenarios[].pe_multiple`) is a real number computed correctly and then
discarded.

**Scope decision (user-approved, 2026-09-27).** Fix the plumbing and keep the
scenario engine. The valuation engine already computes a scenario P/E that
blends the company's own trailing P/E with the peer median
(`engines/valuation.py:250-266`); the defect is that it is recorded only as
prose and then dropped. Replacing the hardcoded ±3pp / ×1.2 assumption
constants with a data-derived model is **deferred** until the `quant/` Python
port lands, so that it can reuse the ported `trends` and `sensitivityGrid`
rather than being written twice.

**Timeline.** Single focused PR. No dependency on the quant port.

## 2. ASF Gate Compliance Overview

| Gate | Applicability | Plan of record |
|---|---|---|
| G0 Build | Applicable | No build-system change. `pyproject.toml` untouched. |
| G1 Tests | **Critical** | Every defect gets a failing test *first*. The exporter is currently under-asserted, so this is the main risk to retire. |
| G2 Lint | Applicable | `ruff` clean on all changed files. Pre-existing `E501` at `svg_charts.py:193` left alone, recorded in `GATES.md`. |
| G3 License | Applicable | AGPL header on every new file. `LICENSE` / `COMMERCIAL-LICENSE.md` untouched. |
| G4 Docs | Applicable | Fix G9 gap: document the bundle's key names in `docs/API-REFERENCE.md`. |
| G5 Reproducible | Applicable | Verified on Aetheris from a clean clone before deploy. |
| G6 Release | Applicable | `CHANGELOG.md` entry. No version bump (owner controls versioning). |
| G7 Governance | Applicable | This plan + `DEVELOPMENT_PROGRESS_TRACKER.md` + decision log. |
| G8 CI | Applicable | PR must show "Lint, Type Check & Test" **pass** (not skipping). |
| G9 Docs | Applicable | API reference section for the bundle schema. |

**Known CI caveat:** lint is non-blocking in `ci.yml` (`|| true`), so G2 is
enforced on changed files manually rather than by the pipeline. Recorded in
`GATES.md` rather than claimed as a clean repo-wide sweep.

## 3. Phase Structure

| Phase | Content | Exit criteria |
|---|---|---|
| **P0** | Planning artifacts + branch | Plan, gates, tracker exist; branch cut from `origin/main` (`eeb97d8`) |
| **P1** | Characterisation tests | Failing tests reproduce each of the 11 defects |
| **P2** | Exporter correctness | Field names, aggregation, dedupe, provenance |
| **P3** | Scenario valuation plumbing | Computed multiple present on the model and in the export |
| **P4** | Presentation honesty | Labels, peer names, P/E plausibility, N/A column, partial-year dividend |
| **P5** | Documentation | Bundle schema documented; changelog |
| **P6** | Gate review + merge + deploy | All applicable gates PASS with evidence; Aetheris verified live |

P1–P4 are one PR: they touch interlocking parts of one code path, and
splitting them would ship a bundle that is still internally inconsistent.

## 4. Per-Phase Detail

### P0 — Planning artifacts
**Files:** `ASFQC/GATES.md`, `BUILD_PLAN.md`, `DEVELOPMENT_PROGRESS_TRACKER.md`
**QA/QC:** Gate statuses recorded from real commands, not assumed.
**Rollback:** `git checkout main`.

### P1 — Characterisation tests (failing first)
Target `tests/test_data_export.py` (currently 6 tests, none asserting the
defective keys) and add focused cases.

Defects to pin, each as a test that fails before the fix:
1. `metrics.payout_ratio` is `null` while `payout_ratio_eps`/`_fcf` hold real values.
2. `fcf_deployment` sub-keys all `null` despite `*_pct_of_fcf` being populated.
3. `scenarios[*].pe_multiple` is `null` despite the engine computing it.
4. Multi-report request: `risk_score` **disappears** from `metrics` while the
   risk table persists in `tables` (last-report-wins replace).
5. `scenarios` and `peers` duplicated once per report.
6. `peer_median_yield` absent from the bundle entirely.
7. Peer names truncated to 20 chars **in the exported** peer rows.
8. A financial period with all-null metrics becomes an all-`N/A` column.
9. A negative P/E renders as a plausible-looking `-45.0x`.
10. `vs 10Y Treasury` row shows the *Treasury's* yield under a label implying it is the company's.
11. `annual_dividends` includes the in-progress year with no partial marker.

**QA/QC:** each test must fail for the stated reason — assert the cause, not
just the symptom (e.g. test 4 asserts the key vanishes, not merely that a
table exists).
**Rollback:** tests are additive; a bad test is deleted, no code to unwind.

### P2 — Exporter correctness
`research_analyst/data_export.py`.

- Export the **real** field names (`payout_ratio_eps`, `payout_ratio_fcf`,
  `*_pct_of_fcf`). Remove the phantom `payout_ratio` key rather than leaving a
  permanently-`null` field, so consumers get a real absence instead of a lie.
- Change `_extract_metrics` from wholesale replace (`data_export.py:109`) to a
  **merge that never overwrites a populated value with a null**. Document the
  precedence rule. This is the fix for defect 4.
- Dedupe `scenarios` by `scenario_type` and `peers` by `ticker` (defect 5).
- Export `peer_median_yield` alongside `current_yield` (defect 6), and export
  the per-peer `dividend_yield` values so the median is **reproducible from the
  export** — today it is computed over the competitor universe, which is a
  different population from the exported peer rows, so a consumer recomputing
  it gets a different number.
- Export scenario `assumptions` for provenance (defect 3, supporting).

**QA/QC:** the P1 tests for 1, 2, 4, 5, 6, 11 turn green.
**Rollback:** single-file revert; bundle is regenerated per request, so no
persisted state to migrate.

### P3 — Scenario valuation plumbing
`research_analyst/engines/valuation.py`, `research_analyst/models.py`.

- `valuation.py:372-385` currently returns `pe_multiple=None` /
  `ev_ebitda_multiple=None` while the computed values live in the local
  variables `scenario_pe` (`:266`) and the EV/EBITDA equivalent (`:296`).
  **Populate the model fields with the computed numbers** and keep the prose
  `Assumption` entries as the human-readable restatement.
- This fixes the export, the HTML report and the SVG chart in one place,
  instead of teaching each consumer to parse prose.
- Note (recorded, not fixed here): the margin effect enters EPS
  *multiplicatively* as `1 + (margin_adj / op_margin)` (`:271`) while the
  displayed `operating_margin` is base + delta. Two different constructions of
  the same idea. Flagged for the deferred assumption rebuild.

**QA/QC:** scenario P/E tests round-trip through the model and the export.
**Rollback:** revert `valuation.py`; the field becomes `null` again, which is
the current behaviour, so no consumer breaks.

### P4 — Presentation honesty
`research_analyst/reports/visuals.py`, `research_analyst/reports/renderer.py`,
`research_analyst/engines/dividend.py`, `research_analyst/providers/market_data.py`.

- **Peer names** — remove the hard `p.name[:20]` slice (`visuals.py:321`). The
  exporter re-parses this markdown, so the truncation is a real data loss in
  the paid CSV, not just a display choice. Full names fit: `ui/app.js:569`
  already wraps tables in `.table-scroll`. Keep the `peers[:8]` cap.
- **Peer P/E plausibility** — `_safe_float` (`market_data.py:94-101`) rejects
  only non-finite values. Give P/E a documented display rule: non-positive
  P/E is *not meaningful*, render `n/m`, and exclude it from peer ranking
  inputs. The surrounding code already normalises `debtToEquity` (`:903-907`)
  and filters non-positive dividend yields downstream, so this is consistent
  rather than novel.
- **Financial summary** — `table_financial_summary` slices the last 5 periods
  purely chronologically (`visuals.py:349,355`) and emits `N/A` for every null
  metric (`:364-365`). Drop **all-null** periods and, when any are dropped,
  say so in the caption. Silently omitting a year would itself be dishonest,
  so the omission must be visible.
- **Partial-year dividend** — `_complete_years` (`dividend.py:179-188`) already
  knows how to drop the in-progress year but is only applied to growth
  (`:195`), not to the stored/exported dict (`:126-127`). Export complete years
  in `annual_dividends` and, when the current year is partial, emit it under an
  explicitly named key with a partial marker. The caveat currently exists only
  at `svg_charts.py:380-383`; JSON/CSV consumers get none.
- **`vs 10Y Treasury`** — the arithmetic is **correct**; the label is not. The
  row value is the Treasury's own yield. Relabel so the row cannot be read as
  the company's yield, and keep an explicit signed spread with direction.
  Separately: `us_10y_yield` falls back to a hardcoded
  `risk_free_rate: float = 0.043` (`config.py:89`) rather than a live
  observation — record which one produced the number, because presenting a
  constant as an observation is the same class of problem.
- **`risk_score: null`** — this is **correct, documented behaviour**
  (`renderer.py:992-996`): no material risks means no score is published. Do
  not invent a score. The actual defect was the aggregation loss (P2). Ensure
  the export explains the null rather than leaving it bare.

**Rendering specimen (prototype for the user-facing change).** Row-level
before → after for the **real META dividend block**, using the actual values in
the downloaded bundle so the change is reviewable as text. "Before" is
verbatim from `C:\Users\nrupa\Downloads\META_source_data.json`.

```markdown
Before (verbatim from the export)
| **Current Yield (fwd)** | 0.28%       |
| **Payout (EPS)**        | 8%          |   <- present in tables...
| **Payout (FCF)**        | 10%         |   <- ...but metrics.payout_ratio = null
| **FCF Coverage**        | 9.64x       |
| **Consecutive Increases** | 1 yrs     |   <- grammar
| **Peer Median Yield**   | 3.41% (below)|
| **vs 10Y Treasury**     | 5.18% (-490 bps) |  <- conflates two numbers
| **Attractiveness**      | Unattractive (income) |

After (VERIFIED — captured from the running code, not proposed)
| **Current Yield (fwd)**   | 0.28%                        |
| **Annual Rate**           | $2.00/share                  |
| **Payout (EPS)**          | 8%                           |
| **Payout (FCF)**          | 10%                          |
| **FCF Coverage**          | 9.64x                        |
| **Consecutive Increases** | 1 year                       |
| **Peer Median Yield**     | 3.41% (below)                |
| **10Y Treasury Yield**    | 5.18%                        |
| **Spread vs 10Y Treasury**| -490 bps (4.90 pp below 10Y) |
| **Attractiveness**        | Unattractive (income)        |
```

Two deviations from the original proposal in this plan, both recorded rather
than silently absorbed:

- The row labels stay `Payout (EPS)` / `Payout (FCF)`. The proposal renamed them
  to `Payout Ratio (…)`; the existing labels are already unambiguous once the
  two rows are separated, and renaming them adds a second, unnecessary contract
  change on top of the key rename.
- `Peer Median Yield` does **not** carry an `n=` count. The peer population
  lives in the report's competitor section, not on `DividendAnalysis`, so the row
  cannot know it without a signature change. The count is instead addressed by
  exporting `peer_yields` — see open item 8 for the remaining population gap.

**A bug the verification caught.** The first implementation of the split printed
`-490 bps (0.28% below 10Y)`: the parenthetical used `current_yield` (0.28%)
instead of the spread magnitude (4.90 pp), so the row claimed a 0.28% spread
while printing 490 bps — a re-creation of the exact conflation the split
removes. It also dereferenced `current_yield` unconditionally and raised
`TypeError` when a yield was absent but a spread present. Fixed to
`abs(spread) * 100` pp and pinned by
`test_spread_parenthetical_states_the_spread_not_the_companys_yield`, verified
to fail when the original expression is reinstated.

Three properties the specimen is designed to guarantee:

1. No row can be misread about **whose** number it is. The `vs 10Y Treasury`
   row currently carries the *Treasury's* yield (5.18%) under a label that
   invites reading it as the company's; splitting it into a level row and a
   signed-spread row removes the ambiguity entirely. The arithmetic is already
   correct and is not changed.
2. `metrics` stops emitting a key that is permanently `null`. The real values
   exist in `tables` all along, so this is a read-the-right-attribute fix.
3. `peer_median_yield` is exported so a customer can reproduce it. Today the
   median is computed over the whole competitor universe, which is a different
   population from the 8 exported peer rows, so recomputing it from the export
   yields a *different* number. The per-peer yields must ship with it.

**QA/QC:** P1 tests 7, 8, 9, 10, 11 turn green; new assertion that no exported
peer name exceeds the model's full name; new assertion that the all-null period
is dropped **and** the caption mentions it.
**Rollback:** per-file revert; presentation-only, no data migration.

### P5 — Documentation
- `docs/API-REFERENCE.md`: document the bundle's top-level keys and the
  `metrics` precedence rule, and state which keys can legitimately be `null`
  and why. This closes ASFQC G9 open item 4.
- `CHANGELOG.md`: entry describing the corrections. **No version bump** — the
  owner controls versioning, and the existing versioning work must not be
  disturbed.

**QA/QC:** documented key names match the produced bundle (verified by test, not
by eye).
**Rollback:** docs-only revert.

### P6 — Gate review, merge, deploy
Gate table in `ASFQC/GATES.md` updated with real command output. Full suite on
**both** Windows and Linux. Merge to `main`, then the Aetheris procedure:
rollback point → `git pull --ff-only` (assert exact SHA) → `pip install .` →
unit sync → `daemon-reload` → restart → health + journal verification.

## 5. Overall Timeline & Milestones

| Milestone | Depends on | Verification |
|---|---|---|
| M1 Planning artifacts | — | 3 files present |
| M2 Failing tests prove 11 defects | P1 | each test fails for its stated reason |
| M3 Exporter correct | P2 | tests 1, 2, 4, 5, 6 green |
| M4 Scenario multiple exported | P3 | test 3 green; model field non-null |
| M5 Presentation honest | P4 | tests 7–11 green |
| M6 Docs match reality | P5 | schema test green |
| M7 Gates green, merged, live | P6 | CI pass + Aetheris health 200 |

## 6. Quality Assurance & Risk Mitigation

**Primary risk — the exporter is under-tested.** `tests/test_data_export.py`
passes while exporting a permanently-`null` key, and its fixtures pass
`payout_ratio=0.15` into a Pydantic model that silently discards unknown
kwargs (`extra='ignore'`). A green suite currently coexists with a broken
bundle. Mitigation: P1 comes first and no fix lands without a test that fails
before it.

**Risk — fixing field names could change the customer contract.** Renaming
`payout_ratio` is technically a breaking change for anyone consuming the
download. **As implemented:** the old key is removed outright and
`schema_version` is bumped `1.0` → `1.1`. The deprecation path originally
planned here (retain the old key with the EPS-based value for one release) was
considered and **rejected** — retaining a phantom aggregate would mean shipping
a number whose basis is ambiguous, which is precisely the defect being fixed, and
`payout_ratio` was `null` on every real bundle anyway, so nothing with a real
value breaks. Consumers reading the key were reading `null`. Recorded as
`ASFQC/GATES.md` open item 11 for owner confirmation rather than merged silently.

**Risk — dropping all-null periods could be read as hiding data.** Mitigation as
implemented: the omission is stated in the caption, naming each omitted period
and the reason, and the period is **still present in the export** inside
`tables` (which ships the report's markdown verbatim) so the audit trail
survives. A structured `omitted_periods` key in `metrics` was considered and not
added — the information is already retrievable and a second representation risks
the two disagreeing.

**Risk — `metrics` merge precedence could mask a newer value.** Mitigation:
explicitly documented rule (a populated value is never overwritten by a null),
covered by a test that asserts the precedence, not just the outcome. The residual
case — two reports disagreeing on the same populated key — is resolved
first-wins, which is order-independent; a disagreement is therefore reported by
whichever report the engine runs first, not hidden.


**Risk — the DEFERRED rebuild is forgotten.** Mitigation: recorded as a named
follow-up in `ASFQC/GATES.md` open items and in the changelog, explicitly
gated on the quant port.

**Rollback path.** Every phase is a revertible file change. The bundle is
computed per request with no persisted state, so reverting the code fully
restores prior output. Deployed rollback point recorded before each deploy.

## 7. Approval Checklist

- [x] User approved scope: report/export fixes first
- [x] User approved: fix the scenario plumbing, keep the engine
- [x] User approved: quant port deferred to a later phase
- [x] User approved: deploy to Aetheris after merge (granted for PR #81; to be
      re-confirmed for this PR)
- [ ] User reviews the P4 rendering specimen above before merge
- [x] AGPL headers and dual-licensing preserved
- [x] Gate tracker created with honest status (G4 recorded FAIL, G9 NOT-STARTED)

## 8. Success Metrics

| Metric | Target |
|---|---|
| Defects with a failing test *before* the fix | 11 / 11 |
| Permanently-`null` export keys after the fix | 0 |
| Exported values a consumer cannot reproduce from the bundle | 0 |
| Ambiguous or mislabelled user-facing rows | 0 |
| Test suite | green on Windows **and** Linux |
| `ruff` on changed files | clean |
| CI | "Lint, Type Check & Test" pass |
| Regression | 0 new failures; `341 passed` floor maintained on Linux |
| ASF gates with recorded evidence | all applicable gates PASS; G4/G9 open items tracked |
