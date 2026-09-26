// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

/**
 * dupont.ts — three-factor DuPont decomposition of return on equity.
 *
 *   ROE = (NI / Revenue) × (Revenue / AvgAssets) × (AvgAssets / AvgEquity)
 *       =  net margin  ×  asset turnover   ×  equity multiplier (leverage)
 *
 * (DuPont Corporation, 1920s; this three-factor form is the standard
 * textbook decomposition. A five-factor extension splitting the tax and
 * interest burden is out of scope for this module.)
 *
 * AVERAGING CONVENTION: flow/stock ratios use average balance-sheet
 * values, (current + prior) / 2. The first period has no prior, so it
 * uses the current value alone — flagged in the JSDoc of dupontSeries.
 *
 * Nulls in, nulls out: a period with any missing input yields nulls,
 * never an exception.
 */

import type { Series, StatementSeries } from "./types.js";
import { div } from "./guards.js";

/** Read index i of a series; undefined (out of range) becomes null. */
function at(values: Series, i: number): number | null {
  const v = values[i];
  return v === undefined ? null : v;
}

/** Mean of two scalars; null when either side is missing. */
function avg2(a: number | null, b: number | null): number | null {
  return a === null || b === null ? null : (a + b) / 2;
}

/**
 * One period of DuPont components. Any field may be null when that
 * period's inputs are incomplete (see dupontPoint).
 */
export interface DupontComponents {
  netMargin: number | null;
  assetTurnover: number | null;
  leverage: number | null;
  roe: number | null;
}

/** Fully-computed DuPont point: all four components are real numbers. */
export interface DupontPoint {
  netMargin: number;
  assetTurnover: number;
  leverage: number;
  roe: number;
}

/**
 * Three-factor DuPont decomposition for a single period.
 *
 * Formulas: netMargin = netIncome / revenue;
 * assetTurnover = revenue / avgAssets;
 * leverage = avgAssets / avgEquity;
 * roe = netIncome / avgEquity (= the product of the three, algebraically).
 *
 * @returns the four components, or null when any input is null, when
 * revenue is 0, or when avgAssets / avgEquity are not positive
 * (a non-positive equity base makes ROE undefined).
 */
export function dupontPoint(
  netIncome: number | null,
  revenue: number | null,
  avgAssets: number | null,
  avgEquity: number | null,
): DupontPoint | null {
  if (
    netIncome === null ||
    revenue === null ||
    avgAssets === null ||
    avgEquity === null
  ) {
    return null;
  }
  if (avgAssets <= 0 || avgEquity <= 0) return null;
  const netMargin = div(netIncome, revenue);
  const assetTurnover = div(revenue, avgAssets);
  const leverage = div(avgAssets, avgEquity);
  const roe = div(netIncome, avgEquity);
  if (
    netMargin === null ||
    assetTurnover === null ||
    leverage === null ||
    roe === null
  ) {
    return null;
  }
  return { netMargin, assetTurnover, leverage, roe };
}

/** One row of dupontSeries: the period label plus its DuPont components. */
export interface DupontRow extends DupontComponents {
  period: string;
}

/**
 * Per-period DuPont decomposition over the whole series (oldest → newest).
 *
 * Averages are (current + prior) / 2. The FIRST period has no prior
 * period, so it uses the current balance-sheet values alone (not a
 * two-period average) — its turnover and leverage are therefore
 * point-in-time, not averaged.
 *
 * @returns one row per period; a row is all-null when that period's
 * inputs are incomplete.
 */
export function dupontSeries(s: StatementSeries): DupontRow[] {
  const rows: DupontRow[] = [];
  for (let i = 0; i < s.periods.length; i++) {
    const avgAssets =
      i === 0 ? at(s.totalAssets, 0) : avg2(at(s.totalAssets, i), at(s.totalAssets, i - 1));
    const avgEquity =
      i === 0 ? at(s.totalEquity, 0) : avg2(at(s.totalEquity, i), at(s.totalEquity, i - 1));
    const p = dupontPoint(at(s.netIncome, i), at(s.revenue, i), avgAssets, avgEquity);
    const label = s.periods[i];
    rows.push({
      period: label === undefined ? `period-${i}` : label.period,
      netMargin: p === null ? null : p.netMargin,
      assetTurnover: p === null ? null : p.assetTurnover,
      leverage: p === null ? null : p.leverage,
      roe: p === null ? null : p.roe,
    });
  }
  return rows;
}

/** Percentage-point contributions of each DuPont factor to a ROE change. */
export interface RoeAttribution {
  marginPts: number;
  turnoverPts: number;
  leveragePts: number;
}

/**
 * Logarithmic attribution of a ROE change to its three DuPont factors.
 *
 * Formula (per factor): contribution_i =
 *   ln(component_last / component_first) / ln(roe_last / roe_first)
 *   × (roe_last − roe_first) × 100
 * in percentage points. The three contributions sum to the ROE change
 * in percentage points. This is the standard log-mean style
 * decomposition for a multiplicative identity (ROE = m × t × l);
 * it is exact only when roe equals the product of the three
 * components in both periods.
 *
 * @returns null when any component or ROE is null, non-positive
 * (log of a non-positive number is undefined — e.g. a loss-making
 * period cannot be attributed this way), or when ROE is unchanged
 * (the denominator ln(1) would be zero).
 */
export function roeAttribution(
  first: DupontComponents,
  last: DupontComponents,
): RoeAttribution | null {
  const fM = first.netMargin;
  const lM = last.netMargin;
  const fT = first.assetTurnover;
  const lT = last.assetTurnover;
  const fL = first.leverage;
  const lL = last.leverage;
  const fR = first.roe;
  const lR = last.roe;
  if (
    fM === null || lM === null || fM <= 0 || lM <= 0 ||
    fT === null || lT === null || fT <= 0 || lT <= 0 ||
    fL === null || lL === null || fL <= 0 || lL <= 0 ||
    fR === null || lR === null || fR <= 0 || lR <= 0
  ) {
    return null;
  }
  if (lR === fR) return null;
  const dRoe = lR - fR; // decimal, e.g. 0.05
  const denom = Math.log(lR / fR);
  const pts = (f: number, l: number): number => (Math.log(l / f) / denom) * dRoe * 100;
  return {
    marginPts: pts(fM, lM),
    turnoverPts: pts(fT, lT),
    leveragePts: pts(fL, lL),
  };
}
