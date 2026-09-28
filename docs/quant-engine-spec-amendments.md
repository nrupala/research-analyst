# Quant Engine — Spec Amendments (locked 2026-09-28)

These amend the `quant/` TypeScript reference where it is wrong. The Python
port implements THIS spec, not the TS as-is. Each amendment states the old
behavior, why it is wrong, and the corrected rule.

## A1. Operating tax rate / NOPAT (affects: allocation.incrementalRoic, damodaran lens)

**Old (TS):** `taxRate = (ebit − netIncome) / ebit`, null unless `ebit > 0`.

**Why wrong:** `(ebit − ni)/ebit = (interestExpense + taxExpense + nonOperating)/ebit`.
It folds the interest tax shield and non-operating items into the *operating*
tax rate, so NOPAT = EBIT×(1−t) is computed with a polluted rate. Damodaran
(Investment Valuation): NOPAT uses the tax rate on *operating* income.

**Corrected:**
```
pretaxOperating_t = ebit_t − interestExpense_t        # interest is a positive magnitude
t_t = taxExpense_t / pretaxOperating_t
NOPAT_t = ebit_t × (1 − t_t)
```
`t_t` is null unless `ebit_t > 0`, `pretaxOperating_t > 0`, and `0 ≤ t_t ≤ 1`
(a rate outside [0,1] is a data artifact, not a rate — missing stays missing,
never clamped into a fabricated number). `incrementalRoic` uses per-period
`t_t`; an interval is null when either endpoint's `t` is null. The old
`(ebit − ni)/ebit` formula is removed, not kept as a fallback.

## A2. Implied-growth labeling (affects: valuation.reverseDcf, damodaran.impliedGrowth)

**Old (TS):** two different inversions both describable as "implied growth".

**Why wrong:** they answer different questions and must never share a label.
- `reverseDcf`: bisection for the *constant explicit-stage* growth rate `g`
  over `years` explicit stages, with a Gordon terminal after. Answers: "what
  near-term growth must the business deliver for today's EV to be fair?"
- `lenses/damodaran.impliedGrowth`: algebraic inversion of the *one-period*
  Gordon model, `g = (EV×r − FCF)/(EV + FCF)`. Answers: "what *perpetual*
  growth is today's EV already pricing in?"

**Corrected labels (used in code, API, report, UI):**
- `reverseDcf` → **"implied explicit-stage growth"**
- `impliedGrowth` (Gordon algebra) → **"implied perpetual growth"**

Both render with their formula visible. Never a bare "implied growth".