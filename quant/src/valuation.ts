// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * valuation.ts — cost of capital and intrinsic-value mathematics.
 *
 * Pure functions over scalars and short arrays: CAPM cost of equity,
 * WACC, a two-stage free-cash-flow DCF with a Gordon-growth terminal
 * value, reverse DCF (implied growth via bisection), historical multiple
 * percentiles, and a two-dimensional sensitivity grid.
 *
 * Nulls in, nulls out — every function returns null (rather than
 * throwing) when a required input is missing or a guard is violated, so
 * report renderers can print "data unavailable" instead of a fabricated
 * number. Research/education only: nothing here is a buy/sell signal.
 */

import { defined } from "./guards.js";
import type { Series } from "./types.js";

/**
 * Cost of equity from the Sharpe–Lintner–Mossin CAPM.
 *
 * Formula: re = rf + β × ERP
 * Source: Sharpe (1964), Lintner (1965), Mossin (1966).
 *
 * Null semantics: null when any input is null or non-finite — equity
 * cannot be priced on risk the caller cannot observe.
 */
export function capmCostOfEquity(
  riskFree: number | null,
  beta: number | null,
  equityRiskPremium: number | null,
): number | null {
  if (
    riskFree === null ||
    beta === null ||
    equityRiskPremium === null ||
    !Number.isFinite(riskFree) ||
    !Number.isFinite(beta) ||
    !Number.isFinite(equityRiskPremium)
  ) {
    return null;
  }
  return riskFree + beta * equityRiskPremium;
}

/**
 * Weighted average cost of capital.
 *
 * Formula: WACC = re × (E / V) + rd × (1 − t) × (D / V),  V = E + D
 *
 * Null semantics: null when any input is null/non-finite, or when
 * V = E + D ≤ 0 (there is no observable capital base to weight).
 */
export function wacc(
  costOfEquity: number | null,
  costOfDebt: number | null,
  taxRate: number | null,
  marketEquity: number | null,
  marketDebt: number | null,
): number | null {
  if (
    costOfEquity === null ||
    costOfDebt === null ||
    taxRate === null ||
    marketEquity === null ||
    marketDebt === null ||
    !Number.isFinite(costOfEquity) ||
    !Number.isFinite(costOfDebt) ||
    !Number.isFinite(taxRate) ||
    !Number.isFinite(marketEquity) ||
    !Number.isFinite(marketDebt)
  ) {
    return null;
  }
  const v = marketEquity + marketDebt;
  if (v <= 0) return null;
  return (
    (costOfEquity * marketEquity) / v +
    (costOfDebt * (1 - taxRate) * marketDebt) / v
  );
}

/** Result of {@link dcf}. */
export interface DcfResult {
  /** Present value of the whole projection: pvExplicit + pvTerminal. */
  enterpriseValue: number;
  /** Σ FCF_t / (1+r)^t over the explicit period. */
  pvExplicit: number;
  /** TV_n / (1+r)^n, the discounted Gordon terminal value. */
  pvTerminal: number;
  /** The explicit-period free cash flows, undiscounted, oldest → newest. */
  cashFlows: (number | null)[];
}

/**
 * Two-stage free-cash-flow DCF with a Gordon-growth terminal value.
 *
 * Explicit period (t = 1..n, n = growthRates.length):
 *   FCF_t = fcf0 × Π_{i=1..t} (1 + g_i)
 * Terminal value at year n (Gordon & Shapiro, 1956):
 *   TV_n = FCF_n × (1 + g) / (r − g)
 * Enterprise value:
 *   EV = Σ_{t=1..n} FCF_t / (1 + r)^t  +  TV_n / (1 + r)^n
 *
 * Null semantics: null when fcf0, discountRate or terminalGrowth is
 * null/non-finite, when growthRates is empty, when any growth rate is
 * non-finite, or when discountRate ≤ terminalGrowth — the Gordon series
 * diverges there, so the terminal value would be infinite or negative.
 */
export function dcf(
  fcf0: number | null,
  growthRates: number[],
  discountRate: number | null,
  terminalGrowth: number | null,
): DcfResult | null {
  if (
    fcf0 === null ||
    discountRate === null ||
    terminalGrowth === null ||
    !Number.isFinite(fcf0) ||
    !Number.isFinite(discountRate) ||
    !Number.isFinite(terminalGrowth) ||
    growthRates.length === 0 ||
    discountRate <= terminalGrowth
  ) {
    return null;
  }
  const cashFlows: number[] = [];
  let fcf = fcf0;
  for (const g of growthRates) {
    if (!Number.isFinite(g)) return null;
    fcf = fcf * (1 + g);
    cashFlows.push(fcf);
  }
  let pvExplicit = 0;
  let discountFactor = 1; // (1 + r)^t after t iterations
  for (const cf of cashFlows) {
    discountFactor *= 1 + discountRate;
    pvExplicit += cf / discountFactor;
  }
  // cashFlows is non-empty (growthRates was non-empty), so .at(-1) is defined.
  const lastFcf = cashFlows.at(-1);
  if (lastFcf === undefined) return null;
  const terminalValue =
    (lastFcf * (1 + terminalGrowth)) / (discountRate - terminalGrowth);
  const pvTerminal = terminalValue / discountFactor; // discountFactor is (1+r)^n now
  return {
    enterpriseValue: pvExplicit + pvTerminal,
    pvExplicit,
    pvTerminal,
    cashFlows,
  };
}

/** Result of {@link reverseDcf}. */
export interface ReverseDcfResult {
  /**
   * The constant explicit-period growth rate that prices the DCF at the
   * current enterprise value. Clamped to the searched interval
   * [-0.5, 1.0] when the value lies outside the model's range.
   */
  impliedGrowth: number;
  /** True when |dcf(impliedGrowth) − currentEV| / currentEV < 1e-6. */
  converged: boolean;
}

/** Search interval for the implied growth rate (see {@link reverseDcf}). */
const REVERSE_DCF_MIN_GROWTH = -0.5;
const REVERSE_DCF_MAX_GROWTH = 1.0;
/** Bisection iterations — the bracket shrinks by 2^100, far past float precision. */
const REVERSE_DCF_ITERATIONS = 100;
/** Relative tolerance on enterprise value for convergence. */
const REVERSE_DCF_TOLERANCE = 1e-6;

/**
 * Reverse DCF: the constant explicit-period growth rate g implied by the
 * market's current enterprise value.
 *
 * Inverts {@link dcf} by bisection (intermediate value theorem): with
 * growthRates = [g, g, …, g] (years entries), EV(g) is continuous in g,
 * so the equation dcf(g) = currentEV is solved by halving the bracket
 * [−0.5, 1.0] 100 times. Handles both increasing (fcf0 > 0) and
 * decreasing (fcf0 < 0) EV(g) orderings.
 *
 * When currentEV lies outside the model's range on [−0.5, 1.0] there is
 * no in-interval root; the function returns the nearest bound with
 * converged: false rather than inventing a growth rate outside the
 * searched interval.
 *
 * Null semantics: null when currentEV is null/non-finite or ≤ 0, when
 * years is not a positive integer, or when any dcf guard fails
 * (fcf0 / discountRate / terminalGrowth missing, or r ≤ terminalGrowth).
 */
export function reverseDcf(
  currentEV: number | null,
  fcf0: number | null,
  discountRate: number | null,
  terminalGrowth: number | null,
  years: number,
): ReverseDcfResult | null {
  if (
    currentEV === null ||
    !Number.isFinite(currentEV) ||
    currentEV <= 0 ||
    !Number.isInteger(years) ||
    years < 1
  ) {
    return null;
  }
  const evAt = (g: number): number | null => {
    const growthRates = new Array<number>(years).fill(g);
    const result = dcf(fcf0, growthRates, discountRate, terminalGrowth);
    return result === null ? null : result.enterpriseValue;
  };
  // Probe the bracket ends first: this also enforces dcf's own guards.
  const evLo = evAt(REVERSE_DCF_MIN_GROWTH);
  const evHi = evAt(REVERSE_DCF_MAX_GROWTH);
  if (evLo === null || evHi === null) return null;
  const resLo = evLo - currentEV;
  const resHi = evHi - currentEV;
  // currentEV outside the model's range on the interval: no in-bracket root.
  if (resLo > 0 && resHi > 0) {
    return { impliedGrowth: REVERSE_DCF_MIN_GROWTH, converged: false };
  }
  if (resLo < 0 && resHi < 0) {
    return { impliedGrowth: REVERSE_DCF_MAX_GROWTH, converged: false };
  }
  let lo = REVERSE_DCF_MIN_GROWTH;
  let hi = REVERSE_DCF_MAX_GROWTH;
  let resAtLo = resLo;
  for (let i = 0; i < REVERSE_DCF_ITERATIONS; i++) {
    const mid = (lo + hi) / 2;
    const evMid = evAt(mid);
    if (evMid === null) return null; // unreachable: dcf is valid on the whole bracket
    const resMid = evMid - currentEV;
    if (resMid === 0) {
      lo = mid;
      hi = mid;
      break;
    }
    // Keep the half-bracket whose ends straddle zero.
    if (
      (resAtLo <= 0 && resMid <= 0) ||
      (resAtLo >= 0 && resMid >= 0)
    ) {
      lo = mid;
      resAtLo = resMid;
    } else {
      hi = mid;
    }
  }
  const impliedGrowth = (lo + hi) / 2;
  const evImplied = evAt(impliedGrowth);
  if (evImplied === null) return null; // unreachable, same as above
  const converged =
    Math.abs(evImplied - currentEV) / currentEV < REVERSE_DCF_TOLERANCE;
  return { impliedGrowth, converged };
}

/**
 * Historical percentile of a current multiple (e.g. P/E, EV/EBITDA).
 *
 * Formula: 100 × |{ h ∈ history : h ≤ current }| / |history|,
 * over the non-null, finite values of history.
 *
 * Null semantics: null when current is null/non-finite, or when history
 * has no observable values to rank against.
 */
export function multiplePercentile(
  current: number | null,
  history: Series,
): number | null {
  if (current === null || !Number.isFinite(current)) return null;
  const past = defined(history);
  if (past.length === 0) return null;
  let atOrBelow = 0;
  for (const v of past) {
    if (v <= current) atOrBelow++;
  }
  return (100 * atOrBelow) / past.length;
}

/** Result of {@link sensitivityGrid}. */
export interface SensitivityGrid {
  /** varyA.values, in order — the row axis. */
  rowLabels: number[];
  /** varyB.values, in order — the column axis. */
  colLabels: number[];
  /** values[i][j] = model with varyA = rowLabels[i], varyB = colLabels[j]. */
  values: (number | null)[][];
}

/**
 * Two-dimensional sensitivity grid: evaluates model() over the Cartesian
 * product varyA.values (rows) × varyB.values (columns), holding every
 * other input at its base value.
 *
 * Null semantics: a cell is null wherever the model returns null for
 * that input combination; the grid itself is always returned.
 */
export function sensitivityGrid<T extends Record<string, number | null>>(
  base: T,
  varyA: { name: keyof T & string; values: number[] },
  varyB: { name: keyof T & string; values: number[] },
  model: (inputs: T) => number | null,
): SensitivityGrid {
  const rowLabels = [...varyA.values];
  const colLabels = [...varyB.values];
  const values: (number | null)[][] = [];
  for (const a of varyA.values) {
    const row: (number | null)[] = [];
    for (const b of varyB.values) {
      const inputs: Record<string, number | null> = { ...base };
      inputs[varyA.name] = a;
      inputs[varyB.name] = b;
      row.push(model(inputs as T));
    }
    values.push(row);
  }
  return { rowLabels, colLabels, values };
}
