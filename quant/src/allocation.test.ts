// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import {
  buybackEffectiveness,
  debtProfile,
  dividendProfile,
  incrementalRoic,
  seriesCagr,
} from "./allocation.js";
import type { StatementSeries } from "./types.js";

function blank(n: number): StatementSeries {
  const empty = (): (number | null)[] => new Array(n).fill(null);
  return {
    ticker: "ALLOC",
    currency: "USD",
    periods: Array.from({ length: n }, (_, i) => ({
      period: `FY${2021 + i}`,
      periodEndDate: `${2021 + i}-12-31`,
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

/**
 * Shared 5-period fixture. Hand-computed expectations are derived in the
 * comments of each test — verify by re-running, not by re-reading.
 */
function fixture(): StatementSeries {
  const s = blank(5);
  s.sharesOutstanding = [100, 95, 90, 88, 80];
  s.shareBuybacks = [50, 60, 40, 55, 70];
  s.price = [10, 11, 12, 13, 14];
  s.dividendsPaid = [20, 22, 22, 25, 30];
  s.netIncome = [60, 70, 80, 90, 100];
  s.freeCashFlow = [80, 90, 100, 110, 120];
  s.ebit = [100, 110, 125, 140, 200];
  s.totalDebt = [500, 520, 540, 560, 600];
  s.cash = [100, 110, 105, 120, 100];
  s.totalEquity = [400, 430, 460, 500, 550];
  s.interestExpense = [20, 22, 24, 25, 25];
  return s;
}

describe("seriesCagr", () => {
  it("computes first→last CAGR over the non-null span", () => {
    // (80/100)^(1/4) − 1 = 0.8^0.25 − 1 ≈ −0.0542584
    expect(seriesCagr([100, 95, 90, 88, 80])).toBeCloseTo(-0.0542584, 6);
    // (600/500)^(1/4) − 1 = 1.2^0.25 − 1 ≈ 0.0466351
    expect(seriesCagr([500, 520, 540, 560, 600])).toBeCloseTo(0.0466351, 6);
  });

  it("skips nulls and uses the non-null span", () => {
    // first=100@0, last=80@4 even with a hole in the middle
    expect(seriesCagr([100, null, 90, null, 80])).toBeCloseTo(-0.0542584, 6);
  });

  it("returns null for degenerate inputs", () => {
    expect(seriesCagr([null, null])).toBeNull();
    expect(seriesCagr([100])).toBeNull();
    expect(seriesCagr([0, 100])).toBeNull(); // non-positive base
    expect(seriesCagr([-5, 100])).toBeNull();
  });
});

describe("buybackEffectiveness", () => {
  it("prices the average buyback dollar", () => {
    const r = buybackEffectiveness(fixture());
    // shares CAGR: (80/100)^(1/4)−1 ≈ −5.42584%
    expect(r.sharesCagr).toBeCloseTo(-0.0542584, 6);
    // total spent: 50+60+40+55+70 = 275
    expect(r.totalSpent).toBe(275);
    // retired: 100 − 80 = 20
    expect(r.sharesRetired).toBe(20);
    // implied avg price: 275/20 = 13.75
    expect(r.impliedAvgPrice).toBe(13.75);
    expect(r.currentPrice).toBe(14);
    // premium vs market: (13.75−14)/14 ≈ −0.0178571 (bought 1.79% cheap)
    expect(r.premiumVsMarket).toBeCloseTo(-0.0178571, 6);
  });

  it("nulls the implied price when shares were not retired", () => {
    const s = fixture();
    s.sharesOutstanding = [80, 85, 90, 95, 100]; // net issuance
    const r = buybackEffectiveness(s);
    expect(r.sharesRetired).toBe(-20);
    expect(r.impliedAvgPrice).toBeNull();
    expect(r.premiumVsMarket).toBeNull();
  });

  it("propagates nulls on empty input", () => {
    const r = buybackEffectiveness(blank(3));
    expect(r).toEqual({
      sharesCagr: null,
      totalSpent: null,
      sharesRetired: null,
      impliedAvgPrice: null,
      currentPrice: null,
      premiumVsMarket: null,
    });
  });
});

describe("dividendProfile", () => {
  it("measures payout ratios and the DPS record", () => {
    const r = dividendProfile(fixture());
    // payout on earnings: 30/100 = 0.30
    expect(r.payoutOnEarnings).toBe(0.3);
    // payout on FCF: 30/120 = 0.25
    expect(r.payoutOnFcf).toBe(0.25);
    // dps = [0.20, 0.2316, 0.2444, 0.2841, 0.375]: 4 trailing increases
    expect(r.yearsGrown).toBe(4);
    expect(r.cuts).toBe(0);
  });

  it("counts cuts and breaks the growth streak on a flat year", () => {
    const s = fixture();
    // dps = [0.20, 0.20, 0.15, 0.25, 0.30]: flat year breaks the streak,
    // one cut (0.20 → 0.15), then two trailing increases
    s.dividendsPaid = [20, 19, 13.5, 22, 24];
    const r = dividendProfile(s);
    expect(r.yearsGrown).toBe(2);
    expect(r.cuts).toBe(1);
  });

  it("handles missing data", () => {
    const r = dividendProfile(blank(3));
    expect(r.payoutOnEarnings).toBeNull();
    expect(r.payoutOnFcf).toBeNull();
    expect(r.yearsGrown).toBe(0);
    expect(r.cuts).toBe(0);
  });
});

describe("debtProfile", () => {
  it("profiles leverage from latest values", () => {
    const r = debtProfile(fixture());
    // net debt: 600 − 100 = 500
    expect(r.netDebtLatest).toBe(500);
    // net debt / ebit: 500/200 = 2.5
    expect(r.netDebtToEbit).toBe(2.5);
    // interest coverage: 200/25 = 8
    expect(r.interestCoverage).toBe(8);
    // debt CAGR ≈ 4.66351%
    expect(r.debtCagr).toBeCloseTo(0.0466351, 6);
  });

  it("reports a net-cash position as negative net debt", () => {
    const s = fixture();
    s.cash = [700, 700, 700, 700, 700];
    const r = debtProfile(s);
    expect(r.netDebtLatest).toBe(-100);
    expect(r.netDebtToEbit).toBe(-0.5);
  });

  it("propagates nulls", () => {
    const r = debtProfile(blank(2));
    expect(r.netDebtLatest).toBeNull();
    expect(r.netDebtToEbit).toBeNull();
    expect(r.interestCoverage).toBeNull();
    expect(r.debtCagr).toBeNull();
  });
});

describe("incrementalRoic", () => {
  it("computes ΔNOPAT/ΔIC per interval", () => {
    const r = incrementalRoic(fixture());
    // t0: tax=(100−60)/100=0.40, NOPAT=60, IC=400+500−100=800
    // t1: tax=(110−70)/110≈0.3636, NOPAT=70, IC=840 → 10/40 = 0.25
    // t2: tax=(125−80)/125=0.36, NOPAT=80, IC=895 → 10/55 ≈ 0.181818
    // t3: tax=(140−90)/140≈0.3571, NOPAT=90, IC=940 → 10/45 ≈ 0.222222
    // t4: tax=(200−100)/200=0.50, NOPAT=100, IC=1050 → 10/110 ≈ 0.090909
    expect(r.byPeriod).toHaveLength(4);
    expect(r.byPeriod[0]?.period).toBe("FY2022");
    expect(r.byPeriod[0]?.value).toBeCloseTo(0.25, 6);
    expect(r.byPeriod[1]?.value).toBeCloseTo(0.181818, 5);
    expect(r.byPeriod[2]?.value).toBeCloseTo(0.222222, 5);
    expect(r.byPeriod[3]?.value).toBeCloseTo(0.090909, 5);
    // average = (0.25+0.181818+0.222222+0.090909)/4 ≈ 0.186237
    expect(r.average).toBeCloseTo(0.186237, 5);
  });

  it("nulls intervals with non-positive ΔIC", () => {
    const s = fixture();
    s.totalEquity = [400, 300, 460, 500, 550]; // IC falls t0→t1: 800 → 710
    const r = incrementalRoic(s);
    expect(r.byPeriod[0]?.value).toBeNull();
    expect(r.byPeriod[1]?.value).not.toBeNull();
  });

  it("nulls everything when inputs are missing", () => {
    const r = incrementalRoic(blank(3));
    expect(r.byPeriod.every((p) => p.value === null)).toBe(true);
    expect(r.average).toBeNull();
  });
});
