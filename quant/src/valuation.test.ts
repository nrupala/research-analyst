// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import {
  capmCostOfEquity,
  dcf,
  multiplePercentile,
  reverseDcf,
  sensitivityGrid,
  wacc,
} from "./valuation.js";

describe("capmCostOfEquity", () => {
  it("computes rf + β × ERP", () => {
    // 0.04 + 1.25 × 0.05 = 0.1025
    expect(capmCostOfEquity(0.04, 1.25, 0.05)).toBeCloseTo(0.1025, 12);
  });

  it("returns null when any input is missing", () => {
    expect(capmCostOfEquity(null, 1.25, 0.05)).toBeNull();
    expect(capmCostOfEquity(0.04, null, 0.05)).toBeNull();
    expect(capmCostOfEquity(0.04, 1.25, null)).toBeNull();
  });
});

describe("wacc", () => {
  it("weights equity and after-tax debt by market value", () => {
    // V = 800 + 200 = 1000
    // 0.10 × 0.8 + 0.05 × (1 − 0.25) × 0.2 = 0.08 + 0.0075 = 0.0875
    expect(wacc(0.1, 0.05, 0.25, 800, 200)).toBeCloseTo(0.0875, 12);
  });

  it("returns null with no capital base or missing inputs", () => {
    expect(wacc(0.1, 0.05, 0.25, 0, 0)).toBeNull();
    expect(wacc(null, 0.05, 0.25, 800, 200)).toBeNull();
    expect(wacc(0.1, 0.05, null, 800, 200)).toBeNull();
  });
});

describe("dcf", () => {
  it("discounts explicit cash flows and a Gordon terminal value", () => {
    // Hand computation for fcf0=100, g=[0.1, 0.1], r=0.10, tg=0.03:
    //   FCF1 = 100 × 1.1            = 110
    //   FCF2 = 110 × 1.1            = 121
    //   PV(explicit) = 110/1.1 + 121/1.21 = 100 + 100 = 200
    //   TV  = 121 × 1.03 / (0.10 − 0.03) = 124.63 / 0.07 = 1780.428571…
    //   PV(TV) = 1780.428571… / 1.21 = 1471.428571…
    //   EV = 200 + 1471.428571… = 1671.428571…
    const result = dcf(100, [0.1, 0.1], 0.1, 0.03);
    expect(result).not.toBeNull();
    expect(result?.pvExplicit).toBeCloseTo(200, 8);
    expect(result?.pvTerminal).toBeCloseTo(1471.4285714285716, 8);
    expect(result?.enterpriseValue).toBeCloseTo(1671.4285714285716, 8);
    expect(result?.cashFlows).toHaveLength(2);
    expect(result?.cashFlows[0]).toBeCloseTo(110, 8);
    expect(result?.cashFlows[1]).toBeCloseTo(121, 8);
  });

  it("returns null on missing inputs, empty growth, or r ≤ g", () => {
    expect(dcf(null, [0.1], 0.1, 0.03)).toBeNull();
    expect(dcf(100, [], 0.1, 0.03)).toBeNull();
    expect(dcf(100, [0.1], null, 0.03)).toBeNull();
    expect(dcf(100, [0.1], 0.1, null)).toBeNull();
    expect(dcf(100, [0.1], 0.03, 0.03)).toBeNull(); // r == tg: Gordon diverges
    expect(dcf(100, [0.1], 0.02, 0.03)).toBeNull(); // r < tg
  });
});

describe("reverseDcf", () => {
  it("round-trips: implied growth fed back into dcf reproduces the EV", () => {
    const target = dcf(100, [0.05, 0.05], 0.1, 0.03);
    expect(target).not.toBeNull();
    const found = reverseDcf(target!.enterpriseValue, 100, 0.1, 0.03, 2);
    expect(found).not.toBeNull();
    expect(found!.converged).toBe(true);
    expect(found!.impliedGrowth).toBeCloseTo(0.05, 6);
  });

  it("reports converged=false at the bound when the EV is out of range", () => {
    // dcf(100, [−0.5, −0.5], 0.1, 0.03) ≈ 370, so EV=1 implies g < −0.5:
    // no root exists inside [−0.5, 1.0].
    const found = reverseDcf(1, 100, 0.1, 0.03, 2);
    expect(found).not.toBeNull();
    expect(found!.converged).toBe(false);
    expect(found!.impliedGrowth).toBeCloseTo(-0.5, 12);
  });

  it("returns null on invalid inputs", () => {
    expect(reverseDcf(0, 100, 0.1, 0.03, 2)).toBeNull(); // EV ≤ 0
    expect(reverseDcf(-5, 100, 0.1, 0.03, 2)).toBeNull();
    expect(reverseDcf(null, 100, 0.1, 0.03, 2)).toBeNull();
    expect(reverseDcf(1000, 100, 0.05, 0.05, 2)).toBeNull(); // r ≤ tg
    expect(reverseDcf(1000, null, 0.1, 0.03, 2)).toBeNull();
    expect(reverseDcf(1000, 100, 0.1, 0.03, 0)).toBeNull(); // years < 1
  });
});

describe("multiplePercentile", () => {
  it("ranks current against non-null history", () => {
    // Non-null history: [10, 20, 30, 40]; ≤ 25 are {10, 20} → 2/4 = 50.
    expect(multiplePercentile(25, [10, 20, 30, 40, null])).toBe(50);
    expect(multiplePercentile(40, [10, 20, 30, 40])).toBe(100);
    expect(multiplePercentile(5, [10, 20, 30, 40])).toBe(0);
  });

  it("returns null with no observable history or missing current", () => {
    expect(multiplePercentile(null, [10, 20])).toBeNull();
    expect(multiplePercentile(25, [null, null])).toBeNull();
    expect(multiplePercentile(25, [])).toBeNull();
  });
});

describe("sensitivityGrid", () => {
  it("builds a rows × cols grid over the two varied inputs", () => {
    const grid = sensitivityGrid(
      { a: 1, b: 2 },
      { name: "a", values: [1, 2] },
      { name: "b", values: [10, 20] },
      (i) => i.a + i.b,
    );
    expect(grid.rowLabels).toEqual([1, 2]);
    expect(grid.colLabels).toEqual([10, 20]);
    expect(grid.values).toEqual([
      [11, 21],
      [12, 22],
    ]);
  });

  it("propagates null cells where the model is undefined", () => {
    const grid = sensitivityGrid(
      { a: 1, b: 2 },
      { name: "a", values: [-1, 2] },
      { name: "b", values: [10] },
      (i) => (i.a < 0 ? null : i.a + i.b),
    );
    expect(grid.values).toEqual([[null], [12]]);
  });
});
