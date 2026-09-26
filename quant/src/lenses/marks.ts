// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * marks.ts — Howard Marks cycles & second-level thinking lens
 * (The Most Important Thing).
 *
 * Marks's two operational ideas: (1) position against the cycle — a gauge
 * combining where valuation stands vs. history with how fast debt is
 * growing; (2) second-level thinking — enumerate outcomes with
 * probabilities and ask what happens if consensus is wrong. The gauge is
 * an explicitly labeled heuristic composite; the probability math is exact.
 */

import { div, lastValue } from "../guards.js";
import type { StatementSeries } from "../types.js";
import type { LensContext, LensResult } from "./types.js";
import { fmtPct, percentileRank, seriesCagr } from "./util.js";

/** Extended context: optionally pass through forensic flags. */
export interface MarksContext extends LensContext {
  /** e.g. ["beneish-m-score", "accrual-spike"] — each becomes a caution signal. */
  forensicFlags?: string[];
}

/**
 * Cycle gauge: 0.6 × valuationPercentile + 0.4 × debtScore, where
 *   valuationPercentile is 0–100 (e.g. current P/E percentile vs history;
 *     100 = most expensive ever),
 *   debtScore = clamp(debtGrowth × 100, 0, 100) (debtGrowth as a decimal;
 *     20% debt growth scores 100).
 *
 * DOCUMENTED HEURISTIC COMPOSITE: the 60/40 weighting and the linear
 * debtScore are judgment calls, not Marks's formula — Marks wrote about
 * cycles qualitatively (The Most Important Thing, ch. 9). The gauge is a
 * "where are we in the cycle" thermometer: high = late-cycle conditions
 * (expensive + levering up). Null when either input is null.
 */
export function cycleGauge(
  valuationPercentile: number | null,
  debtGrowth: number | null,
): number | null {
  if (valuationPercentile === null || debtGrowth === null) return null;
  const debtScore = Math.min(100, Math.max(0, debtGrowth * 100));
  return 0.6 * valuationPercentile + 0.4 * debtScore;
}

/** One scenario for second-level thinking. */
export interface SecondLevelOutcome {
  label: string;
  /** Payoff/value under this scenario (any consistent unit). */
  value: number;
  /** Probability as a decimal; the set should sum to 1. */
  probability: number;
}

/** Output of {@link secondLevel}. */
export interface SecondLevelResult {
  /** True when probabilities sum to 1 ± 0.01. */
  valid: boolean;
  /** The actual probability sum (for diagnosis). */
  probabilitySum: number;
  /** Σ probability × value. Null when invalid. */
  expectedValue: number | null;
  /**
   * max(value) − min(value): the "what if consensus is wrong" spread —
   * how much the answer changes across scenarios. Null when invalid.
   */
  spread: number | null;
}

/**
 * Second-level thinking, formalized (Marks, The Most Important Thing,
 * ch. 1: "first-level thinking says X; second-level thinking asks what
 * happens if consensus is wrong").
 *
 * Validates that probabilities sum to 1 within ±0.01, then returns the
 * probability-weighted expected value and the spread between the best and
 * worst scenario. An invalid probability set returns valid=false with null
 * expectedValue/spread rather than a silently wrong number.
 */
export function secondLevel(outcomes: SecondLevelOutcome[]): SecondLevelResult {
  const probabilitySum = outcomes.reduce((a, o) => a + o.probability, 0);
  const valid = outcomes.length > 0 && Math.abs(probabilitySum - 1) <= 0.01;
  if (!valid) {
    return { valid, probabilitySum, expectedValue: null, spread: null };
  }
  let ev = 0;
  let lo = Infinity;
  let hi = -Infinity;
  for (const o of outcomes) {
    ev += o.probability * o.value;
    if (o.value < lo) lo = o.value;
    if (o.value > hi) hi = o.value;
  }
  return { valid, probabilitySum, expectedValue: ev, spread: hi - lo };
}

/**
 * Marks lens: where are we in the cycle, and what does the downside look like?
 *
 * Signals: (1) the cycle gauge — valuation percentile (current P/E vs its
 * own history) blended with debt growth; favor < 35 ("lean in"),
 * caution > 65 ("lean out"), else neutral; (2) a standalone valuation
 * caution when the P/E percentile exceeds 75; (3) one caution signal per
 * forensic flag passed via MarksContext (beneish-style flag passthrough).
 * Only positive P/E observations enter the history (negative multiples are
 * not rankable on a "cheap→expensive" axis).
 *
 * Originator: Howard Marks, The Most Important Thing (2011).
 * Phrasing: "based on principles popularized by Howard Marks
 * (public-domain methodology)".
 */
export function run(s: StatementSeries, ctx?: MarksContext): LensResult {
  const missing: string[] = [];

  // P/E history from aligned (price, eps) pairs with positive earnings.
  const peHist: number[] = [];
  const n = Math.min(s.price.length, s.epsDiluted.length);
  for (let i = 0; i < n; i++) {
    const p = s.price[i] ?? null;
    const e = s.epsDiluted[i] ?? null;
    if (p !== null && e !== null && e > 0) peHist.push(p / e);
  }
  const latestPe = peHist.length > 0 ? peHist[peHist.length - 1] ?? null : null;
  const valuationPercentile =
    latestPe === null ? null : percentileRank(peHist, latestPe);
  if (valuationPercentile === null) missing.push("price/epsDiluted (P/E history)");

  const debtGrowth = seriesCagr(s.totalDebt);
  if (debtGrowth === null) missing.push("totalDebt (debt growth)");

  const gauge = cycleGauge(valuationPercentile, debtGrowth);
  const gaugeRead =
    gauge === null ? "neutral" : gauge > 65 ? "caution" : gauge < 35 ? "favor" : "neutral";

  const signals = [
    {
      label: "Cycle gauge",
      value:
        gauge === null
          ? "n/a"
          : `${gauge.toFixed(1)} (valuation pct ${valuationPercentile === null ? "n/a" : valuationPercentile.toFixed(0)}, debt growth ${fmtPct(debtGrowth)})`,
      read: gaugeRead as "favor" | "caution" | "neutral",
      note: "Heuristic composite: 0.6× P/E percentile vs history + 0.4× debt-growth score. Favor < 35 (early-cycle conditions), caution > 65 (late-cycle).",
    },
    {
      label: "Valuation vs history",
      value:
        valuationPercentile === null
          ? "n/a"
          : `P/E ${latestPe === null ? "n/a" : latestPe.toFixed(1)} at the ${valuationPercentile.toFixed(0)}th percentile of its own history`,
      read: (valuationPercentile !== null && valuationPercentile > 75
        ? "caution"
        : "neutral") as "favor" | "caution" | "neutral",
      note: "Downside enumeration: a multiple above the 75th percentile of its own history leaves little room for multiple expansion.",
    },
  ];

  for (const flag of ctx?.forensicFlags ?? []) {
    signals.push({
      label: `Forensic flag: ${flag}`,
      value: "raised",
      read: "caution",
      note: "Passed through from forensic analysis — second-level thinking requires pricing this downside explicitly.",
    });
  }

  return {
    lens: "marks",
    name: "Howard Marks — Cycles & Second-Level Thinking",
    summary:
      "Cycle-positioning lens based on principles popularized by Howard Marks (public-domain methodology, " +
      "The Most Important Thing): locate the cycle with valuation-vs-history and debt growth, then enumerate " +
      "the downside. Use secondLevel() to formalize scenario probabilities.",
    signals,
    rawValues: {
      cycleGauge: gauge,
      valuationPercentile,
      debtGrowth,
      latestPe,
      forensicFlagCount: ctx?.forensicFlags?.length ?? 0,
    },
    missing,
  };
}
