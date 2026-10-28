// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * dalio.ts — Ray Dalio diversification & debt-cycle lens (Principles).
 *
 * Two Dalio ideas as pure functions: (1) diversification as the "holy
 * grail" — the mathematics of how uncorrelated return streams cut risk,
 * with risk-parity weighting; (2) the debt cycle — credit expansion vs.
 * contraction read from the race between liability growth and revenue
 * growth, plus the leverage trend.
 */

import { div, lastValue } from "../guards.js";
import type { StatementSeries } from "../types.js";
import type { LensContext, LensResult } from "./types.js";
import { fmtPct, seriesCagr } from "./util.js";

/** Debt-cycle gauge reading. */
export type DebtCycleGauge = "expansion" | "contraction" | "stable";

/**
 * Diversification factor: (1 + (n − 1) × rho) / n.
 * (Dalio, Principles — the "holy grail" curve.)
 *
 * Under equal weights, equal volatilities, and a common pairwise
 * correlation rho, portfolio variance equals this fraction of the average
 * single-stream variance. n = 1 → 1 (no diversification); as n grows the
 * factor → rho (only the correlated component remains). Dalio's practical
 * point: with low correlation, 15–20 good uncorrelated streams capture most
 * of the benefit. Null when n < 1 or rho is null/non-finite.
 */
export function diversificationFactor(n: number, rho: number | null): number | null {
  if (rho === null || !Number.isFinite(rho) || !Number.isFinite(n) || n < 1) return null;
  return (1 + (n - 1) * rho) / n;
}

/**
 * Risk-parity weights: w_i = (1 / σ_i) / Σ_j (1 / σ_j).
 * Allocates so each stream contributes equally to portfolio risk (under
 * zero correlation each contributes equal variance). Returns null when
 * the list is empty or any volatility is null, non-finite, or ≤ 0.
 */
export function riskParityWeights(vols: (number | null)[]): number[] | null {
  if (vols.length === 0) return null;
  const inv: number[] = [];
  for (const v of vols) {
    if (v === null || !Number.isFinite(v) || v <= 0) return null;
    inv.push(1 / v);
  }
  const total = inv.reduce((a, b) => a + b, 0);
  if (total <= 0) return null;
  return inv.map((x) => x / total);
}

/**
 * Debt-cycle gauge from the race between liability growth and revenue growth.
 *
 * Heuristic (documented as such): "expansion" when liabilitiesCAGR exceeds
 * revenueCAGR by more than 5pp (credit growing materially faster than the
 * income that services it); "contraction" when revenueCAGR exceeds
 * liabilitiesCAGR by more than 5pp (deleveraging); otherwise "stable".
 * This is a company-level analogue of Dalio's credit-cycle observation
 * that crises follow credit growing faster than income. Null when either
 * CAGR is null.
 */
export function debtCycleGauge(
  liabilitiesCagr: number | null,
  revenueCagr: number | null,
): DebtCycleGauge | null {
  if (liabilitiesCagr === null || revenueCagr === null) return null;
  const gap = liabilitiesCagr - revenueCagr;
  if (gap > 0.05) return "expansion";
  if (gap < -0.05) return "contraction";
  return "stable";
}

/**
 * Dalio lens: diversification arithmetic and the company-level debt cycle.
 *
 * Signals: (1) the holy-grail curve — diversification factor at 1, 5, and
 * 15 streams under an illustrative ρ = 0.3 (labeled illustrative: the
 * engine has no segment-level streams); (2) the debt-cycle gauge with the
 * two CAGRs; (3) the leverage trend (latest vs earliest
 * totalLiabilities/totalAssets). Reads: gauge "expansion" with rising
 * leverage → caution; "contraction" with falling leverage → favor.
 *
 * Originator: Ray Dalio, Principles (2017).
 * Phrasing: "based on principles popularized by Ray Dalio
 * (public-domain methodology)".
 */
export function run(s: StatementSeries, _ctx?: LensContext): LensResult {
  const liabCagr = seriesCagr(s.totalLiabilities);
  const revCagr = seriesCagr(s.revenue);
  const missing: string[] = [];
  if (liabCagr === null) missing.push("totalLiabilities (for CAGR)");
  if (revCagr === null) missing.push("revenue (for CAGR)");

  const gauge = debtCycleGauge(liabCagr, revCagr);

  const lev = (i: number): number | null => {
    const tl = s.totalLiabilities[i] ?? null;
    const ta = s.totalAssets[i] ?? null;
    return div(tl, ta);
  };
  const levFirst = lev(0);
  const levLast = lev(s.periods.length - 1);
  if (levFirst === null || levLast === null) missing.push("totalLiabilities/totalAssets (leverage trend)");
  const levDelta = levFirst !== null && levLast !== null ? levLast - levFirst : null;

  const cycleRead =
    gauge === null
      ? "neutral"
      : gauge === "expansion" && levDelta !== null && levDelta > 0
        ? "caution"
        : gauge === "contraction" && levDelta !== null && levDelta < 0
          ? "favor"
          : "neutral";

  const holyGrail = [1, 5, 15].map((n) => ({
    n,
    f: diversificationFactor(n, 0.3),
  }));

  return {
    lens: "dalio",
    name: "Ray Dalio — Diversification & Debt Cycles",
    summary:
      "Risk-architecture lens based on principles popularized by Ray Dalio (public-domain methodology, Principles): " +
      "the mathematics of diversification, and whether the company's credit is expanding faster than the income that services it.",
    signals: [
      {
        label: "Debt-cycle gauge",
        value: gauge === null ? "n/a" : `${gauge} (liab CAGR ${fmtPct(liabCagr)} vs revenue CAGR ${fmtPct(revCagr)})`,
        read: cycleRead as "favor" | "caution" | "neutral",
        note: "Expansion = liabilities compounding >5pp faster than revenue (credit outrunning income); contraction = deleveraging. Heuristic.",
      },
      {
        label: "Leverage trend",
        value:
          levDelta === null
            ? "n/a"
            : `liabilities/assets ${fmtPct(levFirst)} → ${fmtPct(levLast)} (${levDelta >= 0 ? "+" : ""}${fmtPct(levDelta)}pp)`,
        read: (levDelta === null ? "neutral" : levDelta > 0.05 ? "caution" : levDelta < -0.05 ? "favor" : "neutral") as
          | "favor"
          | "caution"
          | "neutral",
        note: "Direction of totalLiabilities/totalAssets from the earliest to the latest period.",
      },
      {
        label: "Holy-grail curve (illustrative)",
        value: holyGrail.map((h) => `n=${h.n}: ${h.f === null ? "n/a" : h.f.toFixed(3)}`).join(", "),
        read: "neutral",
        note: "Illustrative: portfolio variance as a fraction of single-stream variance at ρ=0.3. 15 low-correlation streams leave ~35% of the risk — the mathematical case for diversification.",
      },
    ],
    rawValues: {
      liabilitiesCagr: liabCagr,
      revenueCagr: revCagr,
      leverageFirst: levFirst,
      leverageLast: levLast,
      leverageDelta: levDelta,
      diversificationFactor15: diversificationFactor(15, 0.3),
    },
    missing,
  };
}
