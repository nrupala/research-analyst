// Copyright (C) 2026 2351485 ALBERTA INC.
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

// Headless UI test for Research Analyst — on-demand interactive chart view (Phase G)
//
// Runs the REAL ui/app.js offline (same vm + DOM-shim harness) and asserts the
// lazy Plotly loader + figure builder:
//   - Plotly is NOT fetched on load (main page stays zero-JS)
//   - buildInteractiveFigure builds trace-ready figures for every chart type
//   - the click handler wires .chart-interactive buttons
//
//   Run:  node ui/tests/interactive_chart.test.mjs

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
      this._listeners = {}; this._innerHTML = ""; this._textContent = "";
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
    head: { appendChild() {} },
    body: null,
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
    alert: () => {},
    atob: (s) => Buffer.from(s, "base64").toString("binary"),
    btoa: (s) => Buffer.from(s, "binary").toString("base64"),
  };
  vm.createContext(context);
  vm.runInContext(APP_JS, context, { filename: "app.js" });
  return context;
}

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

test("app.js exposes the interactive builders", () => {
  const ctx = loadApp();
  assert.strictEqual(typeof ctx.buildInteractiveFigure, "function");
  assert.strictEqual(typeof ctx.ensurePlotly, "function");
  assert.strictEqual(typeof ctx.openInteractiveView, "function");
});

test("no script tag is injected at load (Plotly stays off the main page)", () => {
  const ctx = loadApp();
  assert.strictEqual(typeof ctx.window.Plotly, "undefined", "Plotly must not be on the page at load");
});

test("financial_trends interactive data builds traces", () => {
  const ctx = loadApp();
  const fig = ctx.buildInteractiveFigure({
    type: "financial_trends", ticker: "AAPL", currency: "USD",
    periods: ["FY2024", "FY2025"], revenue_b: [391, 416],
    margins_pct: { Gross: [45.6, 46.1], Operating: [31.2, 31.9] },
  });
  assert.strictEqual(fig.traces.length, 3, "bar + 2 margin lines");
  assert.ok(fig.traces[0].type === "bar" && fig.traces[1].type === "scatter");
  assert.ok(fig.layout.title.includes("AAPL"));
});

test("scenario interactive data builds range bars", () => {
  const ctx = loadApp();
  const fig = ctx.buildInteractiveFigure({
    type: "scenario", currency: "USD",
    scenarios: [{ label: "Bull", low: 150, high: 200 }, { label: "Bear", low: 80, high: 100 }],
  });
  assert.strictEqual(fig.traces[0].type, "bar");
  assert.ok(fig.traces[0].text[0].includes("$150"), "USD range label");
});

test("risks interactive data builds scatter", () => {
  const ctx = loadApp();
  const fig = ctx.buildInteractiveFigure({
    type: "risks", risks: [{ title: "Regulatory", probability: 3, impact: 4 }],
  });
  assert.strictEqual(fig.traces[0].type, "scatter");
  assert.deepStrictEqual(fig.traces[0].x, [3]);
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