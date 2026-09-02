// Headless UI test for Research Analyst — collapsible report sections (Phase C)
//
// Runs the REAL ui/app.js offline (same vm + DOM-shim harness) and asserts that
// mdToHTML wraps each <h2> section in <details class="report-section" open> so
// analysts can collapse steps without anything hidden by default.
//
//   Run:  node ui/tests/collapsible_sections.test.mjs

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

const FIXTURE = [
  "# ACME Research Report",
  "",
  "## Step 1 — Snapshot",
  "",
  "Intro paragraph with a [link](https://x.example).",
  "",
  "## Step 2 — Valuation",
  "",
  "| Metric | Value |", "| --- | --- |", "| WACC | 9% |",
  "",
  "## Step 3 — Risks",
  "",
  "Key risks summarized.",
  "",
].join("\n");

test("every h2 section becomes an open details block", () => {
  const html = loadApp().mdToHTML(FIXTURE);
  const opens = (html.match(/<details class="report-section" open>/g) || []).length;
  assert.strictEqual(opens, 3, `expected 3 collapsible sections, found ${opens}`);
  const closes = (html.match(/<\/details>/g) || []).length;
  assert.strictEqual(closes, 3, "details blocks must be balanced");
});

test("headings are preserved inside summary", () => {
  const html = loadApp().mdToHTML(FIXTURE);
  for (const step of ["Step 1 — Snapshot", "Step 2 — Valuation", "Step 3 — Risks"]) {
    assert.ok(html.includes(`<summary><h2>${step}</h2></summary>`), `heading ${step} not in summary`);
  }
});

test("h1 title is NOT wrapped (only h2 sections)", () => {
  const html = loadApp().mdToHTML(FIXTURE);
  assert.ok(html.includes("<h1>ACME Research Report</h1>"), "h1 must stay unwrapped");
  assert.ok(!html.includes("<details class=\"report-section\">\n<h1"), "h1 must not be inside a details block");
});

test("section content stays inside the body wrapper", () => {
  const html = loadApp().mdToHTML(FIXTURE);
  const i = html.indexOf("Step 2 — Valuation");
  const after = html.slice(i, i + 400);
  assert.ok(after.includes("WACC") && after.includes("</div></details>"), "step 2 body content must live inside its details block");
});

test("chart blocks are preserved inside collapsible sections", () => {
  const ctx = loadApp();
  const plotly = `<div class="plotly-chart-data" data-plotly="e30="></div>`;
  const mermaid = `<div class="mermaid-data" data-mermaid="e30="></div>`;
  const md = "## Step 1 — Snapshot\n\n" + plotly + "\n\n## Step 2 — Valuation\n\n" + mermaid + "\n";
  const html = ctx.mdToHTML(md);
  assert.ok(html.includes(plotly), "plotly block lost inside details");
  assert.ok(html.includes(mermaid), "mermaid block lost inside details");
  assert.strictEqual((html.match(/<details class="report-section" open>/g) || []).length, 2);
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