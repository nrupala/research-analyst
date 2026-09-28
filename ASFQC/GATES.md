<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> - SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# ASF Gate Compliance — Research Analyst

Gate tracker per the ASF quality gates. **A gate is PASS only with recorded
evidence** (command + observed output). No assumed passes.

Last updated: 2026-09-27 — branch `fix/source-data-export-integrity`

---

## G0 — Build system

| | |
|---|---|
| **Status** | PASS |
| **Evidence** | `pyproject.toml` (PEP 621, setuptools backend, `[project.optional-dependencies] dev`/`tui`, console script `research-analyst`). Clean install: `pip install -e ".[dev]"` exit 0 on both Windows and Linux (Aetheris aarch64 isolated venv). |
| **Notes** | `quant/` is a second, independent build (`package.json` + `tsconfig.json` + `vitest.config.ts`) that is **not** currently wired into CI or any deploy path. See Open Items. |

## G1 — Tests

| | |
|---|---|
| **Status** | PASS |
| **Evidence** | `python -m pytest -q` → **371 passed, 2 skipped** on Windows. Pre-change baseline in the same environment was `340 passed, 2 skipped`; delta `+31` = the new `tests/test_export_integrity.py` suite. Zero regressions: no previously-passing test changed outcome. PR #81 baseline (merged) was `340 passed, 2 skipped` Windows / `341 passed, 1 skipped` Linux (Aetheris). `quant/` suite: 125 tests across 8 files, **not executed in CI** (no `node_modules`; never installed). |
| **Notes** | The 2 skips are one POSIX-only test and one TUI/environment test; both pre-existing. See Open item 1 for the quant CI gap. |

## G2 — Lint / typecheck

| | |
|---|---|
| **Status** | PASS (with a recorded pre-existing exception) |
| **Evidence** | PR #81: `ruff check` on all changed files → `All checks passed!`; CI job "Lint, Type Check & Test" **pass**. This change: `python -m ruff check` on the five touched files → **26 findings, all pre-existing**, verified by per-file before/after comparison — `engines/valuation.py` 9 → 9 (unchanged), `reports/visuals.py` 23 → **17** (6 removed, none added), `data_export.py` 0 → 0, `tests/test_export_integrity.py` 0 (new file, clean), `tests/test_data_export.py` 0. |
| **Exception** | `research_analyst/reports/svg_charts.py:193` raises `E501` (111 > 100). **Confirmed pre-existing at `17b6bb1`** via `git show 17b6bb1:research_analyst/reports/svg_charts.py \| ruff check --stdin-filename -`. Deliberately not fixed in PR #81 to keep that diff focused. Must not be silently ignored elsewhere. |
| **Notes** | Repo-wide `ruff check .` reports a large pre-existing backlog (order-of-magnitude 271 findings at last count). CI treats lint as non-blocking (`\|\| true`). **This means G2 is enforced only on changed files, not repo-wide** — recorded here rather than claimed as a clean sweep. The 26 remaining findings in the two touched modules are `E501` line-length plus two `F401` unused imports that predate this work; they are recorded in Open item 3. |


## G3 — License

| | |
|---|---|
| **Status** | PASS |
| **Evidence** | `LICENSE` present — AGPL-3.0-or-later. `COMMERCIAL-LICENSE.md` present (dual-licensing for uses incompatible with AGPL). Every source file carries an `SPDX-License-Identifier: AGPL-3.0-or-later` header. `quant/package.json` declares `"license": "AGPL-3.0-or-later"`. |
| **Notes** | `NOTICE` is **not present**. Not legally required for pure AGPL-3.0, so not treated as a failure; recorded for completeness. |

## G4 — Contribution docs

| | |
|---|---|
| **Status** | FAIL |
| **Evidence** | `CONTRIBUTING.md` **present**. `CODE_OF_CONDUCT.md` **MISSING** (verified by `Test-Path`). |
| **Remediation** | Owner decision: adopt Contributor Covenant (or equivalent) and add the file. Deliberately not authored unilaterally — a Code of Conduct is a policy commitment, not a technical artifact. Tracked in Open Items. |

## G5 — Reproducible install / run

| | |
|---|---|
| **Status** | PASS |
| **Evidence** | `deploy/oci-native/bootstrap.sh` provisions user, venv, dirs (now including the matplotlib cache dir, step 4b) and `ra.service`. Verified end to end on Aetheris: fresh isolated `git clone` + `python3 -m venv` + `pip install -e ".[dev]"` → `341 passed`. Live service health `200` at loopback, `ra-origin.nrupalakolkar.com`, and `ra.devinfo.dev`. |
| **Notes** | `bootstrap.sh` must be run on a genuinely fresh host to fully prove this; current evidence is a working live deployment plus a from-clone install. |

## G6 — Release process

| | |
|---|---|
| **Status** | PASS |
| **Evidence** | `CHANGELOG.md` present. Version is `0.4.0` in `research_analyst/__init__.py` and `pyproject.toml`. CI has a "Create Release" job (observed **skipping** on PR #81, i.e. correctly gated to non-PR events). This change extends the `[Unreleased]` section with Fixed / Changed / Added / Deferred entries describing the bundle `schema_version` 1.0 → 1.1 break and the deprecation decision. |
| **Notes** | Tag strategy is owned by the release job's trigger configuration; not audited in this pass. The `schema_version` bump is the compatibility-relevant signal for consumers and is covered by a test so docs and payload cannot drift apart. |

## G7 — Governance

| | |
|---|---|
| **Status** | PASS (external log) |
| **Evidence** | Durable decision log at `C:\Users\nrupa\.config\opencode\conversation_decisions.md`, append-only, with entries for the 2026-09-27 deploy, the PR #81 fix and its root cause, and this work. `BUILD_PLAN.md` + `DEVELOPMENT_PROGRESS_TRACKER.md` (this effort) are the in-repo governance artifacts. |
| **Notes** | The decision log lives in the operator's global config, **not in this repository**, so it is not reviewable by an outside contributor. `BUILD_PLAN.md` + `DEVELOPMENT_PROGRESS_TRACKER.md` (this effort) are the in-repo governance artifacts. |

## G8 — CI/CD

| | |
|---|---|
| **Status** | PASS (Python path) |
| **Evidence** | `.github/workflows/ci.yml` — job "Lint, Type Check & Test" observed **pass** (1m10s) on PR #81; "Cloudflare Pages" observed **pass**; "Create Release" and "Deploy to Fly.io" correctly **skipping** on a PR. |
| **Gap** | The `quant/` TypeScript suite (125 tests) has **no CI job**. Nothing in `ci.yml` installs or runs it. Tracked in Open Items. |

## G9 — Documentation quality

| | |
|---|---|
| **Status** | PARTIAL |
| **Evidence** | `docs/` present with `API-REFERENCE.md`, `AGENCY.md` and deployment/API material. **This change closes the specific gap that let the export defects survive**: `docs/API-REFERENCE.md` now carries a "Bundle schema" section documenting every top-level key (`schema_version`, `ticker`/`company_name`/`currency`/`generated_at`/`security_type`, `tables`, `metrics`, `scenarios`, `peers`), the `metrics` precedence rule, which `null` values are legitimate and why (`risk_score`, dividend keys, `peer_median_yield`, `fcf_deployment.*`), the field-name traps (`payout_ratio_eps` vs `payout_ratio_fcf`, complete vs partial dividend years, why `peer_yields` must ship with `peer_median_yield`), and the scenario fields. Two tests assert the docs and the produced bundle agree (`test_schema_version_tracks_the_documented_shape`, `test_documented_top_level_keys_match_the_bundle`). |
| **Remaining** | The `docs/` set has **not** been audited against the full required guide list (user guide, quick start, install, configuration, troubleshooting). HTML publication build not attempted. Recorded as NOT-STARTED for the rest of G9; the bundle-schema part is done. |
| **Notes** | The undocumented key names were a direct contributing cause: `payout_ratio` looked plausible in the exporter, and no document said the model used `payout_ratio_eps`. Documenting the payload is a correctness control, not a chore. |

---

## Open items

| # | Item | Gate | Status |
|---|---|---|---|
| 1 | `quant/` (125 tests) has no CI job and has never been installed/typechecked; `vitest.config.ts` requests the v8 coverage provider but `@vitest/coverage-v8` is **not** in `devDependencies`; no lockfile; `vitest ^5.0.2` version unverified against the registry | G0/G1/G8 | OPEN |
| 2 | `CODE_OF_CONDUCT.md` missing — needs an owner decision | G4 | OPEN |
| 3 | Repo-wide `ruff` backlog; CI lint is non-blocking, so G2 is enforced on changed files only. 26 findings remain in `valuation.py` (9) and `visuals.py` (17), all pre-existing and unchanged-or-improved by this change | G2 | OPEN |
| 4 | ~~`/api/research/data` bundle key names undocumented in `docs/API-REFERENCE.md`~~ | G9 | **CLOSED by this change** — bundle schema section added, with tests binding docs to payload |
| 5 | `docs/` guide set not audited against the required list; no HTML docs build | G9 | OPEN |
| 6 | Decision log lives outside the repo, so not contributor-visible | G7 | ACCEPTED (with note) |
| 7 | `us_10y_yield` falls back to a hardcoded `risk_free_rate` instead of a live observation. The split Treasury rows now state the benchmark honestly, but the *source* is still a constant — same class of problem as the old conflated row. Needs a provider decision, not a patch | G1 | OPEN |
| 8 | `peer_median_yield` is computed over the whole competitor universe while `peers` ships at most 8 rows. `peer_yields` (per-peer yields) is now exported so the median is reproducible *for the peers shown*, but the two populations still differ. Either export the full universe or state the population explicitly in the caption | G1 | OPEN |
| 9 | Scenario assumption constants are still hardcoded (±3pp operating margin, ×1.2/×0.8 multiple) in `engines/valuation.py`. Deliberately deferred to the `quant/` Python port so `trends` and `sensitivityGrid` are reused rather than reimplemented | G1 | DEFERRED (by decision) |
| 10 | Low-but-positive peer P/E values (e.g. CHTR 2.9x) render as real numbers. Only non-positive P/E is treated as `n/m`. Decided against automatic outlier suppression — a genuine low multiple should stay visible | G1 | DEFERRED (by decision) |
| 11 | Removing `metrics.payout_ratio` is a breaking change to a paid API. | G6 | **CLOSED — owner confirmed the clean break** (2026-09-27). Rationale recorded: the key was `null` on every real bundle, so no consumer was reading a real value from it, and retaining a single ambiguous payout figure is the defect being fixed. `schema_version` 1.0 → 1.1 plus the CHANGELOG entry carries the signal. |

