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

// Headless UI test for Research Analyst — markdown link rendering in mdToHTML
//
// Runs the REAL ui/app.js offline (same vm + DOM-shim harness as
// chart_html_preservation.test.mjs) and asserts that `[text](url)` markdown is
// converted to clickable <a> links with target=_blank + rel=noopener.
//
//   Run:  node ui/tests/markdown_links.test.mjs
//
// Why this exists: thinkwithfinance cross-references render as raw
// `[Learn more](https://thinkwithfinance.com/...)` text — the converter was
// missing entirely. This locks in the fix (Phase B of the presentation batch).

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
  };
  document.body = document.createElement("body");
  const context = {
    document,
    window: { location: { href: "" }, localStorage: { getItem: () => null, setItem: () => {} }, matchMedia: () => ({ matches: false }) },
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
  // app.js's esc() uses a DOM node (textContent -> innerHTML) which the shim
  // can't mirror; shadow the global with a faithful HTML-escape equivalent.
  context.esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return context;
}

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

test("app.js exposes a callable mdToHTML", () => {
  const ctx = loadApp();
  assert.strictEqual(typeof ctx.mdToHTML, "function");
});

test("markdown links convert to <a> with target+rel", () => {
  const md = "See [Learn more — Reading financial statements](https://thinkwithfinance.com/p/reading-financial-statements-like-an-analyst) for details.";
  const html = loadApp().mdToHTML(md);
  assert.ok(
    html.includes('<a href="https://thinkwithfinance.com/p/reading-financial-statements-like-an-analyst" target="_blank" rel="noopener noreferrer">Learn more — Reading financial statements</a>'),
    "link was not converted to a clickable anchor: " + html
  );
});

test("raw [text](url) never leaks as literal markdown", () => {
  const md = "Section link:\n\n*Learn more — [Valuation](https://thinkwithfinance.com/p/valuation-101)*";
  const html = loadApp().mdToHTML(md);
  assert.ok(!html.includes("[Valuation]"), "raw markdown link syntax leaked into the HTML");
  assert.ok(html.includes(">Valuation<"), "link text missing from rendered anchor");
});

test("multiple links all convert", () => {
  const md = "A: [One](https://a.example/1) and B: [Two](https://b.example/2).";
  const html = loadApp().mdToHTML(md);
  const anchors = (html.match(/<a href="https:\/\/(a|b)\.example\//g) || []).length;
  assert.strictEqual(anchors, 2, `expected 2 anchors, found ${anchors}: ${html}`);
});

test("links with URL query strings survive", () => {
  const md = "[Doc](https://docs.example.com/path?utm_source=ra&utm_medium=report)";
  const html = loadApp().mdToHTML(md);
  assert.ok(html.includes('href="https://docs.example.com/path?utm_source=ra&amp;utm_medium=report"'), html);
});

test("crossref-style line with italic wrapper still links", () => {
  const md = "*Learn more — [Risk and position sizing](https://thinkwithfinance.com/p/risk-and-position-sizing) (thinkwithfinance)*";
  const html = loadApp().mdToHTML(md);
  assert.ok(html.includes(">Risk and position sizing<"), "crossref-style link text missing");
  assert.ok(!html.includes("[Risk and position sizing]"), "crossref-style raw markdown leaked");
});

test("chart blocks unaffected by the link pass", () => {
  const ctx = loadApp();
  const chart = `<div class="chart-svg"><svg xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto" viewBox="0 0 10 10"></svg></div>`;
  const html = ctx.mdToHTML("Intro with [link](https://x.example).\n\n" + chart + "\n\nTail.");
  assert.ok(html.includes(chart), "chart block was mangled by the link converter");
  assert.ok(html.includes("<a href=\"https://x.example\""), "prose link did not convert");
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