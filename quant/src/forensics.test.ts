// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import {
  altmanZ,
  beneishM,
  cashConversion,
  sloanAccruals,
  workingCapitalDays,
} from "./forensics.js";
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

describe("sloanAccruals", () => {
  it("computes (NI − OCF) / TA (hand-computed)", () => {
    // (100 − 140) / 1000 = −0.04 → cash earnings exceed reported profit
    expect(sloanAccruals(100, 140, 1000)).toBeCloseTo(-0.04, 10);
    // (150 − 100) / 1000 = 0.05 → positive accruals
    expect(sloanAccruals(150, 100, 1000)).toBeCloseTo(0.05, 10);
  });

  it("returns null on missing or degenerate inputs", () => {
    expect(sloanAccruals(null, 140, 1000)).toBeNull();
    expect(sloanAccruals(100, null, 1000)).toBeNull();
    expect(sloanAccruals(100, 140, null)).toBeNull();
    expect(sloanAccruals(100, 140, 0)).toBeNull();
    expect(sloanAccruals(100, 140, -100)).toBeNull();
  });
});

describe("cashConversion", () => {
  it("computes OCF / NI (hand-computed)", () => {
    expect(cashConversion(140, 100)).toBeCloseTo(1.4, 10);
    // negative earnings still yield a (negative) ratio — null means no data
    expect(cashConversion(50, -100)).toBeCloseTo(-0.5, 10);
  });

  it("returns null when net income is zero or inputs are missing", () => {
    expect(cashConversion(140, 0)).toBeNull();
    expect(cashConversion(null, 100)).toBeNull();
    expect(cashConversion(140, null)).toBeNull();
  });
});

describe("altmanZ", () => {
  function safeFixture(): StatementSeries {
    const s = blankSeries(1);
    s.currentAssets = [600];
    s.currentLiabilities = [300];
    s.totalAssets = [2000];
    s.retainedEarnings = [800];
    s.ebit = [300];
    s.price = [50];
    s.sharesOutstanding = [100];
    s.totalLiabilities = [1500];
    s.revenue = [3000];
    return s;
  }

  it("scores a healthy manufacturer as safe (hand-computed)", () => {
    // X1=(600−300)/2000=0.15, X2=800/2000=0.4, X3=300/2000=0.15,
    // X4=(50×100)/1500=3.3333, X5=3000/2000=1.5
    // Z = 1.2(0.15)+1.4(0.4)+3.3(0.15)+0.6(3.3333)+1.0(1.5)
    //   = 0.18+0.56+0.495+2.0+1.5 = 4.735 > 2.99 → safe
    const r = altmanZ(safeFixture(), 0);
    expect(r.z).toBeCloseTo(4.735, 4);
    expect(r.zone).toBe("safe");
    if (r.components !== null) {
      expect(r.components.x1).toBeCloseTo(0.15, 10);
      expect(r.components.x2).toBeCloseTo(0.4, 10);
      expect(r.components.x3).toBeCloseTo(0.15, 10);
      expect(r.components.x4).toBeCloseTo(3.3333333333, 8);
      expect(r.components.x5).toBeCloseTo(1.5, 10);
    } else {
      expect.unreachable();
    }
    expect(r.missing).toEqual([]);
  });

  it("scores a middling firm as grey (hand-computed)", () => {
    const s = blankSeries(1);
    s.currentAssets = [400];
    s.currentLiabilities = [300];
    s.totalAssets = [2000];
    s.retainedEarnings = [400];
    s.ebit = [100];
    s.price = [20];
    s.sharesOutstanding = [100];
    s.totalLiabilities = [1500];
    s.revenue = [2000];
    // X1=0.05, X2=0.2, X3=0.05, X4=2000/1500=1.3333, X5=1.0
    // Z = 0.06+0.28+0.165+0.8+1.0 = 2.305 → grey
    const r = altmanZ(s, 0);
    expect(r.z).toBeCloseTo(2.305, 4);
    expect(r.zone).toBe("grey");
  });

  it("scores a distressed firm as distress (hand-computed)", () => {
    const s = blankSeries(1);
    s.currentAssets = [200];
    s.currentLiabilities = [300];
    s.totalAssets = [2000];
    s.retainedEarnings = [-200];
    s.ebit = [50];
    s.price = [5];
    s.sharesOutstanding = [100];
    s.totalLiabilities = [1500];
    s.revenue = [1000];
    // X1=−0.05, X2=−0.1, X3=0.025, X4=500/1500=0.3333, X5=0.5
    // Z = −0.06−0.14+0.0825+0.2+0.5 = 0.5825 < 1.81 → distress
    const r = altmanZ(s, 0);
    expect(r.z).toBeCloseTo(0.5825, 4);
    expect(r.zone).toBe("distress");
  });

  it("reports missing inputs instead of a score", () => {
    const s = safeFixture();
    s.ebit = [null];
    const r = altmanZ(s, 0);
    expect(r.z).toBeNull();
    expect(r.zone).toBeNull();
    expect(r.components).toBeNull();
    expect(r.missing).toContain("ebit");

    const s2 = safeFixture();
    s2.totalLiabilities = [0];
    expect(altmanZ(s2, 0).missing).toContain("totalLiabilities");
  });

  it("reports an out-of-range period index", () => {
    const r = altmanZ(safeFixture(), 5);
    expect(r.z).toBeNull();
    expect(r.missing).toEqual(["periodIndex"]);
  });
});

describe("beneishM", () => {
  /** Two-period fixture; t−1 is the shared base year. */
  function base(): StatementSeries {
    const s = blankSeries(2);
    s.revenue = [1000, 1200];
    s.receivables = [100, 150];
    s.grossProfit = [400, 420];
    s.currentAssets = [500, 600];
    s.ppeNet = [300, 320];
    s.totalAssets = [2000, 2200];
    s.depreciationAmortization = [50, 60];
    s.sgaExpense = [200, 264];
    s.currentLiabilities = [300, 330];
    s.totalDebt = [400, 440];
    s.netIncome = [120, 132];
    s.operatingCashFlow = [100, 90];
    return s;
  }

  it("computes all eight variables and clears the screen (hand-computed)", () => {
    // DSRI = (150/1200)/(100/1000) = 0.125/0.1 = 1.25
    // GMI  = 0.4/(420/1200) = 0.4/0.35 = 1.1428571429
    // AQI  = [1−(600+320)/2200]/[1−(500+300)/2000] = 0.58181818/0.6 = 0.9696969697
    // SGI  = 1200/1000 = 1.2
    // DEPI = [50/350]/[60/380] = 0.14285714/0.15789474 = 0.9047619048
    // SGAI = (264/1200)/(200/1000) = 0.22/0.2 = 1.1
    // LVGI = [(330+440)/2200]/[(300+400)/2000] = 0.35/0.35 = 1.0
    // TATA = (132−90)/2200 = 0.0190909091
    // M = −4.84 +0.92(1.25)+0.528(1.1428571429)+0.404(0.9696969697)
    //     +0.892(1.2)+0.115(0.9047619048)−0.172(1.1)
    //     +4.679(0.0190909091)−0.327(1.0)
    //   = −1.9472398701 < −1.78 → no flag
    const r = beneishM(base(), 1);
    expect(r.m).toBeCloseTo(-1.9472398701, 4);
    expect(r.flag).toBe(false);
    if (r.variables !== null) {
      const v = r.variables;
      expect(v.dsri).toBeCloseTo(1.25, 8);
      expect(v.gmi).toBeCloseTo(1.1428571429, 8);
      expect(v.aqi).toBeCloseTo(0.9696969697, 8);
      expect(v.sgi).toBeCloseTo(1.2, 8);
      expect(v.depi).toBeCloseTo(0.9047619048, 8);
      expect(v.sgai).toBeCloseTo(1.1, 8);
      expect(v.lvgi).toBeCloseTo(1.0, 8);
      expect(v.tata).toBeCloseTo(0.0190909091, 8);
    } else {
      expect.unreachable();
    }
    expect(r.missing).toEqual([]);
  });

  it("flags an aggressive profile above −1.78 (hand-computed)", () => {
    const s = blankSeries(2);
    s.revenue = [1000, 1500];
    s.receivables = [100, 225];
    s.grossProfit = [400, 450];
    s.currentAssets = [500, 600];
    s.ppeNet = [300, 300];
    s.totalAssets = [2000, 3000];
    s.depreciationAmortization = [50, 50];
    s.sgaExpense = [200, 270];
    s.currentLiabilities = [300, 555];
    s.totalDebt = [400, 600];
    s.netIncome = [120, 280];
    s.operatingCashFlow = [100, 100];
    // DSRI=1.5, GMI=0.4/0.3=1.3333333333, AQI=0.7/0.6=1.1666666667,
    // SGI=1.5, DEPI=(50/350)/(50/350)=1.0, SGAI=0.18/0.2=0.9,
    // LVGI=0.385/0.35=1.1, TATA=(280−100)/3000=0.06
    // M = −4.84+0.92(1.5)+0.528(1.3333)+0.404(1.1667)+0.892(1.5)
    //     +0.115(1.0)−0.172(0.9)+4.679(0.06)−0.327(1.1)
    //   = −1.0654266667 > −1.78 → flag
    const r = beneishM(s, 1);
    expect(r.m).toBeCloseTo(-1.0654266667, 4);
    expect(r.flag).toBe(true);
  });

  it("needs a prior period", () => {
    const r = beneishM(base(), 0);
    expect(r.m).toBeNull();
    expect(r.flag).toBeNull();
    expect(r.variables).toBeNull();
    expect(r.missing).toEqual(["priorPeriod"]);
  });

  it("names the variables it cannot build", () => {
    const s = base();
    s.receivables = [100, null]; // kills DSRI only
    const r = beneishM(s, 1);
    expect(r.m).toBeNull();
    expect(r.missing).toEqual(["DSRI"]);
  });
});

describe("workingCapitalDays", () => {
  function fixture(): StatementSeries {
    const s = blankSeries(1);
    s.receivables = [100];
    s.revenue = [1000];
    s.inventory = [200];
    s.grossProfit = [400]; // COGS = 1000 − 400 = 600
    s.accountsPayable = [150];
    return s;
  }

  it("computes DSO / DIO / DPO (hand-computed)", () => {
    // DSO = 100/1000×365 = 36.5
    // DIO = 200/600×365 = 121.6667
    // DPO = 150/600×365 = 91.25
    const r = workingCapitalDays(fixture(), 0);
    expect(r).not.toBeNull();
    expect(r!.dso).toBeCloseTo(36.5, 8);
    expect(r!.dio).toBeCloseTo(121.6666666667, 4);
    expect(r!.dpo).toBeCloseTo(91.25, 8);
  });

  it("nulls each field independently on missing inputs", () => {
    const s = fixture();
    s.inventory = [null];
    const r = workingCapitalDays(s, 0);
    expect(r!.dso).toBeCloseTo(36.5, 8);
    expect(r!.dio).toBeNull();
    expect(r!.dpo).toBeCloseTo(91.25, 8);
  });

  it("nulls DIO/DPO when COGS is zero but keeps DSO", () => {
    const s = fixture();
    s.grossProfit = [1000]; // COGS = 0
    const r = workingCapitalDays(s, 0);
    expect(r!.dso).toBeCloseTo(36.5, 8);
    expect(r!.dio).toBeNull();
    expect(r!.dpo).toBeNull();
  });

  it("returns null for an out-of-range index", () => {
    expect(workingCapitalDays(fixture(), 3)).toBeNull();
  });
});
