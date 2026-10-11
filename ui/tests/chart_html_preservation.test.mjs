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

// Headless UI test for Research Analyst — chart HTML preservation in mdToHTML
//
// Runs the REAL ui/app.js offline in a Node `vm` context against a minimal DOM
// shim (no jsdom / no network), then calls the app's own mdToHTML() on a
// fixture report whose Plotly chart carries an `<extra></extra>` hovertemplate.
//
//   Run:  node ui/tests/chart_html_preservation.test.mjs
//
// Why this exists (regression guard — this class of bug shipped with ZERO coverage):
//   mdToHTML() shields <div class="plotly-chart-data|mermaid-data"> blocks with a
//   placeholder BEFORE it escapes <>& and runs the markdown passes, then restores
//   them verbatim at the end. A Plotly hovertemplate contains `<extra></extra>`,
//   whose `>` broke earlier attribute-bounded (`[^>]*>`) and greedy (`[\s\S]*</div>`)
//   preserve regexes: the chart block leaked into the escape + <p>-wrap passes,
//   corrupting the chart AND swallowing the headings around it. Current main uses
//   the non-greedy `[\s\S]*?</div>`, which is correct. This test locks that in.
//
// Coverage:
//   - Every heading in the fixture survives as its own <hN> tag (none dropped/merged)
//   - The Plotly block — including <extra></extra> — is preserved verbatim
//   - The Mermaid block is preserved verbatim
//   - No chart markup leaks into the prose as escaped text (&lt;extra&gt; / &lt;/div&gt;)
//   - Discriminating guards: the two known-buggy preserve regexes DO mangle this
//     exact fixture, proving the fixture actually exercises the failure class.

import assert from "node:assert";
import vm from "node:vm";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_JS = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");

// ---- Minimal DOM shim ----
// app.js builds its `dom` map from getElementById at load and attaches
// listeners, so every referenced id must resolve to *something*. mdToHTML
// itself is pure string work; we only need the module to load without throwing.
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
    // Never return null: any id app.js asks for at load resolves to a live shim node.
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
  return context;
}

// ---- Fixture: a report shaped like real server output ----
// SVG chart block (Phase F: charts are server-rendered static SVG).
const CHART_SVG = '<svg xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto" viewBox="0 0 640 420"><g><text>x=1: $10.50</text></g></svg>';
const CHART_DIV = `<div class="chart-svg">${CHART_SVG}</div>`;

const MERMAID_SYNTAX = "graph TD; A[Screen] --> B{Undervalued?}; B -->|Yes| C[Buy list]; B -->|No| D[Watch];";
const DIAGRAM_DIV = `<div class="chart-svg"><pre class="diagram-fallback">${MERMAID_SYNTAX}</pre></div>`;

// Headings deliberately placed BEFORE, BETWEEN, and AFTER the two chart blocks.
const SECTIONS = [
  { md: "# ACME Research Report",     tag: "h1", text: "ACME Research Report" },
  { md: "## Step 1 — Snapshot",       tag: "h2", text: "Step 1 — Snapshot" },
  { md: "## Step 2 — Valuation",      tag: "h2", text: "Step 2 — Valuation" },   // between the two charts
  { md: "### Step 2a — DCF detail",   tag: "h3", text: "Step 2a — DCF detail" }, // between the two charts
  { md: "## Step 3 — Technicals",     tag: "h2", text: "Step 3 — Technicals" },  // after both charts
  { md: "## Step 4 — Risks",          tag: "h2", text: "Step 4 — Risks" },       // after both charts
];

const FIXTURE = [
  SECTIONS[0].md, "",
  SECTIONS[1].md, "",
  "Revenue grew **12%** YoY and margins expanded.", "",
  CHART_DIV, "",                       // svg chart, headings on both sides
  SECTIONS[2].md, "",
  "Fair-value estimate derived below.", "",
  SECTIONS[3].md, "",
  "| Metric | Value |", "| --- | --- |", "| WACC | 9.0% |", "",
  DIAGRAM_DIV, "",                      // diagram block immediately after a chart
  SECTIONS[4].md, "",
  "- RSI neutral", "- MACD positive", "",
  SECTIONS[5].md, "",
  "Key risks summarized.", "",
].join("\n");

// ---- Tiny runner (mirrors the other ui/tests/*.test.mjs) ----
const tests = [];
const test = (name, fn) => tests.push({ name, fn });

test("app.js exposes a callable mdToHTML", () => {
  const ctx = loadApp();
  assert.strictEqual(typeof ctx.mdToHTML, "function", "mdToHTML must be defined by app.js");
});

test("every step heading survives as its own <hN> tag", () => {
  const html = loadApp().mdToHTML(FIXTURE);
  for (const s of SECTIONS) {
    assert.ok(
      html.includes(`<${s.tag}>${s.text}</${s.tag}>`),
      `heading dropped/mangled: expected <${s.tag}>${s.text}</${s.tag}>`
    );
  }
  // Exactly the six headings we authored — no swallow, no duplication.
  const hCount = (html.match(/<h[1-4]>/g) || []).length;
  assert.strictEqual(hCount, SECTIONS.length, `expected ${SECTIONS.length} headings, found ${hCount}`);
});

test("the SVG chart block is preserved verbatim", () => {
  const html = loadApp().mdToHTML(FIXTURE);
  assert.ok(html.includes(CHART_DIV), "chart-svg block was not preserved verbatim");
  assert.ok(html.includes("<svg"), "svg markup lost");
});

test("the interactive-view button is preserved verbatim (never raw base64 text)", () => {
  const ctx = loadApp();
  const btn = '<button type="button" class="chart-interactive" data-interactive="eyJ0eXBlIjogInNjZW5hcmlvIn0=">Interactive view \u2197</button>';
  const html = ctx.mdToHTML("## Step 1\n\n" + CHART_DIV + "\n\n" + btn + "\n\nTail text.");
  assert.ok(html.includes(btn), "chart-interactive button was not preserved verbatim");
  assert.ok(!html.includes("data-interactive=&quot;"), "button attribute was HTML-escaped");
  assert.ok(!html.includes("&lt;button"), "button tag was escaped to text");
});

test("the Mermaid/D2 block is preserved verbatim", () => {
  const html = loadApp().mdToHTML(FIXTURE);
  assert.ok(html.includes(DIAGRAM_DIV), "diagram block was not preserved verbatim");
});

test("no chart markup leaks into prose as escaped text", () => {
  const html = loadApp().mdToHTML(FIXTURE);
  assert.ok(!html.includes("&lt;svg"), "chart <svg> leaked and was HTML-escaped into the body");
  assert.ok(!html.includes("&lt;/svg&gt;"), "chart </svg> leaked and was HTML-escaped into the body");
});

// ---- Discriminating guards: prove the fixture actually exercises the bug class ----
test("guard: attribute-bounded preserve regex truncates the svg chart (fixture is discriminating)", () => {
  const OLD_ATTR_BOUNDED = /<div class="(?:plotly-chart-data|mermaid-data|chart-svg)"[^>]*>(?:<\/div>)?/;
  const m = OLD_ATTR_BOUNDED.exec(CHART_DIV);
  assert.ok(m, "old regex should still match the opening of the block");
  assert.ok(
    m[0].length < CHART_DIV.length && !m[0].endsWith("</div>"),
    "fixture must contain a '>' inside the div content so the buggy regex truncates it"
  );
});

test("guard: greedy preserve regex swallows headings between chart blocks (fixture is discriminating)", () => {
  const GREEDY = /<div class="(?:plotly-chart-data|mermaid-data|chart-svg)"[\s\S]*<\/div>/; // note: no '?'
  const gm = GREEDY.exec(FIXTURE);
  assert.ok(gm, "greedy regex should match");
  assert.ok(
    gm[0].includes("Step 2 — Valuation") && gm[0].includes("Step 2a — DCF detail"),
    "fixture must have headings sitting between the two chart blocks for the greedy regex to swallow"
  );
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
