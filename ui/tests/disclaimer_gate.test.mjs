// Headless UI tests for Research Analyst — disclaimer gate
//
// Runs the REAL ui/app.js offline in a Node `vm` context against a minimal
// DOM shim (no jsdom / no network required).
//
//   Run:  node ui/tests/disclaimer_gate.test.mjs
//
// Coverage:
//   - First load (no stored ack) shows gate with full text
//   - Clicking accept sets localStorage and hides gate
//   - When stored ack matches version, gate stays hidden
//   - If fetch rejects, gate stays hidden (fail-open)

import assert from "node:assert";
import vm from "node:vm";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const APP_JS = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");

function makeEnv(ids) {
  const registry = new Map();
  const all = [];
  const localStorage = new Map();

  class El {
    constructor(tag) {
      this.tagName = (tag || "div").toUpperCase();
      this.children = []; this.parentNode = null;
      this._attrs = {}; this._innerHTML = ""; this._className = ""; this._id = "";
      this.style = {}; this.hidden = false; this.disabled = false;
      this.value = ""; this._textContent = ""; this.href = ""; this.download = ""; this.type = "";
      this._listeners = {}; this._open = false;
    }
    get id() { return this._id; }
    set id(v) { if (this._id && registry.get(this._id) === this) registry.delete(this._id); this._id = v; if (v) registry.set(v, this); }
    get className() { return this._className; }
    set className(v) { this._className = v || ""; }
    get innerHTML() { return this._innerHTML; }
    set innerHTML(v) { this._innerHTML = String(v); if (this._innerHTML === "") this.children = []; }
    get textContent() { return this._textContent; }
    set textContent(v) { this._textContent = String(v); }
    setAttribute(k, v) { this._attrs[k] = String(v); if (k === "id") this.id = v; }
    getAttribute(k) { return this._attrs[k] || null; }
    appendChild(n) { n.parentNode = this; this.children.push(n); return n; }
    removeChild(n) { const i = this.children.indexOf(n); if (i >= 0) this.children.splice(i, 1); n.parentNode = null; return n; }
    remove() { if (this.parentNode) this.parentNode.removeChild(this); }
    addEventListener(t, fn) { (this._listeners[t] || (this._listeners[t] = [])).push(fn); }
    removeEventListener(t, fn) { const a = this._listeners[t]; if (a) { const i = a.indexOf(fn); if (i >= 0) a.splice(i, 1); } }
    dispatch(t, ev) { ev = ev || {}; ev.type = t; if (ev.target === undefined) ev.target = this; if (!ev.preventDefault) ev.preventDefault = () => {}; (this._listeners[t] || []).slice().forEach((fn) => fn.call(this, ev)); }
    click() { this.dispatch("click", { target: this }); }
    focus() {}
    showModal() { this._open = true; }
    close() { this._open = false; }
  }

  const document = {
    createElement(tag) { const el = new El(tag); all.push(el); return el; },
    getElementById(id) { return registry.get(id) || null; },
    addEventListener() {},
  };
  document.body = document.createElement("body");

  function mk(id, tag) { const el = document.createElement(tag || "div"); el.id = id; return el; }
  ids.forEach((spec) => { mk(spec.id, spec.tag); });
  
  // Add disclaimer gate elements
  const gate = mk("ra-disclaimer-gate", "section");
  const gateContent = document.createElement("div");
  gateContent.className = "disclaimer-gate__content";
  const gateTitle = document.createElement("h2");
  gateTitle.id = "ra-gate-title";
  gateTitle.textContent = "Before you use Research Analyst";
  const gateBody = mk("ra-gate-body", "div");
  gateBody.className = "disclaimer-gate__body";
  const gateAccept = mk("ra-gate-accept", "button");
  gateAccept.textContent = "I understand — continue";
  gateAccept.className = "btn btn--primary";
  
  gateContent.appendChild(gateTitle);
  gateContent.appendChild(gateBody);
  gateContent.appendChild(gateAccept);
  gate.appendChild(gateContent);
  document.body.appendChild(gate);

  const state = { fetchImpl: async () => { throw new Error("fetch not mocked"); } };
  const context = {
    document,
    window: { 
      location: { href: "" },
      localStorage: {
        getItem: (k) => localStorage.get(k) || null,
        setItem: (k, v) => localStorage.set(k, v),
      },
    },
    fetch: (...a) => state.fetchImpl(...a),
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (h) => clearTimeout(h),
    requestAnimationFrame: (fn) => setTimeout(fn, 0),
    console,
    JSON, Date, Math, Object, Array, String, Number, Boolean, RegExp, Error, Promise,
    encodeURIComponent,
  };
  vm.createContext(context);
  vm.runInContext(APP_JS, context, { filename: "app.js" });

  return { context, document, registry, state, localStorage, el: (id) => registry.get(id) };
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
  { id: "ra-disclaimer-gate", tag: "section" }, { id: "ra-gate-body", tag: "div" }, { id: "ra-gate-accept", tag: "button" },
];

const flush = async (n = 40) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0)); };

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

// --- First load: no stored ack -> shows gate with full text ---
test("first load: no stored ack shows gate with full text", async () => {
  const env = makeEnv(ELEMENT_IDS);
  env.state.fetchImpl = async (url) => {
    assert.strictEqual(url, "/api/disclaimer");
    return { ok: true, json: async () => ({ 
      version: "1", 
      full: "Disclaimer text here", 
      short: "Short disclaimer" 
    }) };
  };
  
  await flush();
  const gate = env.el("ra-disclaimer-gate");
  assert.ok(gate, "gate element exists");
  assert.strictEqual(gate.hidden, false, "gate is shown");
  assert.strictEqual(env.el("ra-gate-body").textContent, "Disclaimer text here", "full text inserted");
  assert.strictEqual(env.localStorage.size, 0, "no localStorage writes yet");
});

// --- Click accept: sets localStorage and hides gate ---
test("click accept: sets localStorage and hides gate", async () => {
  const env = makeEnv(ELEMENT_IDS);
  env.state.fetchImpl = async () => ({
    ok: true, json: async () => ({ version: "1", full: "Disclaimer text here" })
  });
  
  await flush();
  env.el("ra-gate-accept").click();
  await flush();
  
  assert.strictEqual(env.el("ra-disclaimer-gate").hidden, true, "gate hidden after accept");
  assert.strictEqual(env.localStorage.get("ra_disclaimer_ack"), "1", "version stored in localStorage");
});

// --- Already acked: gate stays hidden ---
test("already acked: gate stays hidden", async () => {
  const env = makeEnv(ELEMENT_IDS);
  env.localStorage.set("ra_disclaimer_ack", "1");
  env.state.fetchImpl = async () => ({
    ok: true, json: async () => ({ version: "1", full: "Disclaimer text here" })
  });
  
  await flush();
  assert.strictEqual(env.el("ra-disclaimer-gate").hidden, true, "gate remains hidden");
  assert.strictEqual(env.localStorage.get("ra_disclaimer_ack"), "1", "version unchanged");
});

// --- Fetch fails: gate stays hidden (fail-open) ---
test("fetch fails: gate stays hidden (fail-open)", async () => {
  const env = makeEnv(ELEMENT_IDS);
  env.state.fetchImpl = async () => { throw new Error("Network error"); };
  
  await flush();
  assert.strictEqual(env.el("ra-disclaimer-gate").hidden, true, "gate hidden on fetch failure");
  assert.strictEqual(env.localStorage.size, 0, "no localStorage writes");
});

// --- Run tests ---
(async () => {
  let pass = 0, fail = 0;
  for (const t of tests) {
    try { await t.fn(); console.log("  \u2713 " + t.name); pass++; }
    catch (e) { console.error("  \u2717 " + t.name + "\n      " + (e && e.message ? e.message : e)); fail++; }
  }
  console.log(`\n${pass}/${tests.length} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();