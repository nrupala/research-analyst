// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * expected.ts — probability-weighted expectation and break-even math.
 *
 * Pure functions: scenario expected value with strict probability
 * validation, one-at-a-time sensitivity (tornado), Graham's margin of
 * safety, and a bisection root-finder for "what input hits this target?".
 *
 * Nulls in, nulls out — functions return null (or a descriptive error
 * for expectedValue) rather than throwing on missing or invalid data, so
 * report renderers can print "data unavailable" instead of a fabricated
 * number. Research/education only: nothing here is a buy/sell signal.
 */

/** One scenario for {@link expectedValue}. */
export interface ScenarioInput {
  label: string;
  value: number | null;
  probability: number | null;
}

/** Successful result of {@link expectedValue}. */
export interface ExpectedValueResult {
  /** Σ value_i × probability_i. */
  expected: number;
  /** Per-scenario value_i × probability_i, in input order. */
  contributions: { label: string; contribution: number }[];
}

/**
 * Probability-sum tolerance: Σp must equal 1 ± 0.01. A looser band would
 * silently mis-weight the scenarios; a tighter one would reject honest
 * rounding (e.g. 0.33 + 0.33 + 0.34).
 */
const PROBABILITY_SUM_TOLERANCE = 0.01;

/**
 * Probability-weighted expected value over discrete scenarios.
 *
 * Formula: E = Σ value_i × probability_i
 *
 * Validation (first violation wins, returned as { error }):
 *   1. at least one scenario,
 *   2. every value is present and finite,
 *   3. every probability is present and finite,
 *   4. every probability ≥ 0,
 *   5. Σp = 1 ± 0.01.
 *
 * The error branch exists so callers can surface *why* the expectation
 * is unavailable instead of silently dropping the scenarios.
 */
export function expectedValue(
  scenarios: ScenarioInput[],
): ExpectedValueResult | { error: string } {
  if (scenarios.length === 0) {
    return { error: "expectedValue: at least one scenario is required" };
  }
  const clean: { label: string; value: number; probability: number }[] = [];
  for (const s of scenarios) {
    if (s.value === null || !Number.isFinite(s.value)) {
      return {
        error: `expectedValue: scenario "${s.label}" has a missing value`,
      };
    }
    if (s.probability === null || !Number.isFinite(s.probability)) {
      return {
        error: `expectedValue: scenario "${s.label}" has a missing probability`,
      };
    }
    if (s.probability < 0) {
      return {
        error: `expectedValue: scenario "${s.label}" has negative probability ${s.probability}`,
      };
    }
    clean.push({ label: s.label, value: s.value, probability: s.probability });
  }
  let totalProbability = 0;
  for (const s of clean) totalProbability += s.probability;
  if (Math.abs(totalProbability - 1) > PROBABILITY_SUM_TOLERANCE) {
    return {
      error: `expectedValue: probabilities sum to ${totalProbability}, expected 1 ± ${PROBABILITY_SUM_TOLERANCE}`,
    };
  }
  let expected = 0;
  const contributions = clean.map((s) => {
    const contribution = s.value * s.probability;
    expected += contribution;
    return { label: s.label, contribution };
  });
  return { expected, contributions };
}

/** One row of {@link tornado}: a single input varied low → high. */
export interface TornadoRow {
  /** The varied input's name. */
  name: string;
  /** model() with this input at its low end, others at base. */
  lowOutput: number | null;
  /** model() with this input at its high end, others at base. */
  highOutput: number | null;
  /** |highOutput − lowOutput|; 0 when either end is null. */
  swing: number;
}

/**
 * One-at-a-time sensitivity ("tornado"): for each range, evaluate the
 * model with that input at low and at high while every other input stays
 * at its base value.
 *
 * Swing = |highOutput − lowOutput| (0 when either end is null), rows
 * sorted by descending swing so the largest driver of the output comes
 * first. Interaction effects are not captured — this is deliberately a
 * first-order screening, not a full factorial design.
 */
export function tornado<T extends Record<string, number | null>>(
  base: T,
  model: (inputs: T) => number | null,
  ranges: { name: keyof T & string; low: number; high: number }[],
): TornadoRow[] {
  const rows: TornadoRow[] = [];
  for (const r of ranges) {
    const lowInputs: Record<string, number | null> = { ...base };
    lowInputs[r.name] = r.low;
    const highInputs: Record<string, number | null> = { ...base };
    highInputs[r.name] = r.high;
    const lowOutput = model(lowInputs as T);
    const highOutput = model(highInputs as T);
    const swing =
      lowOutput !== null && highOutput !== null
        ? Math.abs(highOutput - lowOutput)
        : 0;
    rows.push({ name: r.name, lowOutput, highOutput, swing });
  }
  rows.sort((a, b) => b.swing - a.swing);
  return rows;
}

/**
 * Graham's margin of safety.
 *
 * Formula: MoS = (intrinsicValue − price) / intrinsicValue
 * Source: Graham (1949), The Intelligent Investor.
 *
 * Positive means the price sits below intrinsic value; negative means
 * above. Null semantics: null when intrinsicValue is null/non-finite or
 * ≤ 0 (a non-positive anchor cannot define a margin), or when price is
 * null/non-finite.
 */
export function marginOfSafety(
  intrinsicValue: number | null,
  price: number | null,
): number | null {
  if (
    intrinsicValue === null ||
    !Number.isFinite(intrinsicValue) ||
    intrinsicValue <= 0 ||
    price === null ||
    !Number.isFinite(price)
  ) {
    return null;
  }
  return (intrinsicValue - price) / intrinsicValue;
}

/** Result of {@link solveForInput}. */
export interface SolveForInputResult {
  /** The input x with model(x) ≈ target. */
  input: number;
  /**
   * True when |model(input) − target| ≤ 1e-9 × max(1, |target|) after
   * bisection. False means the model is discontinuous or flat on the
   * bracket and bisection could not pin the root.
   */
  converged: boolean;
}

/** Bisection iterations — the bracket shrinks by 2^100, far past float precision. */
const SOLVE_ITERATIONS = 100;

/**
 * Bisection root-finder: the input x in [lo, hi] with model(x) = target.
 *
 * Method: bisection (intermediate value theorem) — requires the target
 * to be bracketed, i.e. between model(lo) and model(hi) inclusive.
 * Works for both increasing and decreasing models; 100 iterations halve
 * the bracket far past float precision.
 *
 * Null semantics: null when model(lo) or model(hi) is null/non-finite,
 * when target is non-finite, when the target is not bracketed, or when
 * the model returns null at any probe point mid-search (a hole in the
 * model cannot be bisected through).
 */
export function solveForInput(
  model: (x: number) => number | null,
  target: number,
  lo: number,
  hi: number,
): SolveForInputResult | null {
  const fLo = model(lo);
  const fHi = model(hi);
  if (
    fLo === null ||
    fHi === null ||
    !Number.isFinite(fLo) ||
    !Number.isFinite(fHi) ||
    !Number.isFinite(target)
  ) {
    return null;
  }
  const bracketed =
    (fLo <= target && target <= fHi) || (fHi <= target && target <= fLo);
  if (!bracketed) return null;
  let a = lo;
  let b = hi;
  let fA = fLo;
  for (let i = 0; i < SOLVE_ITERATIONS; i++) {
    const mid = (a + b) / 2;
    const fMid = model(mid);
    if (fMid === null || !Number.isFinite(fMid)) return null;
    if (fMid === target) {
      a = mid;
      b = mid;
      fA = fMid;
      break;
    }
    // Keep the half-bracket whose ends straddle the target.
    if ((fA <= target && fMid <= target) || (fA >= target && fMid >= target)) {
      a = mid;
      fA = fMid;
    } else {
      b = mid;
    }
  }
  const input = (a + b) / 2;
  const fInput = model(input);
  if (fInput === null || !Number.isFinite(fInput)) return null;
  const converged =
    Math.abs(fInput - target) <= 1e-9 * Math.max(1, Math.abs(target));
  return { input, converged };
}
