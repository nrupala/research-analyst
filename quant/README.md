# ra-quant — Research Analyst Analytical Engine

Pure-function quantitative analysis over multi-year financial statement series.
Numbers in, numbers out. No I/O, no network, no advice.

## The contract

Every module consumes a `StatementSeries` (see `src/types.ts`):

- One ticker, N fiscal periods, **oldest → newest**.
- Every line item is an aligned `(number | null)[]`. Missing data is `null`,
  never `0`.
- **Sign convention:** cash-flow outflows (capex, buybacks, dividends) are
  **positive magnitudes**. `$32.1B` of capex is `32100000000`.
- Units are plain numbers in the statement currency. Scale at the boundary.

## Design laws

1. Pure functions only.
2. Nulls in, nulls out — never throw on data gaps.
3. Every exported function documents its formula + canonical source.
4. No narrative, no recommendations. The engine cannot tell anyone to buy or sell.

## Layout

- `src/types.ts` — the `StatementSeries` contract + validation.
- `src/guards.ts` — null-safe math helpers.
- `src/trends.ts` — growth, trajectories, per-share analysis (Phase B).
- `src/dupont.ts`, `src/forensics.ts` — ROE decomposition, Sloan/Altman/Beneish (Phase C).
- `src/valuation.ts` — WACC, DCF, reverse DCF, sensitivities (Phase D).
- `src/allocation.ts` — buyback/dividend/debt track record (Phase E).
- `src/expected.ts` — probability-weighted scenarios (Phase F).

## Develop

```sh
npm install
npm run typecheck   # tsc --noEmit, strict
npm run test        # vitest run
npm run build       # emit to dist/
```

## License

AGPL-3.0-or-later. See the repository root LICENSE.
