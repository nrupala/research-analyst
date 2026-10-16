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

// Headless UI test for Research Analyst — paid source-data download RETIRED
// (owner ruling, 2026-10-15: source data is never sold or redistributed).
//
// Runs the REAL ui/app.js offline (same vm + DOM-shim harness) and asserts:
//   - downloadSourceData no longer exists
//   - the export toolbar offers only MD/HTML/PDF (no "Download data" button)
//   - app.js carries no reference to the retired /api/research/data endpoint
//
//   Run:  node ui/tests/download_data.test.mjs

import assert from "node:assert";
import vm from "node:vm";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_JS = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");

function loadApp(opts = {}) {
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
    insertBefore(n, ref) { n.parentNode = this; const i = this.children.indexOf(ref); if (i < 0) this.children.push(n); else this.children.splice(i, 0, n); return n; }
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
    body: new El("body"),
    head: { appendChild() {} },
  };
  const calls = [];
  const context = {
    document,
    window: { location: { href: "" }, localStorage: { getItem: () => null, setItem: () => {} }, matchMedia: () => ({ matches: false }), addEventListener: () => {} },
    fetch: async (url, init) => {
      calls.push({ url, init });
      if (opts.fetch401) return { status: 401, ok: false, json: async () => ({ detail: "paid" }) };
      return { status: 200, ok: true, json: async () => ({ ticker: "AAPL", scenarios: [] }) };
    },
    setTimeout: (fn) => setTimeout(fn, 0), clearTimeout: (h) => clearTimeout(h),
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    console, JSON, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Promise,
    encodeURIComponent, prompt: opts.prompt || (() => null),
    alert: opts.alert || (() => {}),
    atob: (s) => Buffer.from(s, "base64").toString("binary"),
    btoa: (s) => Buffer.from(s, "binary").toString("base64"),
  };
  vm.createContext(context);
  vm.runInContext(APP_JS, context, { filename: "app.js" });
  return { ctx: context, calls };
}

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

test("app.js no longer exposes downloadSourceData", () => {
  const { ctx } = loadApp();
  assert.strictEqual(typeof ctx.downloadSourceData, "undefined");
});

test("export toolbar has no data-download button after a report", () => {
  const { ctx } = loadApp();
  ctx.currentReports = ["# report"];
  ctx.activeTicker = "AAPL";
  // stub reportContent so insertBefore works (shim elements are ephemeral)
  const barHost = ctx.document.createElement("div");
  const parentHost = ctx.document.createElement("div");
  barHost.parentNode = parentHost;
  ctx.dom.reportContent = barHost;
  ctx.addExportToolbar();
  const bar = ctx.document.getElementById("export-toolbar");
  const texts = bar.children.map((c) => c.textContent);
  assert.ok(texts.includes("Download MD"));
  assert.ok(!texts.some((t) => t.includes("Download data")), "retired data button still present: " + texts);
  assert.deepStrictEqual(texts, ["Download MD", "Download HTML", "Download PDF"]);
});

test("app.js carries no reference to the retired endpoint", () => {
  assert.ok(!APP_JS.includes("/api/research/data"), "retired endpoint still referenced in app.js");
  assert.ok(!APP_JS.includes("downloadSourceData"), "retired function still referenced in app.js");
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