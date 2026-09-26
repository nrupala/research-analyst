// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * allocation.ts — Buffett-style capital allocation tests.
 *
 * Four pure analyses of how management deploys cash: buybacks, dividends,
 * debt, and incremental reinvestment. All functions are null-safe
 * (nulls in, nulls out) and never throw on data gaps.
 *
 * Sign convention (from types.ts): share buybacks, dividends paid, and
 * capital expenditure are POSITIVE MAGNITUDES.
 */

import { defined, div, firstValue, lastValue } from "./guards.js";
import { seriesCagr } from "./trends.js";

/**
 * Re-exported from the trends module (single canonical implementation).
 */
export { seriesCagr };
import type { Series, StatementSeries } from "./types.js";


/** Output of {@link buybackEffectiveness}. */
export interface BuybackEffectiveness {
  /** CAGR of sharesOutstanding, first → last non-null observation. */
  sharesCagr: number | null;
  /** Sum of shareBuybacks over the window (positive magnitude). Null when no buyback data. */
  totalSpent: number | null;
  /** First − last sharesOutstanding. Positive means shares were retired. */
  sharesRetired: number | null;
  /** totalSpent / sharesRetired — the average price paid per retired share. */
  impliedAvgPrice: number | null;
  /** Latest period-end price. */
  currentPrice: number | null;
  /** (impliedAvgPrice − currentPrice) / currentPrice. Positive = overpaid vs today. */
  premiumVsMarket: number | null;
}

/**
 * Tests whether buybacks created value (Buffett's rule: repurchase only
 * below intrinsic value).
 *
 * impliedAvgPrice = totalSpent / sharesRetired answers "what did management
 * actually pay per share retired?" premiumVsMarket then compares that
 * against today's price. A persistent premium means the company bought
 * high — the classic buyback value-destruction pattern.
 *
 * Null semantics: impliedAvgPrice is null when sharesRetired <= 0 (no net
 * retirement — e.g. issuance offset repurchases) or buyback data is missing;
 * premiumVsMarket is null when either price is missing or currentPrice is 0.
 */
export function buybackEffectiveness(s: StatementSeries): BuybackEffectiveness {
  const sharesCagr = seriesCagr(s.sharesOutstanding);
  const spent = defined(s.shareBuybacks);
  const totalSpent = spent.length > 0 ? spent.reduce((a, b) => a + b, 0) : null;
  const first = firstValue(s.sharesOutstanding);
  const last = lastValue(s.sharesOutstanding);
  const sharesRetired = first !== null && last !== null ? first - last : null;
  const impliedAvgPrice =
    totalSpent !== null && sharesRetired !== null && sharesRetired > 0
      ? totalSpent / sharesRetired
      : null;
  const currentPrice = lastValue(s.price);
  const premiumVsMarket =
    impliedAvgPrice !== null && currentPrice !== null && currentPrice !== 0
      ? (impliedAvgPrice - currentPrice) / currentPrice
      : null;
  return { sharesCagr, totalSpent, sharesRetired, impliedAvgPrice, currentPrice, premiumVsMarket };
}

/** Output of {@link dividendProfile}. */
export interface DividendProfile {
  /** Latest dividendsPaid / latest netIncome. Null when either is missing or earnings are 0. */
  payoutOnEarnings: number | null;
  /** Latest dividendsPaid / latest freeCashFlow. Null when either is missing or FCF is 0. */
  payoutOnFcf: number | null;
  /**
   * Trailing consecutive year-over-year increases in dividends per share
   * (dps = dividendsPaid / sharesOutstanding), counted back from the latest
   * observation. A flat year breaks the streak; nulls are skipped pairwise.
   */
  yearsGrown: number;
  /** Count of year-over-year declines in dividends per share over the whole window. */
  cuts: number;
}

/**
 * Dividend sustainability profile.
 *
 * payoutOnEarnings and payoutOnFcf use the latest non-null observation of
 * each series (they need not come from the same period — documented
 * limitation). yearsGrown/cuts are computed on dividends per share so
 * buyback-driven per-share growth is not mistaken for dividend growth.
 */
export function dividendProfile(s: StatementSeries): DividendProfile {
  const payoutOnEarnings = div(lastValue(s.dividendsPaid), lastValue(s.netIncome));
  const payoutOnFcf = div(lastValue(s.dividendsPaid), lastValue(s.freeCashFlow));

  // Per-share dividend series over aligned non-null (dividends, shares) pairs.
  const dps: number[] = [];
  const n = Math.min(s.dividendsPaid.length, s.sharesOutstanding.length);
  for (let i = 0; i < n; i++) {
    const d = s.dividendsPaid[i];
    const sh = s.sharesOutstanding[i];
    if (d !== null && d !== undefined && sh !== null && sh !== undefined && sh > 0) {
      dps.push(d / sh);
    }
  }

  let yearsGrown = 0;
  for (let i = dps.length - 1; i >= 1; i--) {
    const cur = dps[i];
    const prev = dps[i - 1];
    if (cur === undefined || prev === undefined) break;
    if (cur > prev) yearsGrown++;
    else break;
  }
  let cuts = 0;
  for (let i = 1; i < dps.length; i++) {
    const cur = dps[i];
    const prev = dps[i - 1];
    if (cur !== undefined && prev !== undefined && cur < prev) cuts++;
  }
  return { payoutOnEarnings, payoutOnFcf, yearsGrown, cuts };
}

/** Output of {@link debtProfile}. */
export interface DebtProfile {
  /** Latest totalDebt − latest cash. Negative = net cash position. */
  netDebtLatest: number | null;
  /** netDebtLatest / latest ebit. Null when ebit is missing or 0. */
  netDebtToEbit: number | null;
  /** Latest ebit / latest interestExpense. Null when either is missing or interest is 0. */
  interestCoverage: number | null;
  /** CAGR of totalDebt, first → last non-null observation. */
  debtCagr: number | null;
}

/**
 * Balance-sheet leverage profile.
 *
 * netDebtToEbit answers "how many years of operating profit to repay net
 * debt"; interestCoverage answers "can operating profit service the
 * interest bill". debtCagr shows whether leverage is structurally growing.
 */
export function debtProfile(s: StatementSeries): DebtProfile {
  const debt = lastValue(s.totalDebt);
  const cash = lastValue(s.cash);
  const ebit = lastValue(s.ebit);
  const interest = lastValue(s.interestExpense);
  const netDebtLatest = debt !== null && cash !== null ? debt - cash : null;
  return {
    netDebtLatest,
    netDebtToEbit: div(netDebtLatest, ebit),
    interestCoverage: div(ebit, interest),
    debtCagr: seriesCagr(s.totalDebt),
  };
}

/** One interval of {@link incrementalRoic}. */
export interface IncrementalRoicPeriod {
  /** Period label of the interval's end (e.g. "FY2024"). */
  period: string;
  /** ΔNOPAT / ΔInvestedCapital for the interval, or null (see below). */
  value: number | null;
}

/** Output of {@link incrementalRoic}. */
export interface IncrementalRoic {
  byPeriod: IncrementalRoicPeriod[];
  /** Mean of the non-null interval values; null when every interval is null. */
  average: number | null;
}

/**
 * Incremental return on invested capital per period interval.
 *
 * For each interval t−1 → t:
 *   NOPAT_t = ebit_t × (1 − taxRate_t),
 *   taxRate_t = (ebit_t − netIncome_t) / ebit_t   (effective rate; null unless ebit_t > 0),
 *   InvestedCapital_t = totalEquity_t + totalDebt_t − cash_t,
 *   incremental ROIC = (NOPAT_t − NOPAT_{t−1}) / (IC_t − IC_{t−1}).
 *
 * The interval value is null when any input is missing OR when
 * ΔInvestedCapital <= 0 (a shrinking capital base makes the ratio
 * economically meaningless — it would reward divestment as "return").
 * average is the mean of the non-null interval values.
 */
export function incrementalRoic(s: StatementSeries): IncrementalRoic {
  const n = s.periods.length;
  const byPeriod: IncrementalRoicPeriod[] = [];
  const values: number[] = [];
  let prevNopat: number | null = null;
  let prevIc: number | null = null;

  for (let i = 0; i < n; i++) {
    const ebit = s.ebit[i] ?? null;
    const ni = s.netIncome[i] ?? null;
    const eq = s.totalEquity[i] ?? null;
    const debt = s.totalDebt[i] ?? null;
    const cash = s.cash[i] ?? null;

    let nopat: number | null = null;
    if (ebit !== null && ni !== null && ebit > 0) {
      const taxRate = (ebit - ni) / ebit;
      nopat = ebit * (1 - taxRate);
    }
    const ic = eq !== null && debt !== null && cash !== null ? eq + debt - cash : null;

    if (i > 0) {
      let value: number | null = null;
      if (nopat !== null && prevNopat !== null && ic !== null && prevIc !== null) {
        const dIc = ic - prevIc;
        value = dIc > 0 ? (nopat - prevNopat) / dIc : null;
      }
      byPeriod.push({ period: s.periods[i]?.period ?? `period-${i}`, value });
      if (value !== null) values.push(value);
    }
    prevNopat = nopat;
    prevIc = ic;
  }

  const average = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : null;
  return { byPeriod, average };
}
