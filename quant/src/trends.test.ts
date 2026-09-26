// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import {
  cagr,
  flattery,
  logLinearTrend,
  marginSeries,
  perShareSeries,
  seriesCagr,
  yoyGrowth,
} from "./trends.js";

describe("cagr", () => {
  it("100→110→121 over 2 periods = 10%", () => {
    // (121/100)^(1/2) − 1 = 1.1 − 1
    expect(cagr(100, 121, 2)).toBeCloseTo(0.1, 12);
  });

  it("handles decline and flat endpoints", () => {
    // (81/100)^(1/2) − 1 = 0.9 − 1
    expect(cagr(100, 81, 2)).toBeCloseTo(-0.1, 12);
    expect(cagr(100, 100, 5)).toBeCloseTo(0, 12);
    // doubling twice in 2 periods = 100% per period
    expect(cagr(100, 400, 2)).toBeCloseTo(1, 12);
  });

  it("returns null on missing/non-positive bases and bad horizons", () => {
    expect(cagr(null, 121, 2)).toBeNull();
    expect(cagr(100, null, 2)).toBeNull();
    expect(cagr(0, 121, 2)).toBeNull();
    expect(cagr(-5, 121, 2)).toBeNull();
    expect(cagr(100, 121, 0)).toBeNull();
    expect(cagr(100, 121, -3)).toBeNull();
    expect(cagr(NaN, 121, 2)).toBeNull();
  });

  it("returns null when the ratio goes negative (fractional power undefined)", () => {
    expect(cagr(100, -50, 2)).toBeNull();
  });
});

describe("seriesCagr", () => {
  it("uses first and last non-null values with index distance as periods", () => {
    expect(seriesCagr([100, 110, 121])).toBeCloseTo(0.1, 12);
    // gaps in the middle do not shorten the horizon: idx 1→3 = 2 periods
    expect(seriesCagr([null, 100, null, 121])).toBeCloseTo(0.1, 12);
  });

  it("returns null with fewer than 2 non-null points", () => {
    expect(seriesCagr([])).toBeNull();
    expect(seriesCagr([null, null])).toBeNull();
    expect(seriesCagr([100])).toBeNull();
    expect(seriesCagr([null, 100, null])).toBeNull();
  });

  it("is consistent with the endpoint ratio (invariant)", () => {
    // first non-null 80 at idx 1, last non-null 125 at idx 4 → 3 periods
    const c = seriesCagr([null, 80, 100, null, 125]);
    expect(c).not.toBeNull();
    expect((1 + (c ?? 0)) ** 3).toBeCloseTo(125 / 80, 10);
  });
});

describe("yoyGrowth", () => {
  it("computes (v[i]/v[i-1])−1 with a null first element", () => {
    // exact equality is not used: 110/100 − 1 is 0.10000000000000009 in float
    const g = yoyGrowth([100, 110, 121]);
    expect(g[0] ?? null).toBeNull();
    expect(g[1] ?? 0).toBeCloseTo(0.1, 12);
    expect(g[2] ?? 0).toBeCloseTo(0.1, 12);
    expect(g).toHaveLength(3);
  });

  it("constant series gives zeros", () => {
    expect(yoyGrowth([5, 5, 5, 5])).toEqual([null, 0, 0, 0]);
  });

  it("propagates nulls from either endpoint", () => {
    expect(yoyGrowth([100, null, 121])).toEqual([null, null, null]);
    const g = yoyGrowth([null, 100, 110]);
    expect(g[0] ?? null).toBeNull();
    expect(g[1] ?? null).toBeNull();
    expect(g[2] ?? 0).toBeCloseTo(0.1, 12);
  });

  it("is null on a non-positive base", () => {
    expect(yoyGrowth([0, 100])).toEqual([null, null]);
    expect(yoyGrowth([-100, -90])).toEqual([null, null]);
  });

  it("keeps input length, including empty input", () => {
    expect(yoyGrowth([])).toEqual([]);
    expect(yoyGrowth([42])).toEqual([null]);
  });

  it("compounding the growth rates reconstructs the series (invariant)", () => {
    const s = [100, 110, 121, 108.9];
    const g = yoyGrowth(s);
    expect(g[0] ?? null).toBeNull();
    let acc: number = s[0] ?? 0;
    for (let i = 1; i < s.length; i++) {
      const gi: number | null | undefined = g[i];
      expect(gi).not.toBeNull();
      expect(gi).not.toBeUndefined();
      acc *= 1 + (gi ?? 0);
    }
    expect(acc).toBeCloseTo(s[3] ?? 0, 9);
  });
});

describe("logLinearTrend", () => {
  it("flat series: slope ≈ 0, rSquared = 1, direction flat", () => {
    const t = logLinearTrend([100, 100, 100, 100]);
    expect(t).not.toBeNull();
    expect(t?.slope).toBeCloseTo(0, 12);
    expect(t?.rSquared).toBe(1);
    expect(t?.direction).toBe("flat");
  });

  it("10%/period exponential: slope ≈ ln(1.1), rSquared ≈ 1, direction up", () => {
    const t = logLinearTrend([100, 110, 121, 133.1]);
    expect(t).not.toBeNull();
    expect(t?.slope).toBeCloseTo(Math.log(1.1), 8);
    expect(t?.rSquared).toBeCloseTo(1, 8);
    expect(t?.direction).toBe("up");
  });

  it("declining series gives negative slope and direction down", () => {
    const t = logLinearTrend([133.1, 121, 110, 100]);
    expect(t).not.toBeNull();
    expect(t?.slope).toBeCloseTo(-Math.log(1.1), 8);
    expect(t?.direction).toBe("down");
  });

  it("treats |slope| < 0.005 as flat", () => {
    // 0.4%/period → slope ≈ ln(1.004) ≈ 0.00399 < 0.005
    const slow = logLinearTrend(
      Array.from({ length: 6 }, (_, i) => 100 * 1.004 ** i),
    );
    expect(slow?.direction).toBe("flat");
    // 0.6%/period → slope ≈ ln(1.006) ≈ 0.00598 > 0.005
    const faster = logLinearTrend(
      Array.from({ length: 6 }, (_, i) => 100 * 1.006 ** i),
    );
    expect(faster?.direction).toBe("up");
  });

  it("ignores nulls and non-positive values but keeps their time index", () => {
    // usable points at t = 1..4 only; shifting t changes only the intercept
    const t = logLinearTrend([null, 100, 110, 121, 133.1, -50, 0]);
    expect(t).not.toBeNull();
    expect(t?.slope).toBeCloseTo(Math.log(1.1), 8);
    expect(t?.direction).toBe("up");
  });

  it("returns null with fewer than 3 usable points", () => {
    expect(logLinearTrend([100, 110])).toBeNull();
    expect(logLinearTrend([null, 100, null])).toBeNull();
    expect(logLinearTrend([])).toBeNull();
  });
});

describe("perShareSeries", () => {
  it("divides element-wise and nulls on missing or non-positive shares", () => {
    expect(perShareSeries([100, 200, null], [10, 0, 20])).toEqual([10, null, null]);
    expect(perShareSeries([100], [-5])).toEqual([null]);
  });

  it("pads to the longer input", () => {
    expect(perShareSeries([100, 200], [10])).toEqual([10, null]);
  });
});

describe("marginSeries", () => {
  it("divides element-wise as fractions", () => {
    expect(marginSeries([30, 40, null], [100, 200, 50])).toEqual([0.3, 0.2, null]);
  });

  it("is null on non-positive revenue", () => {
    expect(marginSeries([30], [0])).toEqual([null]);
    expect(marginSeries([30], [-100])).toEqual([null]);
  });
});

describe("flattery", () => {
  it("flags buyback flattery when per-share growth outruns total growth", () => {
    const r = flattery(0.08, 0.1);
    expect(r).not.toBeNull();
    expect(r?.gapPts).toBeCloseTo(2, 10);
    expect(r?.interpretation).toBe(
      "per-share growth exceeds total growth — buybacks are flattering the per-share number",
    );
  });

  it("flags dilution when per-share growth lags", () => {
    const r = flattery(0.1, 0.04);
    expect(r?.gapPts).toBeCloseTo(-6, 10);
    expect(r?.interpretation).toBe(
      "per-share growth lags — dilution or share issuance",
    );
  });

  it("calls small gaps aligned", () => {
    const r = flattery(0.05, 0.055);
    expect(r?.gapPts).toBeCloseTo(0.5, 10);
    expect(r?.interpretation).toBe("per-share and total growth are aligned");
  });

  it("returns null on missing input", () => {
    expect(flattery(null, 0.1)).toBeNull();
    expect(flattery(0.1, null)).toBeNull();
    expect(flattery(NaN, 0.1)).toBeNull();
  });
});
