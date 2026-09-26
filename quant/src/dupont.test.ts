// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { dupontPoint, dupontSeries, roeAttribution } from "./dupont.js";
import type { StatementSeries } from "./types.js";

function blankSeries(n: number): StatementSeries {
  const blank = (): (number | null)[] => new Array(n).fill(null);
  return {
    ticker: "TEST",
    currency: "USD",
    periods: Array.from({ length: n }, (_, i) => ({
      period: `FY${2023 + i}`,
      periodEndDate: `${2023 + i}-12-31`,
    })),
    revenue: blank(),
    grossProfit: blank(),
    operatingIncome: blank(),
    ebit: blank(),
    netIncome: blank(),
    epsDiluted: blank(),
    sgaExpense: blank(),
    depreciationAmortization: blank(),
    operatingCashFlow: blank(),
    capitalExpenditure: blank(),
    freeCashFlow: blank(),
    dividendsPaid: blank(),
    shareBuybacks: blank(),
    totalAssets: blank(),
    totalEquity: blank(),
    totalLiabilities: blank(),
    retainedEarnings: blank(),
    ppeNet: blank(),
    accountsPayable: blank(),
    totalDebt: blank(),
    cash: blank(),
    currentAssets: blank(),
    currentLiabilities: blank(),
    inventory: blank(),
    receivables: blank(),
    interestExpense: blank(),
    taxExpense: blank(),
    sharesOutstanding: blank(),
    price: blank(),
  };
}

describe("dupontPoint", () => {
  it("decomposes ROE into its three factors (hand-computed)", () => {
    // NI=100, rev=1000, avgAssets=500, avgEquity=250:
    //   netMargin     = 100/1000 = 0.1
    //   assetTurnover = 1000/500  = 2
    //   leverage      = 500/250   = 2
    //   roe           = 100/250   = 0.4  (= 0.1 × 2 × 2)
    const p = dupontPoint(100, 1000, 500, 250);
    expect(p).not.toBeNull();
    expect(p!.netMargin).toBeCloseTo(0.1, 10);
    expect(p!.assetTurnover).toBeCloseTo(2, 10);
    expect(p!.leverage).toBeCloseTo(2, 10);
    expect(p!.roe).toBeCloseTo(0.4, 10);
    // roe equals the product of the three factors
    expect(p!.netMargin * p!.assetTurnover * p!.leverage).toBeCloseTo(p!.roe, 10);
  });

  it("returns null on missing or degenerate inputs", () => {
    expect(dupontPoint(null, 1000, 500, 250)).toBeNull(); // missing NI
    expect(dupontPoint(100, null, 500, 250)).toBeNull(); // missing revenue
    expect(dupontPoint(100, 1000, null, 250)).toBeNull(); // missing assets
    expect(dupontPoint(100, 1000, 500, null)).toBeNull(); // missing equity
    expect(dupontPoint(100, 0, 500, 250)).toBeNull(); // zero revenue
    expect(dupontPoint(100, 1000, 0, 250)).toBeNull(); // zero assets
    expect(dupontPoint(100, 1000, -50, 250)).toBeNull(); // negative assets
    expect(dupontPoint(100, 1000, 500, 0)).toBeNull(); // zero equity
    expect(dupontPoint(100, 1000, 500, -250)).toBeNull(); // negative equity
  });
});

describe("dupontSeries", () => {
  function fixture(): StatementSeries {
    const s = blankSeries(3);
    s.netIncome = [80, 100, 120];
    s.revenue = [800, 1000, 1100];
    s.totalAssets = [400, 500, 600];
    s.totalEquity = [200, 250, 300];
    return s;
  }

  it("uses current-only values for the first period, averages afterwards", () => {
    const rows = dupontSeries(fixture());
    expect(rows).toHaveLength(3);
    expect(rows[0]!.period).toBe("FY2023");

    // Period 0: no prior → avgAssets=400, avgEquity=200
    //   margin=80/800=0.1, turnover=800/400=2, leverage=400/200=2, roe=80/200=0.4
    expect(rows[0]!.netMargin).toBeCloseTo(0.1, 10);
    expect(rows[0]!.assetTurnover).toBeCloseTo(2, 10);
    expect(rows[0]!.leverage).toBeCloseTo(2, 10);
    expect(rows[0]!.roe).toBeCloseTo(0.4, 10);

    // Period 1: avgAssets=(500+400)/2=450, avgEquity=(250+200)/2=225
    //   margin=100/1000=0.1, turnover=1000/450=2.2222, leverage=450/225=2,
    //   roe=100/225=0.44444
    expect(rows[1]!.netMargin).toBeCloseTo(0.1, 10);
    expect(rows[1]!.assetTurnover).toBeCloseTo(2.2222222222, 8);
    expect(rows[1]!.leverage).toBeCloseTo(2, 10);
    expect(rows[1]!.roe).toBeCloseTo(0.4444444444, 8);

    // Period 2: avgAssets=(600+500)/2=550, avgEquity=(300+250)/2=275
    //   margin=120/1100=0.1090909, turnover=1100/550=2, leverage=550/275=2,
    //   roe=120/275=0.4363636
    expect(rows[2]!.netMargin).toBeCloseTo(0.1090909091, 8);
    expect(rows[2]!.assetTurnover).toBeCloseTo(2, 10);
    expect(rows[2]!.leverage).toBeCloseTo(2, 10);
    expect(rows[2]!.roe).toBeCloseTo(0.4363636364, 8);
  });

  it("nulls only the row with missing inputs", () => {
    const s = fixture();
    s.netIncome = [80, null, 120];
    const rows = dupontSeries(s);
    expect(rows[0]!.roe).toBeCloseTo(0.4, 10);
    expect(rows[1]).toMatchObject({
      netMargin: null,
      assetTurnover: null,
      leverage: null,
      roe: null,
    });
    expect(rows[2]!.roe).toBeCloseTo(0.4363636364, 8);
  });
});

describe("roeAttribution", () => {
  it("attributes the ROE change to the three factors in percentage points", () => {
    // first:  m=0.10, t=2.0, l=2.0, roe=0.40
    // last:   m=0.12, t=1.8, l=2.2, roe=0.4752  (0.12×1.8×2.2)
    // ΔROE = 0.0752 = 7.52 pp
    // contribution_i = ln(c_last/c_first)/ln(roe_last/roe_first) × ΔROE × 100
    //   margin:   ln(1.2)/ln(1.188) × 7.52 = 7.9587182328
    //   turnover: ln(0.9)/ln(1.188) × 7.52 = −4.5992074208
    //   leverage: ln(1.1)/ln(1.188) × 7.52 = 4.1604891880
    const a = roeAttribution(
      { netMargin: 0.1, assetTurnover: 2, leverage: 2, roe: 0.4 },
      { netMargin: 0.12, assetTurnover: 1.8, leverage: 2.2, roe: 0.4752 },
    );
    expect(a).not.toBeNull();
    expect(a!.marginPts).toBeCloseTo(7.9587182328, 4);
    expect(a!.turnoverPts).toBeCloseTo(-4.5992074208, 4);
    expect(a!.leveragePts).toBeCloseTo(4.160489188, 4);
    // contributions sum to the ROE change in percentage points
    expect(a!.marginPts + a!.turnoverPts + a!.leveragePts).toBeCloseTo(7.52, 8);
  });

  it("returns null when attribution is undefined", () => {
    const good = { netMargin: 0.1, assetTurnover: 2, leverage: 2, roe: 0.4 };
    const better = { netMargin: 0.12, assetTurnover: 1.8, leverage: 2.2, roe: 0.4752 };
    // non-positive component → ln undefined
    expect(
      roeAttribution({ ...good, netMargin: -0.05 }, better),
    ).toBeNull();
    expect(
      roeAttribution(good, { ...better, assetTurnover: 0 }),
    ).toBeNull();
    // null component
    expect(roeAttribution({ ...good, roe: null }, better)).toBeNull();
    // non-positive roe
    expect(
      roeAttribution({ ...good, roe: -0.1 }, { ...better, roe: -0.05 }),
    ).toBeNull();
    // unchanged roe → ln(1) = 0 denominator
    expect(roeAttribution(good, { ...better, roe: 0.4 })).toBeNull();
  });
});
