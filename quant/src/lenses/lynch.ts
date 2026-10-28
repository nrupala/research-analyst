// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * lynch.ts — Peter Lynch company-classification lens (One Up on Wall
 * Street).
 *
 * Lynch argued that the right valuation yardstick depends on what KIND of
 * company you hold. {@link classify} assigns one of his six categories from
 * the statements; {@link pegRatio} prices growth; {@link run} emits
 * classification-appropriate signals.
 *
 * All categories are documented heuristics fitted to Lynch's prose, not
 * exact replications — Lynch himself used judgment, not cutoffs.
 */

import { defined, div, firstValue, lastValue } from "../guards.js";
import type { StatementSeries } from "../types.js";
import type { LensContext, LensResult } from "./types.js";
import { coefVar, fmtPct, seriesCagr, signChanges } from "./util.js";

/** Lynch's six company categories plus a fallback. */
export type LynchClassification =
  | "fast grower"
  | "stalwart"
  | "slow grower"
  | "cyclical"
  | "turnaround"
  | "asset play"
  | "unclassified";

/** Detail behind {@link classify}. */
export interface LynchClassDetail {
  classification: LynchClassification;
  /** EPS CAGR (decimal) over the available window; null when not computable. */
  epsCagr: number | null;
  /** Latest revenue (context for the stalwart "large company" check). */
  revenueLatest: number | null;
  /** Sign flips in net income history (cyclical screen input). */
  signChanges: number | null;
  /** Coefficient of variation of net income (cyclical screen input). */
  netIncomeCv: number | null;
  /** price / book value per share (asset-play screen input). */
  priceToBook: number | null;
  /** cash / total assets (asset-play screen input). */
  cashToAssets: number | null;
  /** Latest dividends paid (slow-grower screen input). */
  dividendLatest: number | null;
}

/**
 * PEG ratio: pe / epsGrowthPct, where epsGrowthPct is in PERCENT units
 * (15 for 15%, not 0.15) — Lynch's convention (One Up on Wall Street).
 * Lynch's rule of thumb: PEG ≈ 1 is fairly priced, < 1 is cheap for the
 * growth, > 2 is expensive. Null when pe is null or growth is null or ≤ 0
 * (a PEG on shrinking earnings is meaningless).
 */
export function pegRatio(pe: number | null, epsGrowthPct: number | null): number | null {
  if (pe === null || epsGrowthPct === null || epsGrowthPct <= 0) return null;
  return pe / epsGrowthPct;
}

/**
 * Classifies the company into one of Lynch's six categories.
 *
 * Heuristic decision order (documented; Lynch used judgment, not cutoffs):
 * 1. "turnaround" — earliest net income < 0 but the last two years > 0
 *    (checked first: a turnaround's coefficient of variation is mechanically
 *    huge because its mean crosses zero, so the cyclical CV screen would
 *    otherwise swallow it).
 * 2. "cyclical" — net income changes sign ≥ 2 times, or its coefficient of
 *    variation exceeds 1 (earnings too erratic for growth math).
 * 3. "asset play" — price/book < 1 AND cash/totalAssets > 20%.
 * 4. "fast grower" — EPS CAGR > 20%.
 * 5. "stalwart" — EPS CAGR 10–20% (revenueLatest reported for the
 *    "large, established company" context).
 * 6. "slow grower" — EPS CAGR < 10% with a dividend being paid.
 * Otherwise "unclassified". Missing inputs skip their checks (e.g. no EPS
 * history means no growth category).
 */
export function classify(s: StatementSeries): LynchClassDetail {
  const ni = defined(s.netIncome);
  const epsCagr = seriesCagr(s.epsDiluted);
  const changes = ni.length > 0 ? signChanges(ni) : null;
  const cv = ni.length > 0 ? coefVar(ni) : null;

  const price = lastValue(s.price);
  const bvps = div(lastValue(s.totalEquity), lastValue(s.sharesOutstanding));
  const priceToBook = div(price, bvps);
  const cashToAssets = div(lastValue(s.cash), lastValue(s.totalAssets));
  const dividendLatest = lastValue(s.dividendsPaid);
  const revenueLatest = lastValue(s.revenue);

  let classification: LynchClassification = "unclassified";
  const earlyLoss = firstValue(s.netIncome) !== null && (firstValue(s.netIncome) as number) < 0;
  const tail = ni.slice(-2);
  const t0 = tail[0];
  const t1 = tail[1];
  const recentProfit = tail.length === 2 && t0 !== undefined && t1 !== undefined && t0 > 0 && t1 > 0;
  if (earlyLoss && recentProfit) {
    classification = "turnaround";
  } else if (changes !== null && (changes >= 2 || (cv !== null && cv > 1))) {
    classification = "cyclical";
  } else if (
    priceToBook !== null &&
    priceToBook < 1 &&
    cashToAssets !== null &&
    cashToAssets > 0.2
  ) {
    classification = "asset play";
  } else if (epsCagr !== null && epsCagr > 0.2) {
    classification = "fast grower";
  } else if (epsCagr !== null && epsCagr >= 0.1) {
    classification = "stalwart";
  } else if (epsCagr !== null && dividendLatest !== null && dividendLatest > 0) {
    classification = "slow grower";
  }

  return {
    classification,
    epsCagr,
    revenueLatest,
    signChanges: changes,
    netIncomeCv: cv,
    priceToBook,
    cashToAssets,
    dividendLatest,
  };
}

/**
 * Lynch lens: classify the company, price its growth with the PEG ratio,
 * and run classification-appropriate checks.
 *
 * Signals: the classification itself; PEG < 1 favor / > 2 caution (the
 * growth-pricing signal, only for growers); a dividend check for slow
 * growers; a timing caution for cyclicals; an asset-backing check for
 * asset plays. Originator: Peter Lynch, One Up on Wall Street (1989).
 * Phrasing: "based on principles popularized by Peter Lynch
 * (public-domain methodology)".
 */
export function run(s: StatementSeries, _ctx?: LensContext): LensResult {
  const missing: string[] = [];
  const detail = classify(s);
  if (detail.epsCagr === null) missing.push("epsDiluted (for growth classification)");
  if (detail.revenueLatest === null) missing.push("revenue");
  if (detail.signChanges === null) missing.push("netIncome");

  const price = lastValue(s.price);
  const eps = lastValue(s.epsDiluted);
  if (price === null) missing.push("price");
  if (eps === null) missing.push("epsDiluted");

  const pe = div(price, eps);
  const growthPct = detail.epsCagr === null ? null : detail.epsCagr * 100;
  const peg = pegRatio(pe, growthPct);

  const signals = [
    {
      label: "Lynch classification",
      value: detail.classification,
      read: "neutral" as const,
      note:
        `EPS CAGR ${fmtPct(detail.epsCagr)}; revenue ${detail.revenueLatest ?? "n/a"}; ` +
        `net-income sign changes ${detail.signChanges ?? "n/a"}. Heuristic mapping of One Up on Wall Street categories.`,
    },
    {
      label: "PEG ratio",
      value: peg === null ? "n/a" : peg.toFixed(2),
      read: (peg === null ? "neutral" : peg < 1 ? "favor" : peg > 2 ? "caution" : "neutral") as
        | "favor"
        | "caution"
        | "neutral",
      note: "P/E divided by EPS growth in percent units. Lynch's yardstick: ~1 fairly priced, <1 cheap for the growth, >2 expensive. Null on non-positive growth.",
    },
  ];

  if (detail.classification === "slow grower") {
    signals.push({
      label: "Slow-grower dividend check",
      value:
        detail.dividendLatest !== null && detail.dividendLatest > 0 ? "paying" : "not paying",
      read:
        detail.dividendLatest !== null && detail.dividendLatest > 0 ? "favor" : "caution",
      note: "Lynch's slow growers earn their keep through the dividend; a slow grower that does not pay one fails the thesis.",
    });
  }
  if (detail.classification === "cyclical") {
    signals.push({
      label: "Cyclical timing",
      value: `${detail.signChanges} earnings sign changes`,
      read: "caution",
      note: "Cyclicals must be bought on depressed (trough) earnings, never on peak multiples — the P/E inverts at the top.",
    });
  }
  if (detail.classification === "asset play") {
    signals.push({
      label: "Asset backing",
      value: `P/B ${(detail.priceToBook ?? NaN).toFixed(2)}, cash/assets ${fmtPct(detail.cashToAssets)}`,
      read: "favor",
      note: "Priced below book with a cash-heavy balance sheet — the market values the assets at less than the cash alone would suggest.",
    });
  }
  if (detail.classification === "turnaround") {
    signals.push({
      label: "Turnaround confirmation",
      value: "early losses → last-2y profits",
      read: "favor",
      note: "Earnings have crossed from loss to profit; Lynch's rule is to wait for the turn to be visible in the statements, not forecast it.",
    });
  }

  return {
    lens: "lynch",
    name: "Peter Lynch — Company Classification",
    summary:
      "Classification-first lens based on principles popularized by Peter Lynch (public-domain methodology, " +
      `One Up on Wall Street): this company reads as a "${detail.classification}". ` +
      "The right yardstick follows the category — PEG for growers, trough earnings for cyclicals, asset value for asset plays.",
    signals,
    rawValues: {
      epsCagr: detail.epsCagr,
      pe,
      peg,
      priceToBook: detail.priceToBook,
      cashToAssets: detail.cashToAssets,
      netIncomeCv: detail.netIncomeCv,
      signChanges: detail.signChanges,
    },
    missing,
  };
}
