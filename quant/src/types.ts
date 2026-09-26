// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

/**
 * quant.ts — shared data contract between the Python backend and the TS engine.
 *
 * A `StatementSeries` is the only input shape the engine understands: one
 * ticker, N fiscal periods, and every line item as an aligned
 * `(number | null)[]` array. Missing data is `null`, never 0 — 0 is a number
 * and would corrupt ratios.
 *
 * SIGN CONVENTION (the one rule): cash-flow outflows — capital expenditure,
 * share buybacks, dividends paid — are POSITIVE MAGNITUDES. The Python engine
 * normalizes with abs(); the bridge preserves that. An outflow of $32.1B is
 * the number 32100000000, not -32100000000.
 *
 * UNITS: plain numbers in the statement currency. No cents/millions scaling
 * inside the engine — scale at the boundary, document at the call site.
 *
 * ORDER: periods run oldest → newest (index 0 is the earliest period).
 * The engine never assumes provider order; the bridge sorts by periodEndDate.
 */

export type Series = (number | null)[];

export interface FiscalPeriod {
  /** Human label, e.g. "FY2025". */
  period: string;
  /** ISO-8601 end date, e.g. "2025-12-31". Null when unknown. */
  periodEndDate: string | null;
}

export interface StatementSeries {
  ticker: string;
  currency: string | null;

  /** Oldest → newest. Every Series below has exactly this length. */
  periods: FiscalPeriod[];

  // ---- income statement ----
  revenue: Series;
  grossProfit: Series;
  operatingIncome: Series;
  ebit: Series;
  netIncome: Series;
  epsDiluted: Series;

  // ---- cash flow statement (outflows as POSITIVE magnitudes) ----
  operatingCashFlow: Series;
  capitalExpenditure: Series;
  freeCashFlow: Series;
  dividendsPaid: Series;
  shareBuybacks: Series;

  // ---- balance sheet ----
  totalAssets: Series;
  totalEquity: Series;
  totalDebt: Series;
  cash: Series;
  currentAssets: Series;
  currentLiabilities: Series;
  inventory: Series;
  receivables: Series;

  // ---- other ----
  interestExpense: Series; // positive magnitude
  taxExpense: Series; // positive magnitude
  sharesOutstanding: Series; // diluted weighted-average, in shares
  price: Series; // period-end close, statement currency
}

/** Names of every numeric series on StatementSeries (for validation). */
export const SERIES_KEYS = [
  "revenue",
  "grossProfit",
  "operatingIncome",
  "ebit",
  "netIncome",
  "epsDiluted",
  "operatingCashFlow",
  "capitalExpenditure",
  "freeCashFlow",
  "dividendsPaid",
  "shareBuybacks",
  "totalAssets",
  "totalEquity",
  "totalDebt",
  "cash",
  "currentAssets",
  "currentLiabilities",
  "inventory",
  "receivables",
  "interestExpense",
  "taxExpense",
  "sharesOutstanding",
  "price",
] as const;

export type SeriesKey = (typeof SERIES_KEYS)[number];

/**
 * Validate that every series matches periods.length.
 * Throws on programmer error (never on data gaps — gaps are nulls).
 */
export function assertValidSeries(s: StatementSeries): void {
  const n = s.periods.length;
  for (const k of SERIES_KEYS) {
    const len = (s[k] as Series).length;
    if (len !== n) {
      throw new Error(
        `quant: series "${k}" has length ${len}, expected ${n} (periods.length) for ${s.ticker}`,
      );
    }
  }
}
