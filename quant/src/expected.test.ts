// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import {
  expectedValue,
  marginOfSafety,
  solveForInput,
  tornado,
} from "./expected.js";

describe("expectedValue", () => {
  it("weights values by probability and reports contributions", () => {
    const out = expectedValue([
      { label: "bull", value: 120, probability: 0.3 },
      { label: "base", value: 100, probability: 0.5 },
      { label: "bear", value: 70, probability: 0.2 },
    ]);
    if ("error" in out) throw new Error(`unexpected error: ${out.error}`);
    // 120×0.3 + 100×0.5 + 70×0.2 = 36 + 50 + 14 = 100
    expect(out.expected).toBeCloseTo(100, 12);
    const byLabel = Object.fromEntries(
      out.contributions.map((c) => [c.label, c.contribution]),
    );
    expect(byLabel["bull"]).toBeCloseTo(36, 12);
    expect(byLabel["base"]).toBeCloseTo(50, 12);
    expect(byLabel["bear"]).toBeCloseTo(14, 12);
  });

  it("returns the first violation as an error", () => {
    expect(expectedValue([])).toEqual({
      error: expect.stringContaining("at least one"),
    });

    const missingValue = expectedValue([
      { label: "bull", value: null, probability: 1 },
    ]);
    expect(missingValue).toEqual({
      error: expect.stringContaining('scenario "bull"'),
    });

    const missingProbability = expectedValue([
      { label: "base", value: 100, probability: null },
    ]);
    expect(missingProbability).toEqual({
      error: expect.stringContaining("missing probability"),
    });

    const negativeProbability = expectedValue([
      { label: "bear", value: 70, probability: -0.1 },
    ]);
    expect(negativeProbability).toEqual({
      error: expect.stringContaining("negative probability"),
    });

    // 0.5 + 0.6 = 1.1 — outside the 1 ± 0.01 band.
    const badSum = expectedValue([
      { label: "a", value: 100, probability: 0.5 },
      { label: "b", value: 100, probability: 0.6 },
    ]);
    expect(badSum).toEqual({
      error: expect.stringContaining("probabilities sum to"),
    });
  });
});

describe("tornado", () => {
  it("ranks inputs by output swing, most sensitive first", () => {
    const base = { growth: 0.05, margin: 0.2, tax: 0.25 };
    // output = 100 × (1+g) × margin × (1−tax); base output = 15.75
    const model = (i: typeof base): number | null =>
      100 * (1 + i.growth) * i.margin * (1 - i.tax);
    const rows = tornado(base, model, [
      { name: "growth", low: 0, high: 0.1 }, // 15 → 16.5, swing 1.5
      { name: "margin", low: 0.1, high: 0.3 }, // 7.875 → 23.625, swing 15.75
      { name: "tax", low: 0.2, high: 0.3 }, // 16.8 → 14.7, swing 2.1
    ]);
    expect(rows.map((r) => r.name)).toEqual(["margin", "tax", "growth"]);
    expect(rows[0]?.swing).toBeCloseTo(15.75, 8);
    expect(rows[1]?.swing).toBeCloseTo(2.1, 8);
    expect(rows[2]?.swing).toBeCloseTo(1.5, 8);
  });

  it("gives swing 0 when the model returns null at an end", () => {
    const rows = tornado(
      { x: 1 },
      (i) => (i.x === 0 ? null : 1 / i.x),
      [{ name: "x", low: 0, high: 2 }],
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.lowOutput).toBeNull();
    expect(rows[0]?.highOutput).toBeCloseTo(0.5, 12);
    expect(rows[0]?.swing).toBe(0);
  });
});

describe("marginOfSafety", () => {
  it("is positive below intrinsic value, negative above", () => {
    // (100 − 80)/100 = 0.2 ; (100 − 120)/100 = −0.2
    expect(marginOfSafety(100, 80)).toBeCloseTo(0.2, 12);
    expect(marginOfSafety(100, 120)).toBeCloseTo(-0.2, 12);
    expect(marginOfSafety(100, 100)).toBe(0);
  });

  it("returns null without a positive intrinsic value or a price", () => {
    expect(marginOfSafety(null, 80)).toBeNull();
    expect(marginOfSafety(0, 80)).toBeNull();
    expect(marginOfSafety(-10, 80)).toBeNull();
    expect(marginOfSafety(100, null)).toBeNull();
  });
});

describe("solveForInput", () => {
  it("bisects to the input that hits the target", () => {
    // 2x + 1 = 7 → x = 3
    const found = solveForInput((x) => 2 * x + 1, 7, 0, 10);
    expect(found).not.toBeNull();
    expect(found!.converged).toBe(true);
    expect(found!.input).toBeCloseTo(3, 9);
  });

  it("handles decreasing models", () => {
    // 10 − x = 7 → x = 3
    const found = solveForInput((x) => 10 - x, 7, 0, 10);
    expect(found).not.toBeNull();
    expect(found!.converged).toBe(true);
    expect(found!.input).toBeCloseTo(3, 9);
  });

  it("returns null when the target is not bracketed or the model is null", () => {
    // model(0)=1, model(10)=21: target 100 is outside.
    expect(solveForInput((x) => 2 * x + 1, 100, 0, 10)).toBeNull();
    expect(solveForInput((x) => (x < 0 ? null : x), 0.5, -1, 1)).toBeNull();
  });
});
