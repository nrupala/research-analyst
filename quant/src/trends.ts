// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

/**
 * trends.ts — Module M1: growth, trajectory and per-share analysis.
 *
 * Pure functions over aligned oldest→newest `Series`. Nulls in, nulls out:
 * missing data propagates as null, never 0, never NaN. Zero dependencies.
 */

import type { Series } from "./types.js";

/** Trend direction derived from a log-linear regression slope. */
export type TrendDirection = "up" | "down" | "flat";

/** Result of a log-linear (exponential) trend fit. */
export interface LogLinearTrend {
  /**
   * Continuously-compounded per-period growth rate. For small slopes this is
   * ≈ the plain growth rate (a slope of 0.095 means ≈10% growth per period).
   */
  slope: number;
  /** Goodness of fit on the log scale, in [0, 1]. 1 for a constant series. */
  rSquared: number;
  /** "flat" when |slope| < 0.005, else "up"/"down" by sign. */
  direction: TrendDirection;
}

/** Buyback-flattery gap between total and per-share growth. */
export interface FlatteryResult {
  /** (perShareGrowth − totalGrowth) × 100, in percentage points. */
  gapPts: number;
  /** Plain-language reading of the gap (see `flattery`). */
  interpretation: string;
}

/**
 * Compound per-period growth rate.
 *
 * Formula: CAGR = (last / first)^(1 / periods) − 1.
 *
 * Returns null when either endpoint is missing (null) or non-finite, when
 * `first <= 0` (a growth rate is undefined off a non-positive base), when
 * `periods <= 0`, or when the result is not a finite real number (e.g. a
 * negative `last` makes the ratio negative and its fractional power undefined
 * on the reals).
 *
 * This is the standard geometric-mean growth rate used across investment
 * analysis (CFA Institute curriculum; "compound annual growth rate"). It
 * answers: "what constant per-period rate compounds `first` into `last`?" It
 * smooths over the path taken, so pair it with `yoyGrowth` or
 * `logLinearTrend` when the trajectory itself matters.
 */
export function cagr(
  first: number | null,
  last: number | null,
  periods: number,
): number | null {
  if (first === null || last === null) return null;
  if (!Number.isFinite(first) || !Number.isFinite(last)) return null;
  if (!Number.isFinite(periods) || periods <= 0) return null;
  if (first <= 0) return null;
  const result = Math.pow(last / first, 1 / periods) - 1;
  return Number.isFinite(result) ? result : null;
}

/**
 * CAGR between the first and last non-null values of a series.
 *
 * Uses the index distance between those two points as `periods`, so gaps in
 * the middle do not shorten the horizon — a null period is treated as missing
 * data, not as zero. Non-finite values (NaN, ±Infinity) are treated as
 * missing, consistent with `defined` in guards.ts.
 *
 * Returns null when fewer than two non-null points exist.
 *
 * Note: endpoints only. A one-off spike at either end moves this number a
 * lot; `logLinearTrend` fits the whole trajectory instead.
 */
export function seriesCagr(values: Series): number | null {
  let firstIdx = -1;
  let lastIdx = -1;
  let first: number | null = null;
  let last: number | null = null;
  for (let i = 0; i < values.length; i++) {
    const v: number | null | undefined = values[i];
    if (v !== null && v !== undefined && Number.isFinite(v)) {
      if (firstIdx < 0) {
        firstIdx = i;
        first = v;
      }
      lastIdx = i;
      last = v;
    }
  }
  if (firstIdx < 0 || lastIdx <= firstIdx) return null;
  return cagr(first, last, lastIdx - firstIdx);
}

/**
 * Period-over-period growth: g[i] = values[i] / values[i-1] − 1.
 *
 * Element i is null when either endpoint is missing (null) or non-finite, or
 * when the base values[i-1] <= 0. Element 0 is always null (no prior period).
 * The returned series has the same length as the input.
 *
 * Invariant: compounding the non-null growth rates reconstructs the series —
 * values[n-1] = values[0] × Π(1 + g[i]) over the non-null g[i]. (Covered by a
 * test; it is the discrete-time counterpart of the CAGR definition.)
 */
export function yoyGrowth(values: Series): Series {
  const out: Series = new Array(values.length).fill(null);
  for (let i = 1; i < values.length; i++) {
    const prev: number | null | undefined = values[i - 1];
    const cur: number | null | undefined = values[i];
    if (
      prev === null ||
      prev === undefined ||
      cur === null ||
      cur === undefined ||
      !Number.isFinite(prev) ||
      !Number.isFinite(cur) ||
      prev <= 0
    ) {
      continue; // stays null
    }
    const g = cur / prev - 1;
    out[i] = Number.isFinite(g) ? g : null;
  }
  return out;
}

/**
 * Exponential trend fit: ordinary least-squares regression of ln(value) on
 * the time index t = 0..n−1, using only positive, finite, non-null values.
 * Each usable value keeps its original series index, so gaps do not compress
 * the time axis.
 *
 * Formulae (standard OLS, y = ln(value)):
 *   slope     = (n·Σty − Σt·Σy) / (n·Σt² − (Σt)²)
 *   intercept = ȳ − slope·t̄
 *   R²        = 1 − Σ(y − ŷ)² / Σ(y − ȳ)²
 *
 * Interpretation: by the chain rule, d/dt ln V = (1/V)·dV/dt, so `slope` is
 * the continuously-compounded per-period growth rate — approximately the
 * plain growth rate when it is small. `direction` is "flat" when
 * |slope| < 0.005 (under 0.5% per period), otherwise "up"/"down" by sign.
 *
 * Returns null when fewer than 3 usable points exist. For a constant series
 * the R² denominator is 0; by convention it reports 1 (a perfect flat fit).
 * R² is clamped to [0, 1] against floating-point dust.
 *
 * This is the standard log-linear (least-squares-on-log-scale) growth
 * estimator used in econometrics for estimating constant growth rates (e.g.
 * Greene, *Econometric Analysis*). Unlike CAGR it fits every data point, so
 * it is less hostage to endpoint spikes.
 */
export function logLinearTrend(values: Series): LogLinearTrend | null {
  // (t, ln v) points; t keeps the original series index.
  const pts: { t: number; y: number }[] = [];
  for (let t = 0; t < values.length; t++) {
    const v: number | null | undefined = values[t];
    if (v !== null && v !== undefined && Number.isFinite(v) && v > 0) {
      pts.push({ t, y: Math.log(v) });
    }
  }
  const n = pts.length;
  if (n < 3) return null;

  let sumT = 0;
  let sumY = 0;
  let sumTT = 0;
  let sumTY = 0;
  for (const p of pts) {
    sumT += p.t;
    sumY += p.y;
    sumTT += p.t * p.t;
    sumTY += p.t * p.y;
  }

  const denom = n * sumTT - sumT * sumT;
  if (denom === 0 || !Number.isFinite(denom)) return null;

  const slope = (n * sumTY - sumT * sumY) / denom;
  const meanY = sumY / n;
  const intercept = meanY - slope * (sumT / n);
  if (!Number.isFinite(slope) || !Number.isFinite(intercept)) return null;

  let ssRes = 0;
  let ssTot = 0;
  for (const p of pts) {
    const fitted = slope * p.t + intercept;
    ssRes += (p.y - fitted) * (p.y - fitted);
    ssTot += (p.y - meanY) * (p.y - meanY);
  }
  let rSquared = ssTot === 0 ? 1 : 1 - ssRes / ssTot;
  rSquared = Math.min(1, Math.max(0, rSquared));

  const direction: TrendDirection =
    Math.abs(slope) < 0.005 ? "flat" : slope > 0 ? "up" : "down";
  return { slope, rSquared, direction };
}

/**
 * Element-wise per-share series: values[i] / shares[i].
 *
 * Null-safe: null wherever either side is missing (null) or non-finite, or
 * shares[i] <= 0. Output length is the longer of the two inputs (missing
 * positions stay null).
 *
 * Use for EPS, FCF/share, book value/share — the per-share view that makes
 * buyback and issuance effects visible. Compare with the total series via
 * `flattery` to see whether per-share growth is earned or engineered.
 */
export function perShareSeries(values: Series, shares: Series): Series {
  const n = Math.max(values.length, shares.length);
  const out: Series = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    const v: number | null | undefined = values[i];
    const s: number | null | undefined = shares[i];
    if (
      v === null ||
      v === undefined ||
      s === null ||
      s === undefined ||
      !Number.isFinite(v) ||
      !Number.isFinite(s) ||
      s <= 0
    ) {
      continue; // stays null
    }
    const q = v / s;
    out[i] = Number.isFinite(q) ? q : null;
  }
  return out;
}

/**
 * Element-wise margin: numerator[i] / revenue[i].
 *
 * Null-safe: null wherever either side is missing (null) or non-finite, or
 * revenue[i] <= 0 (margins are undefined on non-positive revenue). Output
 * length is the longer of the two inputs.
 *
 * Gross margin, operating margin and net margin are all this function with
 * different numerators. Keep margins as fractions (0.3 = 30%) inside the
 * engine; format at the boundary.
 */
export function marginSeries(numerator: Series, revenue: Series): Series {
  const n = Math.max(numerator.length, revenue.length);
  const out: Series = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    const num: number | null | undefined = numerator[i];
    const rev: number | null | undefined = revenue[i];
    if (
      num === null ||
      num === undefined ||
      rev === null ||
      rev === undefined ||
      !Number.isFinite(num) ||
      !Number.isFinite(rev) ||
      rev <= 0
    ) {
      continue; // stays null
    }
    const m = num / rev;
    out[i] = Number.isFinite(m) ? m : null;
  }
  return out;
}

/**
 * Buyback-flattery gap between total and per-share growth.
 *
 * gapPts = (perShareGrowth − totalGrowth) × 100, in percentage points.
 *
 * Interpretation:
 * - gap >  1 → "per-share growth exceeds total growth — buybacks are
 *   flattering the per-share number" (fewer shares, same profit: the per-share
 *   number outruns the business).
 * - gap < −1 → "per-share growth lags — dilution or share issuance" (share
 *   count growth is eating the underlying growth).
 * - otherwise → "per-share and total growth are aligned".
 *
 * Returns null when either input is missing (null) or non-finite.
 *
 * This encodes the well-documented critique that share repurchases inflate
 * per-share growth metrics (EPS, FCF/share) relative to the underlying
 * business — the reason serious analysis compares the total and per-share
 * series rather than trusting the per-share number alone.
 */
export function flattery(
  totalGrowth: number | null,
  perShareGrowth: number | null,
): FlatteryResult | null {
  if (totalGrowth === null || perShareGrowth === null) return null;
  if (!Number.isFinite(totalGrowth) || !Number.isFinite(perShareGrowth)) {
    return null;
  }
  const gapPts = (perShareGrowth - totalGrowth) * 100;
  if (!Number.isFinite(gapPts)) return null;
  let interpretation: string;
  if (gapPts > 1) {
    interpretation =
      "per-share growth exceeds total growth — buybacks are flattering the per-share number";
  } else if (gapPts < -1) {
    interpretation = "per-share growth lags — dilution or share issuance";
  } else {
    interpretation = "per-share and total growth are aligned";
  }
  return { gapPts, interpretation };
}
