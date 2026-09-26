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

// Headless UI tests for Research Analyst — comparative (v0.2.0) + single-ticker regression.
//
// Runs the REAL ui/app.js offline in a Node `vm` context against a minimal,
// dependency-free DOM shim (no jsdom / no network required). This is the
// headless equivalent of the v0.1.2 jsdom approach; it can be swapped for
// jsdom in CI where npm is reachable without changing the assertions.
//
//   Run:  node ui/tests/compare.test.mjs
//
// Coverage:
//   - Compare 2 and 5 tickers -> mocked /api/compare -> scorecard + per-dimension
//     tables rendered; 3-button export toolbar present; MD + HTML exports are
//     self-contained (footer + Buy Me a Coffee + prepared-on), disclaimer present,
//     no leaked/undefined data.
//   - Invalid counts (1 and 6) -> inline validation error, NO request fired.
//   - Regression: single-ticker /api/research path still renders + exports.

import assert from "node:assert";
import vm from "node:vm";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_JS = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");

// --------------------------------------------------------------------------
// Minimal DOM shim (only the surface ui/app.js actually touches)
// --------------------------------------------------------------------------

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function makeEnv(ids) {
  const registry = new Map();
  const all = [];

  function matchSel(el, selector) {
    return String(selector).split(",").map((t) => t.trim()).filter(Boolean).some((tok) => {
      if (tok.startsWith(".")) {
        const cls = tok.slice(1);
        return (el._className || "").split(/\s+/).filter(Boolean).includes(cls);
      }
      return el.tagName === tok.toUpperCase();
    });
  }
  function descendants(el) {
    const out = [];
    (function walk(n) { n.children.forEach((c) => { out.push(c); walk(c); }); })(el);
    return out;
  }

  class ClassList {
    constructor(el) { this.el = el; }
    _tok() { return (this.el._className || "").split(/\s+/).filter(Boolean); }
    add(...c) { const t = this._tok(); c.forEach((x) => { if (!t.includes(x)) t.push(x); }); this.el._className = t.join(" "); }
    remove(...c) { this.el._className = this._tok().filter((x) => !c.includes(x)).join(" "); }
    contains(c) { return this._tok().includes(c); }
    toggle(c, force) { const has = this.contains(c); const on = force === undefined ? !has : !!force; if (on) this.add(c); else this.remove(c); return on; }
  }

  class El {
    constructor(tag) {
      this.tagName = (tag || "div").toUpperCase();
      this.children = []; this.parentNode = null;
      this._attrs = {}; this._innerHTML = ""; this._className = ""; this._id = "";
      this.style = {}; this.hidden = false; this.disabled = false;
      this.value = ""; this._textContent = ""; this.href = ""; this.download = ""; this.type = "";
      this._listeners = {}; this._open = false;
      this.classList = new ClassList(this);
    }
    get id() { return this._id; }
    set id(v) { if (this._id && registry.get(this._id) === this) registry.delete(this._id); this._id = v; if (v) registry.set(v, this); }
    get className() { return this._className; }
    set className(v) { this._className = v || ""; }
    get innerHTML() { return this._innerHTML; }
    set innerHTML(v) { this._innerHTML = String(v); if (this._innerHTML === "") this.children = []; }
    get textContent() { return this._textContent; }
    set textContent(v) { this._textContent = String(v); this._innerHTML = escapeHtml(String(v)); }
    setAttribute(k, v) { this._attrs[k] = String(v); if (k === "id") this.id = v; }
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; }
    appendChild(n) { n.parentNode = this; this.children.push(n); return n; }
    insertBefore(n, ref) { n.parentNode = this; const i = this.children.indexOf(ref); if (i < 0) this.children.push(n); else this.children.splice(i, 0, n); return n; }
    removeChild(n) { const i = this.children.indexOf(n); if (i >= 0) this.children.splice(i, 1); n.parentNode = null; return n; }
    remove() { if (this.parentNode) this.parentNode.removeChild(this); }
    after(...nodes) { if (!this.parentNode) return; const i = this.parentNode.children.indexOf(this); const els = nodes.map((n) => typeof n === "string" ? Object.assign(new El("span"), {_textContent: n}) : n); els.forEach((n) => { if (n.parentNode) n.parentNode.removeChild(n); n.parentNode = this.parentNode; }); this.parentNode.children.splice(i + 1, 0, ...els); }
    before(...nodes) { if (!this.parentNode) return; const i = this.parentNode.children.indexOf(this); const els = nodes.map((n) => typeof n === "string" ? Object.assign(new El("span"), {_textContent: n}) : n); els.forEach((n) => { if (n.parentNode) n.parentNode.removeChild(n); n.parentNode = this.parentNode; }); this.parentNode.children.splice(i, 0, ...els); }
    addEventListener(t, fn) { (this._listeners[t] || (this._listeners[t] = [])).push(fn); }
    removeEventListener(t, fn) { const a = this._listeners[t]; if (a) { const i = a.indexOf(fn); if (i >= 0) a.splice(i, 1); } }
    dispatch(t, ev) { ev = ev || {}; ev.type = t; if (ev.target === undefined) ev.target = this; if (!ev.preventDefault) ev.preventDefault = () => {}; (this._listeners[t] || []).slice().forEach((fn) => fn.call(this, ev)); }
    click() { this.dispatch("click", { target: this }); }
    focus() {}
    showModal() { this._open = true; }
    close() { this._open = false; }
    cloneNode(deep) { const c = new El(this.tagName); c._innerHTML = this._innerHTML; c._className = this._className; c._attrs = Object.assign({}, this._attrs); c._textContent = this._textContent; if (deep) c.children = this.children.map((ch) => ch.cloneNode(true)); return c; }
    querySelectorAll(sel) { return descendants(this).filter((el) => matchSel(el, sel)); }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  }

  const document = {
    createElement(tag) { const el = new El(tag); all.push(el); return el; },
    getElementById(id) { return registry.get(id) || null; },
    querySelectorAll(sel) { return all.filter((el) => matchSel(el, sel)); },
    querySelector(sel) { return all.filter((el) => matchSel(el, sel))[0] || null; },
    addEventListener() {},
  };
  document.body = document.createElement("body");

  function mk(id, tag) { const el = document.createElement(tag || "div"); el.id = id; return el; }
  ids.forEach((spec) => { mk(spec.id, spec.tag); });

  // Parent wiring addExportToolbar relies on: reportContent.parentNode === results
  const results = registry.get("results");
  ["meta-bar", "report-tabs", "report-content", "export-footer"].forEach((id) => {
    const el = registry.get(id); if (el && results) results.appendChild(el);
  });
  document.body.appendChild(results || document.createElement("div"));

  // Captured blobs (downloadBlob -> new Blob([content], {type}))
  const blobs = [];
  class Blob {
    constructor(parts, opts) { this._parts = parts || []; this.type = (opts && opts.type) || ""; blobs.push(this); }
    async text() { return this._parts.join(""); }
  }

  const state = { fetchImpl: async () => { throw new Error("fetch not mocked"); }, prints: 0 };
  const context = {
    document,
    window: { location: { href: "" } },
    fetch: (...a) => state.fetchImpl(...a),
    Blob,
    URL: { createObjectURL: () => "blob:mock", revokeObjectURL: () => {} },
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (h) => clearTimeout(h),
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    console,
    JSON, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Promise,
    encodeURIComponent, atob: (s) => Buffer.from(s, "base64").toString("binary"), btoa: (s) => Buffer.from(s, "binary").toString("base64"),
  };
  context.window.print = () => { state.prints++; };
  context.print = context.window.print;
  vm.createContext(context);
  vm.runInContext(APP_JS, context, { filename: "app.js" });

  return { context, document, registry, state, blobs, el: (id) => registry.get(id), lastBlob: () => blobs[blobs.length - 1] };
}

const ELEMENT_IDS = [
  { id: "research-form", tag: "form" }, { id: "ticker", tag: "input" }, { id: "report-type", tag: "select" },
  { id: "timeframe", tag: "select" }, { id: "btn-submit", tag: "button" }, { id: "btn-text", tag: "span" },
  { id: "btn-spinner", tag: "span" }, { id: "status" }, { id: "status-text" }, { id: "progress-bar" },
  { id: "error-panel" }, { id: "error-message" }, { id: "btn-retry", tag: "button" }, { id: "results" },
  { id: "meta-bar" }, { id: "report-tabs" }, { id: "report-content" }, { id: "btn-about", tag: "button" },
  { id: "about-modal", tag: "dialog" }, { id: "btn-close-about", tag: "button" }, { id: "export-footer" },
  { id: "mode-single", tag: "button" }, { id: "mode-compare", tag: "button" }, { id: "compare-form", tag: "form" },
  { id: "compare-tickers", tag: "input" }, { id: "compare-timeframe", tag: "select" }, { id: "compare-error", tag: "small" },
  { id: "btn-compare", tag: "button" }, { id: "btn-compare-text", tag: "span" }, { id: "btn-compare-spinner", tag: "span" },
  { id: "resolve-candidates" },
];

const flush = async (n = 40) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0)); };

// --------------------------------------------------------------------------
// Mock server payloads
// --------------------------------------------------------------------------

const MOCK_CSS = ".report table{border-collapse:collapse}.report th{background:#f1f5f9}/*MOCK_STYLE_MARKER*/";

function compareMarkdown(tickers) {
  const cols = tickers.join(" | ");
  const sep = tickers.map(() => "------").join("|");
  return [
    `# Comparative Research Report — ${tickers.join(" vs ")}`,
    "",
    "**Generated:** 2026-07-18 12:00 UTC",
    `**Tickers analyzed:** ${tickers.join(", ")}`,
    "",
    "## Scorecard",
    "",
    "| Rank | Ticker | Company | Overall (0–100) | Metric wins |",
    "|------|--------|---------|-----------------|-------------|",
    ...tickers.map((t, i) => `| ${i + 1} | **${t}** | ${t} Inc | ${(90 - i * 5).toFixed(1)} | ${2 - i} |`),
    "",
    "## Valuation",
    "",
    `| Metric | ${cols} |`,
    `|--------|${sep}|`,
    `| Base-case implied upside | ${tickers.map((_, i) => `${(12 - i).toFixed(1)}% (#${i + 1})`).join(" | ")} |`,
    "",
    "## Growth & Margins",
    "",
    `| Metric | ${cols} |`,
    `|--------|${sep}|`,
    `| Operating margin (base case) | ${tickers.map((_, i) => `${(30 - i).toFixed(1)}%`).join(" | ")} |`,
    "",
    "---",
    "",
    "**Disclaimer:**",
    "This report is for informational and educational purposes only. It is not financial advice.",
    "",
    "**Compliance:** This tool ranks and compares numbers; you decide. It makes no buy, sell, or hold recommendation.",
    "",
    "*Report prepared on https://ra.devinfo.dev — 2026-07-18. Support: https://www.buymeacoffee.com/nrupala*",
  ].join("\n");
}

function compareResponse(tickers) {
  return {
    request_id: "test1234",
    tickers,
    report: {
      requested_tickers: tickers, tickers,
      scorecard: tickers.map((t, i) => ({ ticker: t, company_name: t + " Inc", overall_score: 90 - i * 5, wins: 2 - i })),
      dimensions: [{ name: "Valuation", metrics: [] }],
      errors: [],
    },
    report_markdown: compareMarkdown(tickers),
    report_html: "<!DOCTYPE html><html><head><style>.win{}</style></head><body><h1>Comparative Research Report — " +
      tickers.join(" vs ") + "</h1><h2>Scorecard</h2><table></table></body></html>",
  };
}

function researchResponse() {
  return {
    request_id: "r1", ticker: "AAPL", company_name: "Apple Inc.", security_type: "equity",
    reports: [{ report_type: "Comprehensive" }],
    metadata: { processing_time_seconds: 1.2, data_sources: ["SEC EDGAR", "Market Data"] },
    reports_markdown: ["# Apple Inc. (AAPL)\n\nSome **bold** analysis.\n\n## Valuation\n\n- Point A\n- Point B\n"],
  };
}

// --------------------------------------------------------------------------
// Test runner
// --------------------------------------------------------------------------

const tests = [];
const test = (name, fn) => tests.push({ name, fn });
const occurrences = (hay, needle) => hay.split(needle).length - 1;

// --- Compare: valid 2 tickers ---
test("compare 2 tickers: renders scorecard + per-dimension tables, 3-button toolbar, self-contained exports", async () => {
  const env = makeEnv(ELEMENT_IDS);
  let fetchCalls = 0; let sentBody = null;
  env.state.fetchImpl = async (url, opts) => {
    if (url === "/style.css") return { ok: true, text: async () => MOCK_CSS };
    fetchCalls++; assert.strictEqual(url, "/api/compare"); assert.strictEqual(opts.method, "POST");
    sentBody = JSON.parse(opts.body);
    return { ok: true, json: async () => compareResponse(["AAPL", "MSFT"]) };
  };
  env.el("mode-compare").click();
  env.el("compare-tickers").value = "AAPL, MSFT";
  env.el("compare-timeframe").value = "1Y"; // mirror the selected default option
  env.el("compare-form").dispatch("submit", {});
  await flush();

  assert.strictEqual(fetchCalls, 1, "exactly one /api/compare request");
  assert.deepStrictEqual(sentBody.tickers, ["AAPL", "MSFT"], "request body carries the two tickers");
  assert.strictEqual(sentBody.timeframe, "1Y", "request body carries the selected timeframe");

  const rc = env.el("report-content").innerHTML;
  assert.ok(/Scorecard/.test(rc), "scorecard heading rendered");
  assert.ok(/Valuation/.test(rc) && /Growth &amp; Margins|Growth & Margins/.test(rc), "per-dimension sections rendered");
  assert.ok(/<table/.test(rc), "side-by-side tables rendered");
  assert.ok(/Disclaimer/.test(rc), "disclaimer carried into render");
  assert.ok(!/undefined/.test(rc), "no leaked undefined in render");

  const toolbar = env.el("export-toolbar");
  assert.ok(toolbar, "export toolbar present");
  assert.strictEqual(toolbar.children.length, 3, "3-button toolbar (compare mode has no data button)");
  assert.deepStrictEqual(toolbar.children.map((b) => b.textContent), ["Download MD", "Download HTML", "Download PDF"]);

  // MD export
  env.context.exportMD();
  const md = await env.lastBlob().text();
  assert.ok(/Scorecard/.test(md) && /Disclaimer/.test(md), "MD export carries report + disclaimer");
  assert.ok(md.includes("Report prepared on https://ra.devinfo.dev"), "MD footer prepared-on present");
  assert.ok(md.includes("buymeacoffee.com/nrupalakolt"), "MD footer Buy Me a Coffee present");
  assert.strictEqual(occurrences(md, "Report prepared on https://ra.devinfo.dev"), 1, "prepared-on appears exactly once (server trailer stripped)");
  assert.ok(!/undefined/.test(md), "no undefined in MD export");

  // HTML export (self-contained)
  await env.context.exportHTML();
  const html = await env.lastBlob().text();
  assert.ok(html.startsWith("<!DOCTYPE html>"), "HTML export is a full document");
  assert.ok(html.includes("MOCK_STYLE_MARKER"), "HTML export inlines the stylesheet (self-contained)");
  assert.ok(!/href="\/style\.css"/.test(html), "HTML export does not link external /style.css");
  assert.ok(/Scorecard/.test(html) && /<table/.test(html), "HTML export carries scorecard + tables");
  assert.ok(/Disclaimer/.test(html), "HTML export carries disclaimer");
  assert.ok(html.includes("Report prepared on") && html.includes("ra.devinfo.dev"), "HTML footer prepared-on present");
  assert.ok(html.includes("buymeacoffee.com/nrupalakolt"), "HTML footer Buy Me a Coffee present");
  assert.ok(!/undefined/.test(html), "no undefined in HTML export");
});

// --- Compare: valid 5 tickers ---
test("compare 5 tickers: request carries 5 tickers and render present", async () => {
  const env = makeEnv(ELEMENT_IDS);
  let sentBody = null;
  env.state.fetchImpl = async (url, opts) => {
    if (url === "/style.css") return { ok: true, text: async () => MOCK_CSS };
    sentBody = JSON.parse(opts.body);
    return { ok: true, json: async () => compareResponse(["AAPL", "MSFT", "GOOG", "AMZN", "META"]) };
  };
  env.el("mode-compare").click();
  env.el("compare-tickers").value = "AAPL MSFT GOOG AMZN META";
  env.el("compare-form").dispatch("submit", {});
  await flush();
  assert.strictEqual(sentBody.tickers.length, 5, "5 tickers sent");
  const rc = env.el("report-content").innerHTML;
  assert.ok(/Scorecard/.test(rc) && /<table/.test(rc), "5-ticker comparison rendered");
  assert.ok(env.el("export-toolbar").children.length === 3, "toolbar present for 5-ticker (compare mode)");
});

// --- Compare: dedupe collapses to invalid count ---
test("compare dedupe: 'AAPL, AAPL' collapses to 1 distinct -> invalid, no request", async () => {
  const env = makeEnv(ELEMENT_IDS);
  let fetchCalls = 0;
  env.state.fetchImpl = async () => { fetchCalls++; return { ok: true, json: async () => ({}) }; };
  env.el("mode-compare").click();
  env.el("compare-tickers").value = "AAPL, AAPL";
  env.el("compare-form").dispatch("submit", {});
  await flush(10);
  assert.strictEqual(fetchCalls, 0, "no request for duplicate collapsing to 1");
  assert.strictEqual(env.el("compare-error").hidden, false, "inline error shown");
});

// --- Invalid: 1 ticker ---
test("invalid count 1: inline error, NO request fired", async () => {
  const env = makeEnv(ELEMENT_IDS);
  let fetchCalls = 0;
  env.state.fetchImpl = async () => { fetchCalls++; return { ok: true, json: async () => ({}) }; };
  env.el("mode-compare").click();
  env.el("compare-tickers").value = "AAPL";
  env.el("compare-form").dispatch("submit", {});
  await flush(10);
  assert.strictEqual(fetchCalls, 0, "no request fired for 1 ticker");
  assert.strictEqual(env.el("compare-error").hidden, false, "inline validation error visible");
  assert.ok(/between 2 and 5/.test(env.el("compare-error").textContent), "clear validation message");
  assert.strictEqual(env.el("results").hidden !== false, true, "results not shown");
});

// --- Invalid: 6 tickers ---
test("invalid count 6: inline error, NO request fired", async () => {
  const env = makeEnv(ELEMENT_IDS);
  let fetchCalls = 0;
  env.state.fetchImpl = async () => { fetchCalls++; return { ok: true, json: async () => ({}) }; };
  env.el("mode-compare").click();
  env.el("compare-tickers").value = "AAPL,MSFT,GOOG,AMZN,META,NVDA";
  env.el("compare-form").dispatch("submit", {});
  await flush(10);
  assert.strictEqual(fetchCalls, 0, "no request fired for 6 tickers");
  assert.strictEqual(env.el("compare-error").hidden, false, "inline validation error visible");
});

// --- Regression: single-ticker path ---
test("regression: single-ticker /api/research still renders + exports", async () => {
  const env = makeEnv(ELEMENT_IDS);
  let researchUrl = null;
  env.state.fetchImpl = async (url, opts) => {
    if (url === "/style.css") return { ok: true, text: async () => MOCK_CSS };
    researchUrl = url;
    return { ok: true, json: async () => researchResponse() };
  };
  env.el("ticker").value = "AAPL";
  env.el("research-form").dispatch("submit", {});
  await flush();
  assert.strictEqual(researchUrl, "/api/research", "single-ticker still calls /api/research");
  const rc = env.el("report-content").innerHTML;
  assert.ok(/Apple/.test(rc) && /Valuation/.test(rc), "single-ticker report rendered");
  const toolbar = env.el("export-toolbar");
  assert.strictEqual(toolbar.children.length, 4, "single-ticker export toolbar intact (incl. data download)");
  env.context.exportMD();
  const md = await env.lastBlob().text();
  assert.ok(/Apple/.test(md), "single-ticker MD export has content");
  assert.ok(md.includes("Report prepared on https://ra.devinfo.dev"), "single-ticker MD footer intact");
});

// --- A.3b: company-name / symbol resolve helpers ---
function resolveResolved(symbol, name) {
  return { query: name, status: "resolved",
    resolved: { symbol, name, quote_type: "EQUITY", market: "IN", market_name: "India (NSE)", currency: "INR" },
    candidates: [], note: "exact name match" };
}
function resolveAmbiguous(query) {
  return { query, status: "ambiguous", resolved: null,
    candidates: [
      { symbol: "RELIANCE.NS", name: "Reliance Industries Ltd", market: "IN", market_name: "India (NSE)", currency: "INR" },
      { symbol: "RELIANCE.BO", name: "Reliance Industries Ltd", market: "IN", market_name: "India (BSE)", currency: "INR" },
    ], note: "multiple listings" };
}

// --- A.3b: multi-word name -> /api/resolve (resolved) -> /api/research ---
test("name lookup: multi-word name resolves then researches the resolved ticker", async () => {
  const env = makeEnv(ELEMENT_IDS);
  const calls = [];
  env.state.fetchImpl = async (url, opts) => {
    if (url === "/style.css") return { ok: true, text: async () => MOCK_CSS };
    calls.push(url);
    if (url === "/api/resolve") {
      assert.strictEqual(opts.method, "POST");
      assert.strictEqual(JSON.parse(opts.body).query, "Reliance Industries");
      return { ok: true, json: async () => resolveResolved("RELIANCE.NS", "Reliance Industries") };
    }
    if (url === "/api/research") {
      assert.strictEqual(JSON.parse(opts.body).ticker, "RELIANCE.NS", "researches the resolved ticker");
      return { ok: true, json: async () => researchResponse() };
    }
    throw new Error("unexpected url " + url);
  };
  env.el("ticker").value = "Reliance Industries";
  env.el("research-form").dispatch("submit", {});
  await flush();
  assert.deepStrictEqual(calls, ["/api/resolve", "/api/research"], "resolve precedes research");
  assert.ok(/Apple|Valuation/.test(env.el("report-content").innerHTML), "report rendered after resolve");
});

// --- A.3b: ambiguous name -> candidate picker -> click -> /api/research ---
test("name lookup: ambiguous shows a candidate picker; clicking one researches that ticker", async () => {
  const env = makeEnv(ELEMENT_IDS);
  const calls = [];
  env.state.fetchImpl = async (url, opts) => {
    if (url === "/style.css") return { ok: true, text: async () => MOCK_CSS };
    calls.push(url);
    if (url === "/api/resolve") return { ok: true, json: async () => resolveAmbiguous("Reliance") };
    if (url === "/api/research") {
      assert.strictEqual(JSON.parse(opts.body).ticker, "RELIANCE.NS");
      return { ok: true, json: async () => researchResponse() };
    }
    throw new Error("unexpected url " + url);
  };
  env.el("ticker").value = "Reliance";
  env.el("research-form").dispatch("submit", {});
  await flush();
  assert.deepStrictEqual(calls, ["/api/resolve"], "no research until a candidate is picked");
  const box = env.el("resolve-candidates");
  assert.strictEqual(box.hidden, false, "candidate picker shown");
  const btns = box.children.filter((c) => c.tagName === "BUTTON");
  assert.strictEqual(btns.length, 2, "both listings offered");
  btns[0].click();
  await flush();
  assert.deepStrictEqual(calls, ["/api/resolve", "/api/research"], "picking a candidate fires research");
  assert.ok(/Apple|Valuation/.test(env.el("report-content").innerHTML), "report rendered after pick");
});

// --------------------------------------------------------------------------
(async () => {
  let pass = 0, fail = 0;
  for (const t of tests) {
    try { await t.fn(); console.log("  \u2713 " + t.name); pass++; }
    catch (e) { console.error("  \u2717 " + t.name + "\n      " + (e && e.message ? e.message : e)); fail++; }
  }
  console.log(`\n${pass}/${tests.length} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
