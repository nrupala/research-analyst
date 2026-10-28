// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * buffett.ts — Warren Buffett owner-earnings & moat lens (Berkshire
 * Hathaway shareholder letters).
 *
 * Buffett's two quantitative ideas, implemented literally: owner earnings
 * ("reported earnings + depreciation/amortization − capex − change in
 * working capital") as the true cash a owner could take home, and the
 * moat as persistent high returns on capital plus stable gross margins.
 * The "equity bond" signal compares the owner-earnings yield to the
 * risk-free rate, exactly as Buffett framed stocks vs. bonds.
 */

import { div, lastValue } from "../guards.js";
import type { StatementSeries } from "../types.js";
import type { LensContext, LensResult } from "./types.js";
import { coefVar, fmtPct } from "./util.js";

/**
 * Owner earnings = netIncome + depreciationAmortization − capex − ΔWC,
 * where ΔWC = workingCapital_t − workingCapital_{t−1} and
 * workingCapital = currentAssets − currentLiabilities.
 * (Buffett, Berkshire Hathaway 1986 shareholder letter.)
 *
 * Sign convention: depreciationAmortization and capex are POSITIVE
 * MAGNITUDES per the engine contract; ΔWC is signed (a working-capital
 * build consumes cash, hence subtracted). Null when any input is null.
 */
export function ownerEarnings(
  netIncome: number | null,
  depreciationAmortization: number | null,
  capex: number | null,
  deltaWorkingCapital: number | null,
): number | null {
  if (
    netIncome === null ||
    depreciationAmortization === null ||
    capex === null ||
    deltaWorkingCapital === null
  ) {
    return null;
  }
  return netIncome + depreciationAmortization - capex - deltaWorkingCapital;
}

/**
 * Return on invested capital for one period: ebit / (equity + debt − cash).
 * The moat test counts how many years clear 15%.
 */
function periodRoic(
  ebit: number | null,
  equity: number | null,
  debt: number | null,
  cash: number | null,
): number | null {
  if (ebit === null || equity === null || debt === null || cash === null) return null;
  const ic = equity + debt - cash;
  if (ic === 0) return null;
  return ebit / ic;
}

/**
 * Buffett lens: owner earnings, moat persistence, and the equity-bond
 * comparison.
 *
 * Signals: (1) owner earnings for the latest computable period (needs two
 * consecutive periods for ΔWC); (2) moat years — count of periods with
 * ROIC ≥ 15% (favor ≥ 5 of the available years, caution when 0);
 * (3) gross-margin stability — coefficient of variation of gross margin
 * (favor < 0.15, caution > 0.30); (4) owner-earnings yield vs the risk-free
 * rate — favor when OEY > rf + 3pp ("buy the equity bond only when it
 * pays a spread"), caution when OEY < rf.
 *
 * Originator: Warren Buffett, Berkshire Hathaway shareholder letters.
 * Phrasing: "based on principles popularized by Warren Buffett
 * (public-domain methodology)".
 */
export function run(s: StatementSeries, ctx?: LensContext): LensResult {
  const missing: string[] = [];
  const n = s.periods.length;

  // Latest owner earnings: scan back for the newest period with NI, D&A,
  // capex, and a computable ΔWC (needs CA/CL at t and t−1).
  let oe: number | null = null;
  let oePeriod: string | null = null;
  for (let i = n - 1; i >= 1; i--) {
    const niV = s.netIncome[i] ?? null;
    const da = s.depreciationAmortization[i] ?? null;
    const capex = s.capitalExpenditure[i] ?? null;
    const caT = s.currentAssets[i] ?? null;
    const clT = s.currentLiabilities[i] ?? null;
    const caP = s.currentAssets[i - 1] ?? null;
    const clP = s.currentLiabilities[i - 1] ?? null;
    if (
      niV !== null &&
      da !== null &&
      capex !== null &&
      caT !== null &&
      clT !== null &&
      caP !== null &&
      clP !== null
    ) {
      oe = ownerEarnings(niV, da, capex, caT - clT - (caP - clP));
      oePeriod = s.periods[i]?.period ?? `period-${i}`;
      break;
    }
  }
  if (oe === null) missing.push("ownerEarnings inputs (netIncome, depreciationAmortization, capitalExpenditure, currentAssets×2, currentLiabilities×2)");

  // Moat: ROIC ≥ 15% year count.
  let moatYears = 0;
  let roicPeriods = 0;
  for (let i = 0; i < n; i++) {
    const r = periodRoic(
      s.ebit[i] ?? null,
      s.totalEquity[i] ?? null,
      s.totalDebt[i] ?? null,
      s.cash[i] ?? null,
    );
    if (r !== null) {
      roicPeriods++;
      if (r >= 0.15) moatYears++;
    }
  }
  if (roicPeriods === 0) missing.push("ROIC inputs (ebit, totalEquity, totalDebt, cash)");

  // Gross-margin stability.
  const margins: number[] = [];
  for (let i = 0; i < n; i++) {
    const gp = s.grossProfit[i] ?? null;
    const rev = s.revenue[i] ?? null;
    if (gp !== null && rev !== null && rev !== 0) margins.push(gp / rev);
  }
  const marginCv = margins.length > 0 ? coefVar(margins) : null;
  if (marginCv === null) missing.push("grossProfit/revenue (margin stability)");

  // Equity-bond comparison.
  const price = lastValue(s.price);
  const shares = lastValue(s.sharesOutstanding);
  if (price === null) missing.push("price");
  if (shares === null) missing.push("sharesOutstanding");
  const mcap = price !== null && shares !== null ? price * shares : null;
  const oey = div(oe, mcap);
  const rf = ctx?.riskFreeRate ?? null;
  if (rf === null) missing.push("ctx.riskFreeRate");

  const moatRead =
    roicPeriods === 0 ? "neutral" : moatYears >= 5 ? "favor" : moatYears === 0 ? "caution" : "neutral";
  const marginRead =
    marginCv === null ? "neutral" : marginCv < 0.15 ? "favor" : marginCv > 0.3 ? "caution" : "neutral";
  const oeyRead =
    oey === null || rf === null
      ? "neutral"
      : oey > rf + 0.03
        ? "favor"
        : oey < rf
          ? "caution"
          : "neutral";

  return {
    lens: "buffett",
    name: "Warren Buffett — Owner Earnings & Moat",
    summary:
      "Owner-economics lens based on principles popularized by Warren Buffett (public-domain methodology, " +
      "Berkshire Hathaway letters): what cash could an owner actually take home, how persistent the returns on " +
      "capital are, and whether the equity 'bond' pays a spread over the risk-free rate.",
    signals: [
      {
        label: "Owner earnings",
        value: oe === null ? "n/a" : `${oe.toFixed(2)}${oePeriod ? ` (${oePeriod})` : ""}`,
        read: "neutral",
        note: "NI + D&A − capex − Δworking capital: the cash a 100% owner could withdraw without harming the business.",
      },
      {
        label: "Moat: years of ROIC ≥ 15%",
        value: roicPeriods === 0 ? "n/a" : `${moatYears} of ${roicPeriods}`,
        read: moatRead as "favor" | "caution" | "neutral",
        note: "Persistent high returns on capital are Buffett's quantitative fingerprint of a moat. Favor at 5+ years.",
      },
      {
        label: "Gross-margin stability",
        value: marginCv === null ? "n/a" : `CV ${marginCv.toFixed(3)}`,
        read: marginRead as "favor" | "caution" | "neutral",
        note: "Coefficient of variation of gross margin; a moat shows up as pricing power that does not wobble. Favor < 0.15, caution > 0.30.",
      },
      {
        label: "Equity bond: owner-earnings yield vs risk-free",
        value:
          oey === null || rf === null
            ? "n/a"
            : `OEY ${fmtPct(oey)} vs rf ${fmtPct(rf)} (spread ${(oey - rf >= 0 ? "+" : "") + fmtPct(oey - rf)})`,
        read: oeyRead as "favor" | "caution" | "neutral",
        note: "Favor when the owner-earnings yield exceeds the risk-free rate by 3+pp; caution when it pays less than cash.",
      },
    ],
    rawValues: {
      ownerEarnings: oe,
      ownerEarningsYield: oey,
      moatYears: roicPeriods === 0 ? null : moatYears,
      moatPeriods: roicPeriods === 0 ? null : roicPeriods,
      grossMarginCv: marginCv,
      marketCap: mcap,
    },
    missing,
  };
}
