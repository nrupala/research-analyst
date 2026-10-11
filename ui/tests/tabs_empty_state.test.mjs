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

// Headless UI test for Research Analyst — report tabs + empty-state (Phase E)
//
// Runs the REAL ui/app.js offline (same vm + DOM-shim harness) and asserts:
//   - report-type labels are humanized (comprehensive -> Comprehensive)
//   - tabs hide when there are no reports
//   - the empty state renders when no report content exists
//
//   Run:  node ui/tests/tabs_empty_state.test.mjs

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

test("humanReportType maps known types to friendly labels", () => {
  const ctx = loadApp();
  assert.strictEqual(ctx.humanReportType("comprehensive"), "Comprehensive");
  assert.strictEqual(ctx.humanReportType("tactical"), "Tactical / Near-Term");
  assert.strictEqual(ctx.humanReportType("long_term"), "Long-Term");
  assert.strictEqual(ctx.humanReportType("etf"), "Etf");
  assert.strictEqual(ctx.humanReportType(null), null);
});

test("renderTabs labels tabs with humanized names", () => {
  const ctx = loadApp();
  ctx.document.getElementById("report-tabs").innerHTML = "";
  ctx.renderTabs([
    { report_type: "comprehensive" },
    { report_type: "long_term" },
  ]);
  const tabsEl = ctx.document.getElementById("report-tabs");
  const children = tabsEl.children || [];
  assert.ok(children.length >= 2, "tabs not appended");
  const texts = children.map((c) => c.textContent);
  assert.ok(texts.includes("Comprehensive"), `labels: ${texts}`);
  assert.ok(texts.includes("Long-Term"), `labels: ${texts}`);
});

test("renderTabs hides the tab bar when no reports", () => {
  const ctx = loadApp();
  const tabsEl = ctx.document.getElementById("report-tabs");
  tabsEl.style.display = "";
  ctx.renderTabs([]);
  assert.strictEqual(tabsEl.style.display, "none", "tab bar should hide when empty");
});

test("renderReport shows the empty state when no content", () => {
  const ctx = loadApp();
  ctx.currentReports = [];
  ctx.renderReport(0);
  const content = ctx.document.getElementById("report-content");
  assert.ok(content.innerHTML.includes("empty-state"), "empty-state markup missing");
  assert.ok(content.innerHTML.includes("No report to display"), "empty-state title missing");
});

test("renderReport renders markdown when content exists", () => {
  const ctx = loadApp();
  ctx.currentReports = ["# Hello Report"];
  // mdToHTML on "# Hello Report" -> h1
  ctx.renderReport(0);
  const content = ctx.document.getElementById("report-content");
  assert.ok(content.innerHTML.includes("<h1>Hello Report</h1>"), "report markdown not rendered");
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