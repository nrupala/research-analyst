// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * damodaran.ts — Aswath Damodaran valuation lens (Investment Valuation /
 * Damodaran on Valuation).
 *
 * Damodaran's framework values a company from its value drivers: cash
 * flows, growth, and risk (discount rate). This module implements the
 * building blocks as pure functions — beta unlevering/relevering, CAPM
 * cost of equity, WACC with market weights, and an algebraically solved
 * reverse-DCF implied growth — and reports each driver as a signal.
 */

import { div, lastValue } from "../guards.js";
import type { StatementSeries } from "../types.js";
import type { LensContext, LensResult } from "./types.js";
import { fmtPct, seriesCagr } from "./util.js";

/**
 * Unlevered (asset) beta: beta / (1 + (1 − t) × D/E).
 * Damodaran (Investment Valuation, ch. 8): strips the financial-leverage
 * effect out of an observed equity beta so business risk can be compared
 * across capital structures. D/E should be market debt / market equity.
 * Null when any input is null or the denominator is 0.
 */
export function unleveredBeta(
  beta: number | null,
  taxRate: number | null,
  debtToEquity: number | null,
): number | null {
  if (beta === null || taxRate === null || debtToEquity === null) return null;
  const denom = 1 + (1 - taxRate) * debtToEquity;
  if (denom === 0) return null;
  return beta / denom;
}

/**
 * Relevered equity beta: unleveredBeta × (1 + (1 − t) × D/E).
 * The inverse of {@link unleveredBeta}: re-applies leverage to an asset
 * beta for a target capital structure. Null semantics as above.
 */
export function releveredBeta(
  assetBeta: number | null,
  taxRate: number | null,
  debtToEquity: number | null,
): number | null {
  if (assetBeta === null || taxRate === null || debtToEquity === null) return null;
  return assetBeta * (1 + (1 - taxRate) * debtToEquity);
}

/**
 * CAPM cost of equity: rf + beta × ERP.
 * Damodaran's risk-and-return building block (Investment Valuation,
 * ch. 7–8). All rates as decimals. Null when any input is null.
 */
export function costOfEquity(
  riskFreeRate: number | null,
  beta: number | null,
  equityRiskPremium: number | null,
): number | null {
  if (riskFreeRate === null || beta === null || equityRiskPremium === null) return null;
  return riskFreeRate + beta * equityRiskPremium;
}

/**
 * WACC with market-value weights: wE × ke + wD × kd × (1 − t),
 * where wE = mcap/(mcap+debt), wD = debt/(mcap+debt), and the pre-tax cost
 * of debt kd = interestExpense/totalDebt. Damodaran (Investment Valuation,
 * ch. 8): weights must be market values, not book. Null when market cap,
 * debt, cost of equity, interest, or tax rate is missing; when totalDebt
 * is 0 the WACC is just the cost of equity.
 */
export function damodaranWacc(
  marketCap: number | null,
  totalDebt: number | null,
  ke: number | null,
  interestExpense: number | null,
  taxRate: number | null,
): number | null {
  if (marketCap === null || totalDebt === null || ke === null) return null;
  if (marketCap <= 0 || totalDebt < 0) return null;
  const capital = marketCap + totalDebt;
  if (capital <= 0) return null;
  if (totalDebt === 0) return ke;
  if (interestExpense === null || taxRate === null) return null;
  const kdAfterTax = (interestExpense / totalDebt) * (1 - taxRate);
  return (marketCap / capital) * ke + (totalDebt / capital) * kdAfterTax;
}

/**
 * Implied perpetual FCF growth from a reverse DCF, solved algebraically.
 *
 * Constant-growth Gordon model on free cash flow:
 *   EV = FCF × (1 + g) / (r − g),   with r > g.
 * Solve for g:
 *   EV × (r − g) = FCF × (1 + g)
 *   EV×r − EV×g = FCF + FCF×g
 *   EV×r − FCF = g × (EV + FCF)
 *   g = (EV×r − FCF) / (EV + FCF).
 *
 * Reads as: "what perpetual growth rate is the current enterprise value
 * already pricing in, given this discount rate?" Null when any input is
 * missing, r ≤ 0, or EV + FCF ≤ 0. An implied g ≥ r is economically
 * impossible under the Gordon model (denominator r − g ≤ 0) — it means the
 * price cannot be justified by any constant growth rate, which the signal
 * flags explicitly.
 */
export function impliedGrowth(
  enterpriseValue: number | null,
  freeCashFlow: number | null,
  discountRate: number | null,
): number | null {
  if (enterpriseValue === null || freeCashFlow === null || discountRate === null) return null;
  if (discountRate <= 0) return null;
  const denom = enterpriseValue + freeCashFlow;
  if (denom <= 0) return null;
  return (enterpriseValue * discountRate - freeCashFlow) / denom;
}

/**
 * Damodaran value-driver lens: cash-flow level, growth, and risk.
 *
 * Signals: (1) cash-flow level — FCF margin favor ≥ 15%, caution < 5%;
 * (2) growth — FCF CAGR favor > 10%, caution < 0%; (3) risk — WACC and beta
 * decomposition, caution when WACC > 12% or beta > 1.5; (4) the reverse-DCF
 * implied perpetual growth vs. historical FCF growth ("what the price
 * already assumes"). All driver thresholds are documented heuristics, not
 * Damodaran's — his framework is the decomposition itself.
 *
 * Originator: Aswath Damodaran, Investment Valuation (1996).
 * Phrasing: "based on principles popularized by Aswath Damodaran
 * (public-domain methodology)".
 */
export function run(s: StatementSeries, ctx?: LensContext): LensResult {
  const missing: string[] = [];
  const need = (name: string, v: number | null): number | null => {
    if (v === null) missing.push(name);
    return v;
  };

  const price = need("price", lastValue(s.price));
  const shares = need("sharesOutstanding", lastValue(s.sharesOutstanding));
  const debt = need("totalDebt", lastValue(s.totalDebt));
  const cash = need("cash", lastValue(s.cash));
  const ebit = need("ebit", lastValue(s.ebit));
  const ni = need("netIncome", lastValue(s.netIncome));
  const interest = need("interestExpense", lastValue(s.interestExpense));
  const fcf = need("freeCashFlow", lastValue(s.freeCashFlow));
  const revenue = need("revenue", lastValue(s.revenue));

  const mcap = price !== null && shares !== null ? price * shares : null;
  const taxRate = ebit !== null && ni !== null && ebit > 0 ? (ebit - ni) / ebit : null;
  if (taxRate === null) missing.push("taxRate (ebit/netIncome)");
  const deRatio = mcap !== null && debt !== null && mcap > 0 ? debt / mcap : null;

  const beta = ctx?.beta ?? null;
  const rf = ctx?.riskFreeRate ?? null;
  const erp = ctx?.equityRiskPremium ?? null;
  if (beta === null) missing.push("ctx.beta");
  if (rf === null) missing.push("ctx.riskFreeRate");
  if (erp === null) missing.push("ctx.equityRiskPremium");

  const assetBeta = unleveredBeta(beta, taxRate, deRatio);
  const ke = costOfEquity(rf, beta, erp);
  const discount = damodaranWacc(mcap, debt, ke, interest, taxRate);
  const ev = mcap !== null && debt !== null && cash !== null ? mcap + debt - cash : null;

  const fcfMargin = div(fcf, revenue);
  const fcfCagr = seriesCagr(s.freeCashFlow);
  const gImplied = impliedGrowth(ev, fcf, discount);

  const signals = [
    {
      label: "Cash-flow level (FCF margin)",
      value: fmtPct(fcfMargin),
      read: (fcfMargin === null ? "neutral" : fcfMargin >= 0.15 ? "favor" : fcfMargin < 0.05 ? "caution" : "neutral") as
        | "favor"
        | "caution"
        | "neutral",
      note: "Latest FCF / revenue. Favor ≥ 15%, caution < 5% (heuristic).",
    },
    {
      label: "Growth (FCF CAGR)",
      value: fmtPct(fcfCagr),
      read: (fcfCagr === null ? "neutral" : fcfCagr > 0.1 ? "favor" : fcfCagr < 0 ? "caution" : "neutral") as
        | "favor"
        | "caution"
        | "neutral",
      note: "Compound growth of free cash flow over the available window; Damodaran's second value driver.",
    },
    {
      label: "Risk (discount rate)",
      value:
        discount === null
          ? "n/a"
          : `WACC ${fmtPct(discount)} (ke ${fmtPct(ke)}, asset β ${assetBeta === null ? "n/a" : assetBeta.toFixed(2)})`,
      read: (discount === null ? "neutral" : discount > 0.12 || (beta !== null && beta > 1.5) ? "caution" : "neutral") as
        | "favor"
        | "caution"
        | "neutral",
      note: "WACC from market weights with CAPM cost of equity; unlevered beta isolates business risk from leverage. Caution when WACC > 12% or beta > 1.5 (heuristic).",
    },
    {
      label: "Reverse DCF: implied growth",
      value:
        gImplied === null
          ? "n/a"
          : `market prices in g ≈ ${fmtPct(gImplied)} vs historical ${fmtPct(fcfCagr)}`,
      read: (gImplied === null
        ? "neutral"
        : (discount !== null && gImplied >= discount) || (fcfCagr !== null && gImplied > fcfCagr + 0.05)
          ? "caution"
          : gImplied <= 0
            ? "favor"
            : "neutral") as "favor" | "caution" | "neutral",
      note: "g = (EV×r − FCF)/(EV + FCF) from the Gordon model. Caution when no constant growth rate can justify the price (g ≥ r), or when the market demands far more growth than history delivered.",
    },
  ];

  return {
    lens: "damodaran",
    name: "Aswath Damodaran — Value Drivers",
    summary:
      "Valuation-by-drivers lens based on principles popularized by Aswath Damodaran (public-domain methodology, " +
      "Investment Valuation): value comes from cash flows, growth, and risk. The reverse DCF shows what perpetual " +
      "growth the current price already assumes.",
    signals,
    rawValues: {
      costOfEquity: ke,
      assetBeta,
      wacc: discount,
      enterpriseValue: ev,
      fcfMargin,
      fcfCagr,
      impliedGrowth: gImplied,
      taxRate,
      debtToEquity: deRatio,
    },
    missing,
  };
}
