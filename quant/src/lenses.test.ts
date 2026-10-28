// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import type { StatementSeries } from "./types.js";
import type { LensContext } from "./lenses/types.js";
import {
  grahamNumber,
  marginOfSafety,
  netCurrentAssetValue,
  run as runGraham,
} from "./lenses/graham.js";
import {
  earningsYield,
  greenblattRoic,
  rankPeers,
  run as runGreenblatt,
} from "./lenses/greenblatt.js";
import { classify, pegRatio, run as runLynch } from "./lenses/lynch.js";
import {
  costOfEquity,
  impliedGrowth,
  releveredBeta,
  run as runDamodaran,
  unleveredBeta,
  damodaranWacc as wacc,
} from "./lenses/damodaran.js";
import { ownerEarnings, run as runBuffett } from "./lenses/buffett.js";
import {
  debtCycleGauge,
  diversificationFactor,
  riskParityWeights,
  run as runDalio,
} from "./lenses/dalio.js";
import { cycleGauge, run as runMarks, secondLevel } from "./lenses/marks.js";
import { runAll } from "./lenses/index.js";

function blank(n: number, startYear = 2021): StatementSeries {
  const empty = (): (number | null)[] => new Array(n).fill(null);
  return {
    ticker: "LENS",
    currency: "USD",
    periods: Array.from({ length: n }, (_, i) => ({
      period: `FY${startYear + i}`,
      periodEndDate: `${startYear + i}-12-31`,
    })),
    revenue: empty(),
    grossProfit: empty(),
    operatingIncome: empty(),
    ebit: empty(),
    netIncome: empty(),
    epsDiluted: empty(),
    sgaExpense: empty(),
    depreciationAmortization: empty(),
    operatingCashFlow: empty(),
    capitalExpenditure: empty(),
    freeCashFlow: empty(),
    dividendsPaid: empty(),
    shareBuybacks: empty(),
    totalAssets: empty(),
    totalEquity: empty(),
    totalLiabilities: empty(),
    retainedEarnings: empty(),
    ppeNet: empty(),
    accountsPayable: empty(),
    totalDebt: empty(),
    cash: empty(),
    currentAssets: empty(),
    currentLiabilities: empty(),
    inventory: empty(),
    receivables: empty(),
    interestExpense: empty(),
    taxExpense: empty(),
    sharesOutstanding: empty(),
    price: empty(),
  };
}

const CTX: LensContext = { beta: 1.2, riskFreeRate: 0.04, equityRiskPremium: 0.05 };

// ---------------------------------------------------------------- graham

describe("graham", () => {
  it("netCurrentAssetValue = currentAssets − totalLiabilities", () => {
    expect(netCurrentAssetValue(600, 500)).toBe(100);
    expect(netCurrentAssetValue(null, 500)).toBeNull();
  });

  it("grahamNumber = sqrt(22.5 × eps × bvps)", () => {
    // sqrt(22.5 × 1.5 × 6) = sqrt(202.5) ≈ 14.23025
    expect(grahamNumber(1.5, 6)).toBeCloseTo(14.23025, 4);
    expect(grahamNumber(-1, 6)).toBeNull();
    expect(grahamNumber(1.5, null)).toBeNull();
  });

  it("marginOfSafety = (iv − price)/iv", () => {
    expect(marginOfSafety(100, 80)).toBe(0.2);
    expect(marginOfSafety(100, 120)).toBe(-0.2);
    expect(marginOfSafety(0, 80)).toBeNull();
  });

  it("fires the net-net rule strictly below ⅔ NCAV/share", () => {
    // NCAV = 600−500 = 100; shares 50 → NCAV/share = 2.00; ⅔ line = 1.3333…
    const at = (p: number): StatementSeries => {
      const s = blank(2);
      s.currentAssets = [600, 600];
      s.totalLiabilities = [500, 500];
      s.sharesOutstanding = [50, 50];
      s.price = [1.25, p];
      return s;
    };
    const below = runGraham(at(1.2));
    const netnetBelow = below.signals.find((x) => x.label.startsWith("Net-net"));
    expect(netnetBelow?.read).toBe("favor");

    const boundary = runGraham(at(4 / 3)); // exactly on the ⅔ line
    const netnetBoundary = boundary.signals.find((x) => x.label.startsWith("Net-net"));
    expect(netnetBoundary?.read).toBe("neutral"); // strictly-less rule

    expect(below.rawValues.ncavPerShare).toBe(2);
  });

  it("grades the seven defensive screens", () => {
    const s = blank(3);
    s.currentAssets = [500, 550, 600];
    s.currentLiabilities = [180, 190, 200]; // ratio 3.0 → pass
    s.totalLiabilities = [450, 480, 500];
    s.sharesOutstanding = [50, 50, 50];
    s.price = [10, 11, 12];
    s.epsDiluted = [1.0, 1.2, 1.5]; // growth 50% → pass
    s.netIncome = [50, 60, 70]; // all > 0 → pass
    s.dividendsPaid = [10, 12, 14]; // all > 0 → pass
    s.totalEquity = [280, 290, 300]; // bvps 6 → P/B = 2 → FAIL
    const r = runGraham(s);
    const read = (label: string): string | undefined =>
      r.signals.find((x) => x.label === label)?.read;
    expect(read("Defensive: current ratio ≥ 2")).toBe("favor");
    expect(read("Defensive: positive earnings every year")).toBe("favor");
    expect(read("Defensive: uninterrupted dividends")).toBe("favor");
    expect(read("Defensive: EPS growth ≥ 33%")).toBe("favor");
    expect(read("Defensive: P/E ≤ 15")).toBe("favor"); // 12/1.5 = 8
    expect(read("Defensive: P/B ≤ 1.5")).toBe("caution"); // 12/6 = 2
    expect(read("Defensive: P/E × P/B ≤ 22.5")).toBe("favor"); // 16
    expect(r.rawValues.grahamNumber).toBeCloseTo(14.23025, 4);
    // MOS = (14.23025 − 12)/14.23025 ≈ 0.15673 → favor
    expect(r.rawValues.marginOfSafety).toBeCloseTo(0.15673, 4);
    expect(r.lens).toBe("graham");
  });

  it("fails the P/E screen on negative earnings", () => {
    const s = blank(1);
    s.price = [10];
    s.epsDiluted = [-1];
    const r = runGraham(s);
    expect(r.signals.find((x) => x.label === "Defensive: P/E ≤ 15")?.read).toBe("caution");
  });
});

// ------------------------------------------------------------- greenblatt

describe("greenblatt", () => {
  it("computes roic and earnings yield", () => {
    // roic = 200/(800+500−100) = 200/1200 ≈ 0.166667
    expect(greenblattRoic(200, 800, 500, 100)).toBeCloseTo(0.166667, 5);
    // EV = 20×50+500−100 = 1400; EY = 200/1400 ≈ 0.142857
    expect(earningsYield(200, 20, 50, 500, 100)).toBeCloseTo(0.142857, 5);
    expect(greenblattRoic(200, 800, 500, null)).toBeNull();
  });

  it("scores quality/value with the documented thresholds", () => {
    const s = blank(3);
    s.ebit = [150, 180, 200];
    s.totalEquity = [700, 750, 800];
    s.totalDebt = [450, 480, 500];
    s.cash = [80, 90, 100];
    s.price = [18, 19, 20];
    s.sharesOutstanding = [50, 50, 50];
    const r = runGreenblatt(s);
    const read = (label: string): string | undefined =>
      r.signals.find((x) => x.label === label)?.read;
    expect(r.rawValues.roic).toBeCloseTo(0.166667, 5);
    expect(read("Quality: return on capital")).toBe("neutral"); // 16.7% between 5% and 20%
    expect(read("Value: earnings yield")).toBe("favor"); // 14.3% ≥ 8%
    expect(read("Magic Formula composite")).toBe("neutral");
  });

  it("rankPeers implements the actual Magic Formula ordering", () => {
    const peers = [
      { id: "A", roic: 0.2, earningsYield: 0.1 },
      { id: "B", roic: 0.15, earningsYield: 0.12 },
      { id: "C", roic: 0.25, earningsYield: 0.05 },
      { id: "D", roic: 0.1, earningsYield: 0.08 },
    ];
    // roic ranks: C=1, A=2, B=3, D=4; EY ranks: B=1, A=2, D=3, C=4
    // composites: A=4, B=4, C=5, D=7 → order A, B, C, D (tie broken by id)
    const ranked = rankPeers(peers);
    expect(ranked.map((p) => p.id)).toEqual(["A", "B", "C", "D"]);
    expect(ranked[0]).toMatchObject({ roicRank: 2, eyRank: 2, composite: 4, order: 1 });
    expect(ranked[1]).toMatchObject({ roicRank: 3, eyRank: 1, composite: 4, order: 2 });
    expect(ranked[2]).toMatchObject({ roicRank: 1, eyRank: 4, composite: 5, order: 3 });
    expect(ranked[3]).toMatchObject({ roicRank: 4, eyRank: 3, composite: 7, order: 4 });
  });

  it("rankPeers ranks null factors last", () => {
    const ranked = rankPeers([
      { id: "A", roic: 0.2, earningsYield: 0.1 },
      { id: "E", roic: null, earningsYield: 0.09 },
    ]);
    const e = ranked.find((p) => p.id === "E");
    expect(e?.roicRank).toBe(2); // null is worse than any number
    expect(e?.order).toBe(2);
  });
});

// ----------------------------------------------------------------- lynch

describe("lynch", () => {
  it("pegRatio uses percent units", () => {
    // pe 17.14 / growth 20.5% ≈ 0.836
    expect(pegRatio(17.142857, 20.5)).toBeCloseTo(0.836, 3);
    expect(pegRatio(15, 0)).toBeNull();
    expect(pegRatio(15, -5)).toBeNull();
    expect(pegRatio(null, 15)).toBeNull();
  });

  it("classifies a fast grower and prices its PEG", () => {
    const s = blank(4);
    s.epsDiluted = [1.0, 1.2, 1.45, 1.75]; // CAGR ≈ 20.51%
    s.netIncome = [100, 120, 145, 175];
    s.price = [24, 26, 28, 30];
    s.revenue = [1000, 1100, 1250, 1400];
    const d = classify(s);
    expect(d.classification).toBe("fast grower");
    // (1.75/1.0)^(1/3) − 1 ≈ 0.20507
    expect(d.epsCagr).toBeCloseTo(0.20507, 4);
    const r = runLynch(s);
    // pe = 30/1.75 ≈ 17.1429; peg ≈ 17.1429/20.507 ≈ 0.8359 → favor
    expect(r.rawValues.peg).toBeCloseTo(0.8359, 3);
    expect(r.signals.find((x) => x.label === "PEG ratio")?.read).toBe("favor");
  });

  it("flags a cyclical on earnings sign changes", () => {
    const s = blank(4);
    s.netIncome = [100, -20, 80, -10]; // 3 sign flips
    s.epsDiluted = [1, 1.1, 1.2, 1.3];
    const d = classify(s);
    expect(d.classification).toBe("cyclical");
    expect(d.signChanges).toBe(3);
    const r = runLynch(s);
    expect(r.signals.find((x) => x.label === "Cyclical timing")?.read).toBe("caution");
  });

  it("detects an asset play", () => {
    const s = blank(3);
    s.netIncome = [50, 55, 60];
    s.epsDiluted = [1, 1.05, 1.1]; // CAGR ≈ 4.9% — slow, but asset screen comes first
    s.price = [5, 5, 5];
    s.totalEquity = [800, 820, 840]; // bvps 16.8 → P/B ≈ 0.30
    s.sharesOutstanding = [50, 50, 50];
    s.cash = [300, 320, 340];
    s.totalAssets = [1000, 1050, 1100]; // cash/assets ≈ 30.9%
    const d = classify(s);
    expect(d.classification).toBe("asset play");
  });

  it("detects a turnaround", () => {
    const s = blank(4);
    s.netIncome = [-40, -10, 25, 60]; // early loss → last-2y profit; 1 flip only, so not cyclical
    const d = classify(s);
    expect(d.classification).toBe("turnaround");
  });
});

// ------------------------------------------------------------- damodaran

describe("damodaran", () => {
  it("unlevers and relevers beta", () => {
    // 1.2 / (1 + 0.75×0.5) = 1.2/1.375 ≈ 0.872727
    expect(unleveredBeta(1.2, 0.25, 0.5)).toBeCloseTo(0.872727, 5);
    expect(releveredBeta(0.872727, 0.25, 0.5)).toBeCloseTo(1.2, 5);
    expect(unleveredBeta(null, 0.25, 0.5)).toBeNull();
  });

  it("costOfEquity = rf + β × ERP", () => {
    expect(costOfEquity(0.04, 1.2, 0.05)).toBeCloseTo(0.1, 8);
  });

  it("wacc uses market weights", () => {
    // mcap 1000, debt 500, ke 0.10, kd = 25/500 = 5% pre-tax, t = 25%
    // = (2/3)(0.10) + (1/3)(0.05)(0.75) ≈ 0.0791667
    expect(wacc(1000, 500, 0.1, 25, 0.25)).toBeCloseTo(0.0791667, 6);
    expect(wacc(1000, 0, 0.1, 25, 0.25)).toBe(0.1); // unlevered → ke
    expect(wacc(null, 500, 0.1, 25, 0.25)).toBeNull();
  });

  it("impliedGrowth solves the Gordon model algebraically", () => {
    // g = (1400×0.0791667 − 80)/(1400+80) = 30.8333/1480 ≈ 0.0208333
    expect(impliedGrowth(1400, 80, 0.0791667)).toBeCloseTo(0.0208333, 5);
    // sanity: plug back — FCF×(1+g)/(r−g) should recover EV
    const g = impliedGrowth(1400, 80, 0.0791667) as number;
    expect((80 * (1 + g)) / (0.0791667 - g)).toBeCloseTo(1400, 3);
    expect(impliedGrowth(1400, 80, 0)).toBeNull();
    expect(impliedGrowth(null, 80, 0.08)).toBeNull();
  });

  it("reports the three value drivers", () => {
    const s = blank(5);
    s.price = [16, 17, 18, 19, 20];
    s.sharesOutstanding = [50, 50, 50, 50, 50]; // mcap 1000
    s.totalDebt = [500, 500, 500, 500, 500];
    s.cash = [100, 100, 100, 100, 100]; // EV 1400
    s.ebit = [180, 185, 190, 195, 200];
    s.netIncome = [135, 139, 142, 146, 150]; // tax rate 25%
    s.interestExpense = [25, 25, 25, 25, 25];
    s.freeCashFlow = [60, 65, 70, 75, 80]; // CAGR ≈ 7.457%
    s.revenue = [900, 930, 960, 980, 1000]; // FCF margin 8%
    const r = runDamodaran(s, CTX);
    expect(r.rawValues.costOfEquity).toBeCloseTo(0.1, 8);
    expect(r.rawValues.assetBeta).toBeCloseTo(0.872727, 5);
    expect(r.rawValues.wacc).toBeCloseTo(0.0791667, 6);
    expect(r.rawValues.impliedGrowth).toBeCloseTo(0.0208333, 5);
    expect(r.rawValues.fcfMargin).toBe(0.08);
    // (80/60)^0.25 − 1 ≈ 0.07457
    expect(r.rawValues.fcfCagr).toBeCloseTo(0.07457, 4);
    const read = (label: string): string | undefined =>
      r.signals.find((x) => x.label === label)?.read;
    expect(read("Cash-flow level (FCF margin)")).toBe("neutral"); // 8% in [5%, 15%)
    expect(read("Growth (FCF CAGR)")).toBe("neutral");
    expect(read("Risk (discount rate)")).toBe("neutral");
  });
});

// ---------------------------------------------------------------- buffett

describe("buffett", () => {
  it("ownerEarnings = NI + D&A − capex − ΔWC", () => {
    // 100 + 30 − 40 − 20 = 70
    expect(ownerEarnings(100, 30, 40, 20)).toBe(70);
    // a working-capital release ADDS to owner earnings
    expect(ownerEarnings(100, 30, 40, -15)).toBe(105);
    expect(ownerEarnings(100, 30, null, 20)).toBeNull();
  });

  it("measures owner earnings, moat, and the equity bond", () => {
    const s = blank(5);
    s.netIncome = [60, 70, 80, 90, 100];
    s.depreciationAmortization = [25, 26, 28, 29, 30];
    s.capitalExpenditure = [35, 36, 38, 39, 40];
    s.currentAssets = [240, 260, 280, 300, 330];
    s.currentLiabilities = [120, 130, 140, 150, 160]; // ΔWC = 170−150 = 20
    s.ebit = [100, 110, 125, 140, 200];
    s.totalEquity = [400, 430, 460, 500, 550];
    s.totalDebt = [500, 520, 540, 560, 600];
    s.cash = [100, 110, 105, 120, 100];
    s.grossProfit = [400, 451, 492, 533, 615];
    s.revenue = [1000, 1100, 1200, 1300, 1500]; // margins ≈ flat 41% → CV ≈ 0.0098
    s.price = [10, 11, 12, 13, 20];
    s.sharesOutstanding = [100, 95, 90, 88, 50]; // mcap 1000

    const r = runBuffett(s, CTX);
    // owner earnings: 100+30−40−20 = 70
    expect(r.rawValues.ownerEarnings).toBe(70);
    // OEY = 70/1000 = 7%; rf 4% → spread 3pp, not > 3pp → neutral
    expect(r.rawValues.ownerEarningsYield).toBeCloseTo(0.07, 8);
    // ROIC: 12.5%, 13.1%, 14.0%, 14.9%, 19.0% → 1 of 5 years ≥ 15%
    expect(r.rawValues.moatYears).toBe(1);
    expect(r.rawValues.moatPeriods).toBe(5);
    expect(r.rawValues.grossMarginCv).toBeCloseTo(0.0098, 3);
    const read = (label: string): string | undefined =>
      r.signals.find((x) => x.label === label)?.read;
    expect(read("Moat: years of ROIC ≥ 15%")).toBe("neutral");
    expect(read("Gross-margin stability")).toBe("favor");
    expect(read("Equity bond: owner-earnings yield vs risk-free")).toBe("neutral");

    // cheaper risk-free rate → the equity bond pays a spread → favor
    const r2 = runBuffett(s, { beta: 1.2, riskFreeRate: 0.03, equityRiskPremium: 0.05 });
    expect(r2.signals.find((x) => x.label.startsWith("Equity bond"))?.read).toBe("favor");
  });
});

// ------------------------------------------------------------------ dalio

describe("dalio", () => {
  it("diversificationFactor follows the holy-grail curve", () => {
    expect(diversificationFactor(1, 0.3)).toBe(1); // no diversification
    // (1 + 14×0.3)/15 = 5.2/15 ≈ 0.346667
    expect(diversificationFactor(15, 0.3)).toBeCloseTo(0.346667, 5);
    // uncorrelated streams diversify to ~1/n
    expect(diversificationFactor(20, 0)).toBeCloseTo(0.05, 8);
    expect(diversificationFactor(0, 0.3)).toBeNull();
    expect(diversificationFactor(5, null)).toBeNull();
  });

  it("riskParityWeights allocates inverse to volatility", () => {
    // (1/0.2, 1/0.1)/15 = (1/3, 2/3)
    const w = riskParityWeights([0.2, 0.1]);
    expect(w?.[0]).toBeCloseTo(1 / 3, 8);
    expect(w?.[1]).toBeCloseTo(2 / 3, 8);
    expect(w?.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 10);
    expect(riskParityWeights([0.2, 0])).toBeNull();
    expect(riskParityWeights([0.2, null])).toBeNull();
    expect(riskParityWeights([])).toBeNull();
  });

  it("debtCycleGauge reads the credit-vs-income race", () => {
    expect(debtCycleGauge(0.2, 0.1)).toBe("expansion"); // +10pp gap
    expect(debtCycleGauge(0.02, 0.1)).toBe("contraction");
    expect(debtCycleGauge(0.08, 0.1)).toBe("stable");
    expect(debtCycleGauge(null, 0.1)).toBeNull();
  });

  it("flags a credit expansion outrunning revenue", () => {
    const s = blank(3);
    s.totalLiabilities = [500, 600, 720]; // CAGR 20%
    s.revenue = [1000, 1100, 1210]; // CAGR 10%
    s.totalAssets = [2000, 2200, 2500]; // leverage 25% → 28.8%
    const r = runDalio(s);
    expect(r.rawValues.liabilitiesCagr).toBeCloseTo(0.2, 8);
    expect(r.rawValues.revenueCagr).toBeCloseTo(0.1, 8);
    expect(r.rawValues.leverageDelta).toBeCloseTo(0.038, 5);
    expect(r.signals.find((x) => x.label === "Debt-cycle gauge")?.value).toMatch(/expansion/);
  });
});

// ------------------------------------------------------------------ marks

describe("marks", () => {
  it("cycleGauge blends valuation percentile and debt growth", () => {
    // 0.6×80 + 0.4×clamp(0.15×100) = 48 + 6 = 54
    expect(cycleGauge(80, 0.15)).toBe(54);
    // debt growth caps at a score of 100: 0.6×50 + 0.4×100 = 70
    expect(cycleGauge(50, 2.0)).toBe(70);
    expect(cycleGauge(null, 0.15)).toBeNull();
  });

  it("secondLevel validates probabilities and prices the consensus-wrong spread", () => {
    const ok = secondLevel([
      { label: "base", value: 100, probability: 0.5 },
      { label: "down", value: 60, probability: 0.3 },
      { label: "tail", value: -20, probability: 0.2 },
    ]);
    expect(ok.valid).toBe(true);
    // EV = 50 + 18 − 4 = 64; spread = 100 − (−20) = 120
    expect(ok.expectedValue).toBe(64);
    expect(ok.spread).toBe(120);

    const bad = secondLevel([
      { label: "a", value: 1, probability: 0.5 },
      { label: "b", value: 2, probability: 0.5 },
      { label: "c", value: 3, probability: 0.5 },
    ]);
    expect(bad.valid).toBe(false); // sums to 1.5
    expect(bad.probabilitySum).toBeCloseTo(1.5, 10);
    expect(bad.expectedValue).toBeNull();
    expect(bad.spread).toBeNull();
  });

  it("locates the cycle from P/E history and debt growth", () => {
    const s = blank(5);
    s.price = [20, 22, 24, 26, 30];
    s.epsDiluted = [2, 2, 2, 2, 1.5]; // P/E: 10, 11, 12, 13, 20
    s.totalDebt = [500, 520, 540, 560, 600]; // CAGR ≈ 4.66351%
    const r = runMarks(s, { ...CTX, forensicFlags: ["beneish-m-score"] });
    // percentile of 20 in [10,11,12,13,20]: (4 + 0.5)/5×100 = 90
    expect(r.rawValues.valuationPercentile).toBe(90);
    // gauge = 0.6×90 + 0.4×4.66351 ≈ 55.8654 → neutral band
    expect(r.rawValues.cycleGauge).toBeCloseTo(55.8654, 3);
    expect(r.signals.find((x) => x.label === "Cycle gauge")?.read).toBe("neutral");
    // 90th percentile > 75 → valuation caution
    expect(r.signals.find((x) => x.label === "Valuation vs history")?.read).toBe("caution");
    // forensic flag passthrough
    const flag = r.signals.find((x) => x.label === "Forensic flag: beneish-m-score");
    expect(flag?.read).toBe("caution");
    expect(r.rawValues.forensicFlagCount).toBe(1);
  });
});

// ----------------------------------------------------------------- runAll

describe("runAll", () => {
  it("runs all seven lenses without throwing on sparse data", () => {
    const results = runAll(blank(3));
    expect(results).toHaveLength(7);
    expect(results.map((r) => r.lens)).toEqual([
      "graham",
      "greenblatt",
      "lynch",
      "damodaran",
      "buffett",
      "dalio",
      "marks",
    ]);
    for (const r of results) {
      expect(r.missing.length).toBeGreaterThan(0);
      expect(Array.isArray(r.signals)).toBe(true);
    }
  });

  it("shares one context across lenses", () => {
    const s = blank(2);
    s.price = [10, 10];
    const results = runAll(s, CTX);
    expect(results.every((r) => typeof r.summary === "string" && r.summary.length > 0)).toBe(true);
  });
});
