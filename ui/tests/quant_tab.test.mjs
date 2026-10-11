// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Headless UI test for Research Analyst — the Quant tab.
//
// Runs the REAL ui/app.js offline (same vm + DOM-shim harness as
// tabs_empty_state.test.mjs) and asserts:
//   - renderTabs appends a Quant tab with the ARIA tab pattern
//     (role="tab", aria-selected, aria-controls) — the generic arrow-key
//     navigation picks it up via the same [role="tab"] query
//   - no Quant tab when there are no reports (tab bar hidden)
//   - renderQuantData renders the phases as tables with formulas and
//     screen-not-verdict framing
//
//   Run:  node ui/tests/quant_tab.test.mjs

import assert from "node:assert";
import vm from "node:vm";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_JS = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");

function loadApp() {
  const registry = new Map();
  class El {
    constructor(tag) {
      this.tagName = (tag || "div").toUpperCase();
      this.children = []; this.parentNode = null; this._attrs = {}; this._id = "";
      this.style = {}; this.hidden = false; this.disabled = false; this.value = "";
      this._listeners = {}; this._innerHTML = ""; this._textContent = ""; this.classList = {
        _s: new Set(),
        add: function (c) { this._s.add(c); },
        remove: function (c) { this._s.delete(c); },
        contains: function (c) { return this._s.has(c); },
      };
    }
    get id() { return this._id; }
    set id(v) { if (this._id && registry.get(this._id) === this) registry.delete(this._id); this._id = v; if (v) registry.set(v, this); }
    get innerHTML() { return this._innerHTML; } set innerHTML(v) { this._innerHTML = String(v); }
    get textContent() { return this._textContent; } set textContent(v) { this._textContent = String(v); }
    setAttribute(k, v) { this._attrs[k] = String(v); if (k === "id") this.id = v; }
    getAttribute(k) { return this._attrs[k] || null; }
    appendChild(n) { n.parentNode = this; this.children.push(n); return n; }
    removeChild(n) { const i = this.children.indexOf(n); if (i >= 0) this.children.splice(i, 1); n.parentNode = null; return n; }
    remove() { if (this.parentNode) this.parentNode.removeChild(this); }
    addEventListener(t, fn) { (this._listeners[t] || (this._listeners[t] = [])).push(fn); }
    removeEventListener() {}
    showModal() {} close() {} focus() {} querySelectorAll() { return []; }
  }
  const document = {
    createElement(tag) { return new El(tag); },
    getElementById(id) { let el = registry.get(id); if (!el) { el = new El("div"); el.id = id; } return el; },
    querySelectorAll() { return []; },
    addEventListener() {},
  };
  document.body = document.createElement("body");
  const context = {
    document,
    window: { location: { href: "" }, localStorage: { getItem: () => null, setItem: () => {} }, matchMedia: () => ({ matches: false }), addEventListener: () => {} },
    fetch: async () => { throw new Error("fetch not used in this test"); },
    setTimeout: (fn) => setTimeout(fn, 0), clearTimeout: (h) => clearTimeout(h),
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    console, JSON, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Promise,
    encodeURIComponent,
    atob: (s) => Buffer.from(s, "base64").toString("binary"),
    btoa: (s) => Buffer.from(s, "binary").toString("base64"),
  };
  vm.createContext(context);
  vm.runInContext(APP_JS, context, { filename: "app.js" });
  return context;
}

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

const QUANT_FIXTURE = {
  ticker: "TST",
  periods: ["FY2023", "FY2024"],
  currency: "USD",
  trends: { revenue_cagr: 0.1, eps_cagr: 0.12, fcf_cagr: null, yoy_revenue_growth_latest: 0.1, gross_margin_latest: 0.4, net_margin_latest: 0.1 },
  dupont: {
    rows: [{ period: "FY2024", roe: 0.08, net_margin: 0.1, asset_turnover: 0.5, leverage: 1.6 }],
    latest: { period: "FY2024", roe: 0.08, net_margin: 0.1, asset_turnover: 0.5, leverage: 1.6 },
    attribution: { roe_change_pp: 1.0, margin_contribution_pp: 0.5, turnover_contribution_pp: 0.3, leverage_contribution_pp: 0.2 },
  },
  forensics: { altman_z: 3.1, altman_zone: "safe", altman_missing: [], beneish_m: -2.1, beneish_flag: false, beneish_missing: [], sloan_accruals: 0.02, cash_conversion: 1.5 },
  valuation: { graham_number: 45.0, lynch_fair_value: 60.0, implied_explicit_stage_growth: 0.07, implied_perpetual_growth: 0.03, discount_rate_used: 0.09 },
  allocation: { incremental_roic_average: null, operating_tax_rate_latest: null, dividend_payout_on_earnings: 0.3, dividend_payout_on_fcf: 0.4, dividend_years_grown: 2, dividend_cuts: 0, debt_net_debt_latest: 100.0, debt_net_debt_to_ebit: 0.5, debt_interest_coverage: null, debt_cagr: 0.05, buyback_shares_cagr: -0.01, buyback_total_spent: 50.0 },
  expected_value: { expected: null, contributions: null, reason: "no scenarios provided" },
  missing_inputs: ["interest_expense (not fetched by any provider)"],
  assumptions: ["Discount rate r = 9.00% (analyst assumption, not observed market data) used for the implied-growth inversions."],
};

test("renderTabs appends a Quant tab with the ARIA tab pattern", () => {
  const ctx = loadApp();
  ctx.document.getElementById("report-tabs").innerHTML = "";
  ctx.renderTabs([{ report_type: "comprehensive" }]);
  const children = ctx.document.getElementById("report-tabs").children || [];
  const texts = children.map((c) => c.textContent);
  assert.ok(texts.includes("Quant"), `tabs: ${texts}`);
  const q = children.find((c) => c.textContent === "Quant");
  assert.strictEqual(q.getAttribute("role"), "tab");
  assert.strictEqual(q.getAttribute("aria-selected"), "false");
  assert.strictEqual(q.getAttribute("aria-controls"), "report-content");
});

test("renderTabs([]) hides the bar and adds no Quant tab", () => {
  const ctx = loadApp();
  const tabsEl = ctx.document.getElementById("report-tabs");
  tabsEl.style.display = "";
  ctx.renderTabs([]);
  const children = tabsEl.children || [];
  assert.ok(!children.some((c) => c.textContent === "Quant"), "no Quant tab when empty");
  assert.strictEqual(tabsEl.style.display, "none");
});

test("renderQuantData renders phase tables with formulas and screen framing", () => {
  const ctx = loadApp();
  ctx.renderQuantData(QUANT_FIXTURE);
  const html = ctx.document.getElementById("report-content").innerHTML;
  assert.ok(html.includes("Implied explicit-stage growth"), "explicit-stage row missing");
  assert.ok(html.includes("Implied perpetual growth"), "perpetual row missing");
  assert.ok(html.includes("screens, not verdicts"), "screen framing missing");
  assert.ok(html.includes("<table>"), "phase tables missing");
  assert.ok(html.includes("Graham number"), "Graham row missing");
  assert.ok(html.includes("Missing inputs"), "missing-inputs section missing");
  // (the shim's esc() swallows dynamic text, so assert the static prefix only)
  assert.ok(html.includes("Expected value:"), "expected-value reason missing");
});

(async () => {
  let pass = 0, fail = 0;
  for (const t of tests) {
    try { await t.fn(); console.log("  \u2713 " + t.name); pass++; }
    catch (e) { console.error("  \u2717 " + t.name + "\n      " + (e && e.message ? e.message : e)); fail++; }
  }
  console.log(`\n${pass}/${tests.length} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();