// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * graham.ts — Benjamin Graham deep-value lens (The Intelligent Investor).
 *
 * Implements Graham's public-domain quantitative screens as pure functions:
 * net current asset value (NCAV), the net-net rule, the Graham number, and
 * the seven defensive-investor criteria. Every screen is reported as an
 * individual pass/fail signal with the measured number attached.
 */

import { defined, div, firstValue, lastValue } from "../guards.js";
import type { StatementSeries } from "../types.js";
import type { LensContext, LensResult, LensSignal } from "./types.js";
import { fmtMoney, fmtNum, fmtPct } from "./util.js";
import { marginOfSafety } from "../expected.js";

/**
 * Graham's margin of safety — the canonical implementation lives in
 * expected.ts (identical formula, stricter null semantics); re-exported
 * here so the lens module keeps its public surface.
 */
export { marginOfSafety };

/**
 * Net current asset value: currentAssets − totalLiabilities.
 * Graham's liquidation-floor proxy (The Intelligent Investor, ch. 15):
 * what remains for shareholders if current assets are realized and ALL
 * liabilities (not just current) are settled. Null when either input is null.
 */
export function netCurrentAssetValue(
  currentAssets: number | null,
  totalLiabilities: number | null,
): number | null {
  if (currentAssets === null || totalLiabilities === null) return null;
  return currentAssets - totalLiabilities;
}

/**
 * Graham number: sqrt(22.5 × eps × bvps).
 * From The Intelligent Investor: the 22.5 = 15 (max P/E) × 1.5 (max P/B)
 * is the ceiling for the product of the two multiples; the geometric mean
 * with per-share earnings and book value gives an upper bound for a
 * defensive purchase price. Null when eps or bvps is null or not positive.
 */
export function grahamNumber(eps: number | null, bvps: number | null): number | null {
  if (eps === null || bvps === null || eps <= 0 || bvps <= 0) return null;
  return Math.sqrt(22.5 * eps * bvps);
}


/**
 * Runs the Graham deep-value lens over a statement series.
 *
 * Signals: the net-net rule (favor when price < ⅔ × NCAV per share —
 * strictly less; exactly at the line is not a buy), the seven
 * defensive-investor screens (each pass = favor, fail = caution), and the
 * Graham-number margin of safety. Inputs that are missing are named in
 * `missing` and their screens are reported neutral.
 *
 * Originator: Benjamin Graham, The Intelligent Investor (1949).
 * Phrasing: "based on principles popularized by Benjamin Graham
 * (public-domain methodology)".
 */
export function run(s: StatementSeries, _ctx?: LensContext): LensResult {
  const missing: string[] = [];
  const need = (name: string, v: number | null): number | null => {
    if (v === null) missing.push(name);
    return v;
  };

  const ca = need("currentAssets", lastValue(s.currentAssets));
  const cl = need("currentLiabilities", lastValue(s.currentLiabilities));
  const tl = need("totalLiabilities", lastValue(s.totalLiabilities));
  const shares = need("sharesOutstanding", lastValue(s.sharesOutstanding));
  const price = need("price", lastValue(s.price));
  const eps = need("epsDiluted", lastValue(s.epsDiluted));
  const equity = need("totalEquity", lastValue(s.totalEquity));
  const niHist = defined(s.netIncome);
  if (niHist.length === 0) missing.push("netIncome");
  const divHist = defined(s.dividendsPaid);
  if (divHist.length === 0) missing.push("dividendsPaid");
  const epsFirst = firstValue(s.epsDiluted);
  const epsLast = lastValue(s.epsDiluted);

  const signals: LensSignal[] = [];
  const rawValues: Record<string, number | null> = {};

  // ---- net-net rule ----
  const ncav = netCurrentAssetValue(ca, tl);
  const ncavps = div(ncav, shares);
  rawValues.ncavPerShare = ncavps;
  if (ncavps !== null && price !== null) {
    const threshold = (2 / 3) * ncavps;
    rawValues.netNetThreshold = threshold;
    if (ncavps > 0 && price < threshold) {
      signals.push({
        label: "Net-net (NCAV)",
        value: `price ${fmtMoney(price)} < ⅔ × NCAV/share ${fmtMoney(threshold)}`,
        read: "favor",
        note: "Classic net-net rule: buying below two-thirds of net current asset value per share (The Intelligent Investor).",
      });
    } else {
      signals.push({
        label: "Net-net (NCAV)",
        value: `price ${fmtMoney(price)} vs ⅔ × NCAV/share ${fmtMoney(threshold)}`,
        read: "neutral",
        note:
          ncavps <= 0
            ? "NCAV per share is not positive — the net-net rule does not apply."
            : "Price is at or above two-thirds of NCAV per share — no net-net discount.",
      });
    }
  } else {
    signals.push({
      label: "Net-net (NCAV)",
      value: "n/a",
      read: "neutral",
      note: "Cannot test the net-net rule without current assets, total liabilities, shares, and price.",
    });
  }

  // ---- defensive screens ----
  const screen = (
    label: string,
    value: string,
    pass: boolean | null,
    note: string,
  ): void => {
    signals.push({
      label,
      value,
      read: pass === null ? "neutral" : pass ? "favor" : "caution",
      note,
    });
  };

  const currentRatio = div(ca, cl);
  rawValues.currentRatio = currentRatio;
  screen(
    "Defensive: current ratio ≥ 2",
    currentRatio === null ? "n/a" : fmtNum(currentRatio),
    currentRatio === null ? null : currentRatio >= 2,
    "Graham's liquidity screen for the defensive investor (The Intelligent Investor, ch. 14).",
  );

  const niWindow = niHist.slice(-10);
  const earningsOk = niWindow.length > 0 ? niWindow.every((v) => v > 0) : null;
  screen(
    "Defensive: positive earnings every year",
    niWindow.length === 0 ? "n/a" : `${niWindow.length}y all > 0: ${earningsOk}`,
    earningsOk,
    "No earnings deficit in any of the last 10 (or fewer available) years.",
  );

  const divWindow = divHist.slice(-10);
  const divOk = divWindow.length > 0 ? divWindow.every((v) => v > 0) : null;
  screen(
    "Defensive: uninterrupted dividends",
    divWindow.length === 0 ? "n/a" : `${divWindow.length}y all > 0: ${divOk}`,
    divOk,
    "Some dividend paid in every available year (capped at 10).",
  );

  const epsGrowth =
    epsFirst !== null && epsLast !== null && epsFirst > 0 ? (epsLast - epsFirst) / epsFirst : null;
  rawValues.epsGrowthWindow = epsGrowth;
  screen(
    "Defensive: EPS growth ≥ 33%",
    epsGrowth === null ? "n/a" : fmtPct(epsGrowth),
    epsGrowth === null ? null : epsGrowth >= 0.33,
    "Earnings-per-share growth of at least one-third over the available window (first → last non-null EPS).",
  );

  const pe = div(price, eps);
  rawValues.pe = pe;
  screen(
    "Defensive: P/E ≤ 15",
    pe === null ? "n/a" : fmtNum(pe),
    pe === null || eps === null || eps <= 0 ? (pe === null ? null : false) : pe <= 15,
    "Price no more than 15× trailing earnings; fails automatically on non-positive earnings.",
  );

  const bvps = div(equity, shares);
  rawValues.bvps = bvps;
  const pb = div(price, bvps);
  rawValues.pb = pb;
  screen(
    "Defensive: P/B ≤ 1.5",
    pb === null ? "n/a" : fmtNum(pb),
    pb === null || bvps === null || bvps <= 0 ? (pb === null ? null : false) : pb <= 1.5,
    "Price no more than 1.5× book value per share.",
  );

  const pePb = pe !== null && pb !== null ? pe * pb : null;
  rawValues.peTimesPb = pePb;
  screen(
    "Defensive: P/E × P/B ≤ 22.5",
    pePb === null ? "n/a" : fmtNum(pePb),
    pePb === null ? null : pePb <= 22.5,
    "Graham's blended valuation ceiling (The Intelligent Investor, ch. 14).",
  );

  // ---- Graham number margin of safety ----
  const gn = grahamNumber(eps, bvps);
  rawValues.grahamNumber = gn;
  const mos = marginOfSafety(gn, price);
  rawValues.marginOfSafety = mos;
  signals.push({
    label: "Graham number margin of safety",
    value:
      gn === null ? "n/a" : `Graham number ${fmtMoney(gn)}, margin of safety ${fmtPct(mos)}`,
    read: mos === null ? "neutral" : mos > 0 ? "favor" : "caution",
    note: "sqrt(22.5 × EPS × book value/share) as an upper bound for a defensive purchase price; margin of safety = (value − price)/value.",
  });

  const passes = signals.filter((x) => x.read === "favor").length;
  const graded = signals.filter((x) => x.read !== "neutral").length;
  return {
    lens: "graham",
    name: "Benjamin Graham — Deep Value",
    summary:
      `Deep-value screen based on principles popularized by Benjamin Graham ` +
      `(public-domain methodology, The Intelligent Investor). ${passes} of ${graded} graded checks read favor; ` +
      `the rest are caution or need data.`,
    signals,
    rawValues,
    missing,
  };
}
