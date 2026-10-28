// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * lenses/util.ts — small internal math helpers shared by the lens modules.
 * Not part of the public lens API surface; tests may import it directly.
 */

import { seriesCagr } from "../allocation.js";
import type { Series } from "../types.js";

export { seriesCagr };

/**
 * Population standard deviation of a sample. Null when empty.
 * Population (÷ n) is used deliberately: these are complete observed
 * windows, not samples drawn for inference.
 */
export function stddev(values: number[]): number | null {
  if (values.length === 0) return null;
  let sum = 0;
  for (const v of values) sum += v;
  const m = sum / values.length;
  let sq = 0;
  for (const v of values) sq += (v - m) * (v - m);
  return Math.sqrt(sq / values.length);
}

/**
 * Coefficient of variation = stddev / |mean|. A scale-free dispersion
 * measure: 0.10 means the series typically varies ±10% around its mean.
 * Null when empty or when the mean is 0.
 */
export function coefVar(values: number[]): number | null {
  if (values.length === 0) return null;
  let sum = 0;
  for (const v of values) sum += v;
  const m = sum / values.length;
  if (m === 0) return null;
  const sd = stddev(values);
  return sd === null ? null : sd / Math.abs(m);
}

/**
 * Percentile rank of x within a reference set, 0–100.
 * Formula: (count(v < x) + 0.5 × count(v == x)) / n × 100.
 * Null when the reference set is empty.
 */
export function percentileRank(values: number[], x: number): number | null {
  if (values.length === 0) return null;
  let less = 0;
  let equal = 0;
  for (const v of values) {
    if (v < x) less++;
    else if (v === x) equal++;
  }
  return ((less + 0.5 * equal) / values.length) * 100;
}

/**
 * Count of sign flips between consecutive non-zero values; zeros are
 * skipped (a zero is "no signal", not a sign). Used for the Lynch
 * cyclical screen.
 */
export function signChanges(values: number[]): number {
  let count = 0;
  let prev = 0;
  let havePrev = false;
  for (const v of values) {
    const sgn = Math.sign(v);
    if (sgn === 0) continue;
    if (havePrev && sgn !== prev) count++;
    prev = sgn;
    havePrev = true;
  }
  return count;
}

/** Non-null values of a series with their period indices (oldest → newest). */
export function indexedDefined(values: Series): { index: number; value: number }[] {
  const out: { index: number; value: number }[] = [];
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v !== null && v !== undefined && Number.isFinite(v)) out.push({ index: i, value: v });
  }
  return out;
}

/** Format a decimal ratio as percent, or "n/a" when null. */
export function fmtPct(x: number | null, digits = 1): string {
  return x === null ? "n/a" : `${(x * 100).toFixed(digits)}%`;
}

/** Format a plain number, or "n/a" when null. */
export function fmtNum(x: number | null, digits = 2): string {
  return x === null ? "n/a" : x.toFixed(digits);
}

/** Format a currency amount with 2 decimals, or "n/a" when null. */
export function fmtMoney(x: number | null): string {
  return x === null ? "n/a" : x.toFixed(2);
}
