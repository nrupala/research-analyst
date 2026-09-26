// Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program. If not, see <https://www.gnu.org/licenses/>.
//
// A separate commercial license is available for uses incompatible with
// the AGPL-3.0. See COMMERCIAL-LICENSE.md.

// Headless UI test for Research Analyst — export toolbar + paid source-data download (8c-2)
//
// Runs the REAL ui/app.js offline (same vm + DOM-shim harness) and asserts:
//   - the export toolbar includes the "Download data (CSV/JSON)" button after a report
//   - downloadSourceData exists and posts to /api/research/data with X-RA-Key on 401 retry
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

test("app.js exposes downloadSourceData", () => {
  const { ctx } = loadApp();
  assert.strictEqual(typeof ctx.downloadSourceData, "function");
});

test("export toolbar includes the data-download button after a report", () => {
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
  assert.ok(texts.includes("Download data (CSV/JSON)"), "paid data button missing: " + texts);
});

test("downloadSourceData posts to /api/research/data", async () => {
  const { ctx, calls } = loadApp();
  ctx.currentReports = ["# report"];
  ctx.activeTicker = "AAPL";
  ctx.dom.ticker.value = "AAPL";
  await ctx.downloadSourceData();
  assert.ok(calls.length >= 1, "no fetch call made");
  const c = calls[0];
  assert.ok(c.url.includes("/api/research/data"), c.url);
  assert.ok(!c.init.headers["X-RA-Key"], "no key sent on first attempt when open");
});

test("downloadSourceData retries with X-RA-Key on 401", async () => {
  const { ctx, calls } = loadApp({ fetch401: true, prompt: () => "paidkey-1" });
  ctx.currentReports = ["# report"];
  ctx.activeTicker = "AAPL";
  ctx.dom.ticker.value = "AAPL";
  await ctx.downloadSourceData();
  assert.ok(calls.length >= 2, "expected a retry after 401");
  const retry = calls[1];
  assert.strictEqual(retry.init.headers["X-RA-Key"], "paidkey-1");
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