// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * Small null-safe guards shared by every quant module.
 * The engine's contract: nulls in, nulls out — never throw on data gaps.
 */

import type { Series } from "./types.js";

/** Non-null values of a series, in order. */
export function defined(values: Series): number[] {
  const out: number[] = [];
  for (const v of values) if (v !== null && Number.isFinite(v)) out.push(v);
  return out;
}

/** Last non-null value, or null when the series is empty. */
export function lastValue(values: Series): number | null {
  for (let i = values.length - 1; i >= 0; i--) {
    const v: number | null | undefined = values[i];
    if (v !== null && v !== undefined && Number.isFinite(v)) return v;
  }
  return null;
}

/** First non-null value, or null when the series is empty. */
export function firstValue(values: Series): number | null {
  for (let i = 0; i < values.length; i++) {
    const v: number | null | undefined = values[i];
    if (v !== null && v !== undefined && Number.isFinite(v)) return v;
  }
  return null;
}

/** Element-wise division; null wherever either side is missing or divisor is 0. */
export function divSeries(num: Series, den: Series): Series {
  const n = Math.max(num.length, den.length);
  const out: Series = new Array(n);
  for (let i = 0; i < n; i++) {
    const a = num[i] ?? null;
    const b = den[i] ?? null;
    out[i] = a !== null && b !== null && b !== 0 ? a / b : null;
  }
  return out;
}

/** Safe division of two scalars. */
export function div(a: number | null, b: number | null): number | null {
  if (a === null || b === null || b === 0) return null;
  return a / b;
}

/** Arithmetic mean of non-null values; null when empty. */
export function mean(values: Series): number | null {
  const d = defined(values);
  if (d.length === 0) return null;
  let sum = 0;
  for (const v of d) sum += v;
  return sum / d.length;
}
