// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, expect, it } from "vitest";
import { defined, div, divSeries, firstValue, lastValue, mean } from "./guards.js";
import { assertValidSeries, type StatementSeries } from "./types.js";

function series(n: number): StatementSeries {
  const blank = (): (number | null)[] => new Array(n).fill(null);
  return {
    ticker: "TEST",
    currency: "USD",
    periods: Array.from({ length: n }, (_, i) => ({
      period: `FY${2020 + i}`,
      periodEndDate: `${2020 + i}-12-31`,
    })),
    revenue: blank(),
    grossProfit: blank(),
    operatingIncome: blank(),
    ebit: blank(),
    netIncome: blank(),
    epsDiluted: blank(),
    operatingCashFlow: blank(),
    capitalExpenditure: blank(),
    freeCashFlow: blank(),
    dividendsPaid: blank(),
    shareBuybacks: blank(),
    totalAssets: blank(),
    totalEquity: blank(),
    totalLiabilities: blank(),
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

describe("guards", () => {
  it("defined strips nulls and non-finite values", () => {
    expect(defined([1, null, 2, NaN, Infinity, 3])).toEqual([1, 2, 3]);
  });

  it("lastValue / firstValue skip nulls", () => {
    expect(lastValue([null, 5, null])).toBe(5);
    expect(firstValue([null, 5, null])).toBe(5);
    expect(lastValue([null, null])).toBeNull();
  });

  it("div guards against null and zero divisor", () => {
    expect(div(4, 2)).toBe(2);
    expect(div(4, 0)).toBeNull();
    expect(div(null, 2)).toBeNull();
  });

  it("divSeries is element-wise and null-safe", () => {
    expect(divSeries([4, 6, null], [2, 0, 3])).toEqual([2, null, null]);
  });

  it("mean ignores nulls", () => {
    expect(mean([2, null, 4])).toBe(3);
    expect(mean([null])).toBeNull();
  });
});

describe("types", () => {
  it("assertValidSeries accepts aligned series", () => {
    expect(() => assertValidSeries(series(3))).not.toThrow();
  });

  it("assertValidSeries throws on misaligned series", () => {
    const s = series(3);
    s.revenue = [1, 2]; // wrong length
    expect(() => assertValidSeries(s)).toThrow(/revenue/);
  });
});
