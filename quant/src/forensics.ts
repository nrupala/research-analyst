// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

/**
 * forensics.ts — earnings-quality and distress forensics.
 *
 * - Sloan (1996) accruals: high accruals predict lower earnings persistence.
 * - Cash conversion: how much of reported profit arrived as cash.
 * - Altman (1968) Z-score: manufacturing bankruptcy-prediction model.
 * - Beneish (1999) M-score: eight-variable earnings-manipulation screen.
 * - Working-capital days: DSO / DIO / DPO cash-conversion-cycle inputs.
 *
 * These are screens, not verdicts: the Altman cutoffs were fit on 1960s
 * US manufacturers, and the Beneish flag is probabilistic. Nulls in,
 * nulls out — missing inputs are reported, never silently dropped.
 */

import type { Series, StatementSeries } from "./types.js";
import { div } from "./guards.js";

/** Read index i of a series; out-of-range or non-finite becomes null. */
function at(values: Series, i: number): number | null {
  const v = values[i];
  if (v === undefined || v === null || !Number.isFinite(v)) return null;
  return v;
}

/**
 * Sloan (1996) accruals ratio: (netIncome − operatingCashFlow) / totalAssets.
 *
 * Sloan, R.G. (1996), "Do Stock Prices Fully Reflect Information in
 * Accruals and Cash Flows about Future Earnings?", The Accounting Review.
 * Finding: the accrual component of earnings is less persistent than the
 * cash-flow component, so high positive accruals warn of lower-quality,
 * less repeatable earnings.
 *
 * @returns null when any input is null or totalAssets <= 0.
 */
export function sloanAccruals(
  netIncome: number | null,
  operatingCashFlow: number | null,
  totalAssets: number | null,
): number | null {
  if (netIncome === null || operatingCashFlow === null || totalAssets === null) return null;
  if (totalAssets <= 0) return null;
  return (netIncome - operatingCashFlow) / totalAssets;
}

/**
 * Cash conversion: operatingCashFlow / netIncome.
 *
 * The share of reported profit that materialized as operating cash.
 * Sustained readings well below 1.0 mean profits are not turning into
 * cash; readings above 1.0 are normal for capital-heavy businesses
 * (depreciation is a non-cash charge).
 *
 * @returns null when either input is null or netIncome is 0.
 * A negative netIncome still yields a (negative) ratio — null means
 * "no data", not "bad".
 */
export function cashConversion(
  operatingCashFlow: number | null,
  netIncome: number | null,
): number | null {
  if (operatingCashFlow === null || netIncome === null || netIncome === 0) return null;
  return operatingCashFlow / netIncome;
}

// ---------------------------------------------------------------------------
// Altman Z-score
// ---------------------------------------------------------------------------

/** Altman Z-score distress zone. */
export type AltmanZone = "safe" | "grey" | "distress";

/** The five Altman (1968) discriminant variables. */
export interface AltmanComponents {
  /** (currentAssets − currentLiabilities) / totalAssets — working capital. */
  x1: number;
  /** retainedEarnings / totalAssets — cumulative profitability. */
  x2: number;
  /** ebit / totalAssets — operating productivity of assets. */
  x3: number;
  /** (price × sharesOutstanding) / totalLiabilities — market leverage. */
  x4: number;
  /** revenue / totalAssets — asset turnover. */
  x5: number;
}

/** Successful Altman computation. `missing` is empty by construction. */
export interface AltmanZOk {
  z: number;
  zone: AltmanZone;
  components: AltmanComponents;
  missing: [];
}

/**
 * Failed Altman computation: z/zone/components are null and `missing`
 * names every unavailable input (series key, e.g. "ebit", or
 * "periodIndex" when i is out of range, or "totalAssets" /
 * "totalLiabilities" when non-positive).
 */
export interface AltmanZMissing {
  z: null;
  zone: null;
  components: null;
  missing: string[];
}

export type AltmanZResult = AltmanZOk | AltmanZMissing;

/**
 * Altman (1968) Z-score for public manufacturers, at period index i.
 *
 * Altman, E.I. (1968), "Financial Ratios, Discriminant Analysis and the
 * Prediction of Corporate Bankruptcy", Journal of Finance.
 *
 *   Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5
 *   X1 = (CA − CL)/TA, X2 = RE/TA, X3 = EBIT/TA,
 *   X4 = marketCap/totalLiabilities, X5 = revenue/TA
 *
 * Zones: Z > 2.99 "safe"; 1.81 ≤ Z ≤ 2.99 "grey" (zone of ignorance);
 * Z < 1.81 "distress". Cutoffs were fit on 1960s US manufacturers —
 * do not apply the model to banks, insurers, or private firms
 * (X4 needs a market price).
 *
 * @returns AltmanZOk on success; AltmanZMissing (z null, `missing`
 * listing the absent inputs) when any component input is unavailable.
 */
export function altmanZ(s: StatementSeries, i: number): AltmanZResult {
  if (!Number.isInteger(i) || i < 0 || i >= s.periods.length) {
    return { z: null, zone: null, components: null, missing: ["periodIndex"] };
  }
  const missing: string[] = [];
  const need = (key: string, v: number | null): number | null => {
    if (v === null) missing.push(key);
    return v;
  };
  const ca = need("currentAssets", at(s.currentAssets, i));
  const cl = need("currentLiabilities", at(s.currentLiabilities, i));
  const ta = need("totalAssets", at(s.totalAssets, i));
  const re = need("retainedEarnings", at(s.retainedEarnings, i));
  const ebit = need("ebit", at(s.ebit, i));
  const price = need("price", at(s.price, i));
  const shares = need("sharesOutstanding", at(s.sharesOutstanding, i));
  const tl = need("totalLiabilities", at(s.totalLiabilities, i));
  const rev = need("revenue", at(s.revenue, i));
  if (ta !== null && ta <= 0) missing.push("totalAssets");
  if (tl !== null && tl <= 0) missing.push("totalLiabilities");

  if (
    missing.length > 0 ||
    ca === null || cl === null || ta === null || re === null ||
    ebit === null || price === null || shares === null ||
    tl === null || rev === null
  ) {
    return { z: null, zone: null, components: null, missing };
  }

  const components: AltmanComponents = {
    x1: (ca - cl) / ta,
    x2: re / ta,
    x3: ebit / ta,
    x4: (price * shares) / tl,
    x5: rev / ta,
  };
  const z =
    1.2 * components.x1 +
    1.4 * components.x2 +
    3.3 * components.x3 +
    0.6 * components.x4 +
    1.0 * components.x5;
  // Exact-boundary rule: Z == 2.99 or Z == 1.81 falls in "grey".
  const zone: AltmanZone = z > 2.99 ? "safe" : z < 1.81 ? "distress" : "grey";
  return { z, zone, components, missing: [] };
}

// ---------------------------------------------------------------------------
// Beneish M-score
// ---------------------------------------------------------------------------

/** The eight Beneish (1999) variables, period t vs t−1. */
export interface BeneishVariables {
  /** Days-sales-in-receivables index. */
  dsri: number;
  /** Gross-margin index. */
  gmi: number;
  /** Asset-quality index. */
  aqi: number;
  /** Sales-growth index. */
  sgi: number;
  /** Depreciation index. */
  depi: number;
  /** SG&A index. */
  sgai: number;
  /** Leverage index. */
  lvgi: number;
  /** Total accruals to total assets. */
  tata: number;
}

/** Successful Beneish computation. `missing` is empty by construction. */
export interface BeneishMOk {
  m: number;
  flag: boolean;
  variables: BeneishVariables;
  missing: [];
}

/**
 * Failed Beneish computation: m/flag/variables are null and `missing`
 * names every variable that could not be built ("DSRI" … "TATA"), or
 * "priorPeriod" when i < 1 (there is no t−1 to compare against).
 */
export interface BeneishMMissing {
  m: null;
  flag: null;
  variables: null;
  missing: string[];
}

export type BeneishMResult = BeneishMOk | BeneishMMissing;

/**
 * Beneish (1999) M-score at period index i, vs period i−1.
 *
 * Beneish, M.D. (1999), "The Detection of Earnings Manipulation",
 * Financial Analysts Journal.
 *
 *   DSRI = (recv_t/rev_t) / (recv_{t−1}/rev_{t−1})
 *   GMI  = [(rev−COGS)/rev]_{t−1} / [(rev−COGS)/rev]_t, COGS = revenue − grossProfit
 *   AQI  = [1 − (CA+PPE)/TA]_t / [1 − (CA+PPE)/TA]_{t−1}
 *   SGI  = rev_t / rev_{t−1}
 *   DEPI = [dep/(PPE+dep)]_{t−1} / [dep/(PPE+dep)]_t   (dep = depreciationAmortization,
 *          a positive magnitude per the StatementSeries contract)
 *   SGAI = (sga/rev)_t / (sga/rev)_{t−1}
 *   LVGI = [(CL+totalDebt)/TA]_t / [(CL+totalDebt)/TA]_{t−1}
 *   TATA = (netIncome − operatingCashFlow) / TA_t
 *
 *   M = −4.84 + 0.92·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI
 *       + 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI
 *
 * flag = M > −1.78 (Beneish's manipulator cutoff). A flag is a screen
 * for further review, not proof of manipulation.
 *
 * @returns BeneishMOk on success; BeneishMMissing (m null, `missing`
 * listing uncomputable variables) when inputs are absent or a
 * denominator is zero.
 */
export function beneishM(s: StatementSeries, i: number): BeneishMResult {
  if (!Number.isInteger(i) || i < 1 || i >= s.periods.length) {
    return { m: null, flag: null, variables: null, missing: ["priorPeriod"] };
  }
  const t = i;
  const p = i - 1;

  const recvT = at(s.receivables, t);
  const recvP = at(s.receivables, p);
  const revT = at(s.revenue, t);
  const revP = at(s.revenue, p);
  const gpT = at(s.grossProfit, t);
  const gpP = at(s.grossProfit, p);
  const caT = at(s.currentAssets, t);
  const caP = at(s.currentAssets, p);
  const ppeT = at(s.ppeNet, t);
  const ppeP = at(s.ppeNet, p);
  const taT = at(s.totalAssets, t);
  const taP = at(s.totalAssets, p);
  const depT = at(s.depreciationAmortization, t);
  const depP = at(s.depreciationAmortization, p);
  const sgaT = at(s.sgaExpense, t);
  const sgaP = at(s.sgaExpense, p);
  const clT = at(s.currentLiabilities, t);
  const clP = at(s.currentLiabilities, p);
  const debtT = at(s.totalDebt, t);
  const debtP = at(s.totalDebt, p);
  const niT = at(s.netIncome, t);
  const ocfT = at(s.operatingCashFlow, t);

  // Sum of two nullable scalars; null when either side is missing.
  const add = (a: number | null, b: number | null): number | null =>
    a === null || b === null ? null : a + b;
  // Non-zero-guarded ratio base used by AQI / DEPI / LVGI.
  const base = (num: number | null, den: number | null): number | null =>
    num === null || den === null || den === 0 ? null : num / den;

  const dsri = div(div(recvT, revT), div(recvP, revP));
  const gmi = div(div(gpP, revP), div(gpT, revT));
  const aqi = div(
    sub1(div(add(caT, ppeT), taT)),
    sub1(div(add(caP, ppeP), taP)),
  );
  const sgi = div(revT, revP);
  const depi = div(
    base(depP, add(ppeP, depP)),
    base(depT, add(ppeT, depT)),
  );
  const sgai = div(div(sgaT, revT), div(sgaP, revP));
  const lvgi = div(
    base(add(clT, debtT), taT),
    base(add(clP, debtP), taP),
  );
  const tata =
    niT === null || ocfT === null || taT === null || taT <= 0
      ? null
      : (niT - ocfT) / taT;

  const entries: [string, number | null][] = [
    ["DSRI", dsri],
    ["GMI", gmi],
    ["AQI", aqi],
    ["SGI", sgi],
    ["DEPI", depi],
    ["SGAI", sgai],
    ["LVGI", lvgi],
    ["TATA", tata],
  ];
  const missing = entries.filter(([, v]) => v === null).map(([k]) => k);

  if (
    missing.length > 0 ||
    dsri === null || gmi === null || aqi === null || sgi === null ||
    depi === null || sgai === null || lvgi === null || tata === null
  ) {
    return { m: null, flag: null, variables: null, missing };
  }

  const variables: BeneishVariables = { dsri, gmi, aqi, sgi, depi, sgai, lvgi, tata };
  const m =
    -4.84 +
    0.92 * dsri +
    0.528 * gmi +
    0.404 * aqi +
    0.892 * sgi +
    0.115 * depi -
    0.172 * sgai +
    4.679 * tata -
    0.327 * lvgi;
  return { m, flag: m > -1.78, variables, missing: [] };
}

/** 1 − v; null when v is null. (Tiny helper for the AQI "soft assets" term.) */
function sub1(v: number | null): number | null {
  return v === null ? null : 1 - v;
}

// ---------------------------------------------------------------------------
// Working-capital days
// ---------------------------------------------------------------------------

/** DSO / DIO / DPO in days; each independently null when its inputs are missing. */
export interface WorkingCapitalDays {
  /** receivables / revenue × 365. */
  dso: number | null;
  /** inventory / COGS × 365, COGS = revenue − grossProfit. */
  dio: number | null;
  /** accountsPayable / COGS × 365. */
  dpo: number | null;
}

/**
 * Working-capital days at period index i.
 *
 *   DSO = receivables / revenue × 365
 *   DIO = inventory / (revenue − grossProfit) × 365
 *   DPO = accountsPayable / (revenue − grossProfit) × 365
 *
 * Rising DSO/DIO with flat DPO means cash is being trapped in
 * receivables and inventory — a classic earnings-quality tell that
 * pairs with the Sloan accruals screen above.
 *
 * @returns null only when i is out of range; otherwise each field is
 * independently null when its own inputs are missing (or COGS is 0).
 */
export function workingCapitalDays(s: StatementSeries, i: number): WorkingCapitalDays | null {
  if (!Number.isInteger(i) || i < 0 || i >= s.periods.length) return null;
  const recv = at(s.receivables, i);
  const rev = at(s.revenue, i);
  const inv = at(s.inventory, i);
  const gp = at(s.grossProfit, i);
  const ap = at(s.accountsPayable, i);
  const cogs = rev === null || gp === null ? null : rev - gp;
  const ratioDays = (num: number | null, den: number | null): number | null =>
    num === null || den === null || den === 0 ? null : (num / den) * 365;
  return {
    dso: ratioDays(recv, rev),
    dio: ratioDays(inv, cogs),
    dpo: ratioDays(ap, cogs),
  };
}
