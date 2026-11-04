// Quant Lab Phase 1 — headless figure-spec tests (spec §8.1).
//
// The builders are pure payload → spec functions, so the PLAYBOOK 31–36
// acceptance criteria are asserted on the specs themselves: named default
// views on ONE template, unified provenance hover, connectgaps false,
// rangebreaks banned, nulls surviving as null (never 0), no invented
// uncertainty bands, SVG-only traces, and honest degradation (panel-missing
// notes, the contributions-instead-of-tornado resolution, vendor-failed
// leaving the tables intact). Live rendering proof is the Gate 17
// real-browser walk, not this file.
import fs from "node:fs";
import vm from "node:vm";
import assert from "node:assert";

const src = fs.readFileSync(new URL("../app.js", import.meta.url), "utf8");

class El {
  constructor(tag) {
    this.tagName = (tag || "div").toUpperCase();
    this.children = [];
    this.listeners = {};
    this.classList = { add() {}, remove() {}, contains: () => false, toggle() {} };
    this.style = {};
    this.dataset = {};
    this._innerHTML = "";
    this._text = "";
    this.value = "";
    this.hidden = false;
  }
  set innerHTML(v) { this._innerHTML = String(v); }
  get innerHTML() {
    if (this._innerHTML) return this._innerHTML;
    // Model the browser: esc() sets textContent and reads innerHTML back.
    return (this._text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  set textContent(v) { this._text = String(v); }
  get textContent() { return this._text; }
  addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); }
  removeEventListener() {}
  appendChild(c) { this.children.push(c); return c; }
  querySelector() { return new El("div"); }
  querySelectorAll() { return []; }
  setAttribute() {}
  getAttribute() { return null; }
  focus() {}
  click() {}
}

const els = {};
function el(id) { return els[id] || (els[id] = new El("div")); }
const documentStub = {
  getElementById: el,
  querySelector: () => new El("div"),
  querySelectorAll: () => [],
  createElement: (t) => new El(t),
  addEventListener() {},
  body: new El("body"),
  documentElement: new El("html"),
};
const windowStub = {
  location: { hash: "", href: "http://test/", search: "" },
  localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  addEventListener() {},
  history: { pushState() {}, replaceState() {} },
};
const ctx = vm.createContext({
  window: windowStub,
  document: documentStub,
  console,
  URLSearchParams,
  setTimeout,
  clearTimeout,
  fetch: async () => { throw new Error("no network in tests"); },
});
ctx.window.document = documentStub;
vm.runInContext(src, ctx);

// --- fixtures ---------------------------------------------------------------

const FULL = {
  ticker: "TST",
  periods: ["FY2023", "FY2024"],
  currency: "USD",
  statements_source: "Fixture Statements (test)",
  trends: {
    revenue_cagr: 0.12, eps_cagr: 0.2, fcf_cagr: null,
    yoy_revenue_growth_latest: 0.25, gross_margin_latest: 0.42, net_margin_latest: 0.11,
    margin_series: { gross: [0.40, 0.42], net: [0.10, 0.11] },
    yoy_series: { revenue: [null, 0.25] },
  },
  dupont: {
    rows: [
      { period: "FY2023", roe: 0.15, net_margin: 0.10, asset_turnover: 0.6, leverage: 2.5 },
      { period: "FY2024", roe: 0.16, net_margin: 0.11, asset_turnover: 0.62, leverage: 2.35 },
    ],
    latest: { period: "FY2024", roe: 0.16, net_margin: 0.11, asset_turnover: 0.62, leverage: 2.35 },
    attribution: { roe_change_pp: 1.0, margin_contribution_pp: 0.5, turnover_contribution_pp: 0.3, leverage_contribution_pp: 0.2 },
  },
  forensics: {
    altman_z: 3.1, altman_zone: "safe", altman_missing: [],
    beneish_m: -2.1, beneish_flag: false, beneish_missing: [],
    sloan_accruals: 0.02, cash_conversion: 1.5,
  },
  valuation: {
    graham_number: 45, lynch_fair_value: 60,
    implied_explicit_stage_growth: 0.07, implied_perpetual_growth: 0.03,
    discount_rate_used: 0.09,
    sensitivity: {
      rows: { label: "discount_rate", values: [0.08, 0.09, 0.10] },
      cols: { label: "perpetual_growth", values: [0.02, 0.025, 0.03] },
      values: [[150.5, 165.2, 183.9], [120.4, 130.0, 141.8], [98.2, 104.6, null]],
      base: { discount_rate: 0.09, perpetual_growth: 0.025, explicit_growth: 0.05 },
    },
  },
  allocation: {
    incremental_roic_average: null, operating_tax_rate_latest: null,
    dividend_payout_on_earnings: 0.3, dividend_payout_on_fcf: 0.4,
    debt_net_debt_latest: 100, debt_net_debt_to_ebit: 0.5,
    debt_interest_coverage: null, buyback_shares_cagr: -0.01,
  },
  expected_value: {
    expected: 10.0,
    contributions: [{ label: "Base", contribution: 12.5 }, { label: "Bear", contribution: -2.5 }],
    reason: null,
  },
  missing_inputs: ["interest_expense (not fetched by any provider)"],
  assumptions: ["Discount rate r = 9.00% (analyst assumption, not observed market data) used for the implied-growth inversions."],
};

const NULL_HEAVY = {
  ticker: "NUL",
  periods: ["FY2023", "FY2024"],
  currency: "USD",
  statements_source: "Fixture Statements (test)",
  trends: {
    revenue_cagr: null, eps_cagr: null, fcf_cagr: null,
    yoy_revenue_growth_latest: null, gross_margin_latest: null, net_margin_latest: null,
    margin_series: { gross: [null, null], net: [null, null] },
    yoy_series: { revenue: [null, null] },
  },
  dupont: {
    rows: [], latest: null,
    attribution: { roe_change_pp: null, margin_contribution_pp: null, turnover_contribution_pp: null, leverage_contribution_pp: null },
  },
  forensics: {
    altman_z: null, altman_zone: null, altman_missing: ["x5_market_value_of_equity"],
    beneish_m: null, beneish_flag: null, beneish_missing: ["receivables"],
    sloan_accruals: null, cash_conversion: null,
  },
  valuation: {
    graham_number: null, lynch_fair_value: null,
    implied_explicit_stage_growth: null, implied_perpetual_growth: null,
    discount_rate_used: null, sensitivity: null,
  },
  allocation: {
    incremental_roic_average: null, operating_tax_rate_latest: null,
    dividend_payout_on_earnings: null, dividend_payout_on_fcf: null,
    debt_net_debt_latest: null, debt_net_debt_to_ebit: null,
    debt_interest_coverage: null, buyback_shares_cagr: null,
  },
  expected_value: { expected: null, contributions: null, reason: "no scenarios provided" },
  missing_inputs: ["shares_outstanding"],
  assumptions: [],
};

const GAP = JSON.parse(JSON.stringify(FULL));
GAP.periods = ["FY2022", "FY2023", "FY2024"];
GAP.trends.margin_series = { gross: [0.40, null, 0.45], net: [0.10, 0.11, null] };
GAP.trends.yoy_series = { revenue: [null, 0.1, 0.2] };
GAP.expected_value = { expected: null, contributions: null, reason: "no scenarios provided" };

// --- helpers ----------------------------------------------------------------

const specsOf = (data) => ctx.buildQuantChartSpecs(data);
const byId = (specs, id) => specs.find((s) => s.id === id);
function allTraces(specs) {
  const out = [];
  for (const s of specs) if (s.figure) for (const t of s.figure.data) out.push(t);
  return out;
}
function assertSpecInvariants(specs, label) {
  for (const s of specs) {
    assert.strictEqual(s.templateName, "aimlds_ink_brass", `${label}: ${s.id} template name`);
    assert.ok(s.viewName && s.viewName.length > 0, `${label}: ${s.id} carries a named default view`);
    if (!s.figure) continue;
    // ONE template object, shared by every figure (PLAYBOOK 36).
    assert.strictEqual(s.figure.layout.template, ctx.AIMLDS_INK_BRASS_TEMPLATE, `${label}: ${s.id} template object`);
    // No error bands / intervals anywhere — the payload carries no error
    // ranges, so drawing one would be fabrication (PLAYBOOK 34).
    assert.ok(!JSON.stringify(s.figure).includes('"error_y"'), `${label}: ${s.id} invents no error bars`);
    assert.ok(!JSON.stringify(s.figure).includes('"error_x"'), `${label}: ${s.id} invents no error bars`);
    for (const tr of s.figure.data) {
      // SVG only (PLAYBOOK 35) and no gauge dials (spec §3.3).
      assert.ok(["scatter", "bar", "waterfall", "heatmap"].includes(tr.type), `${label}: ${s.id} trace type ${tr.type}`);
      if (tr.type === "scatter") {
        assert.strictEqual(tr.connectgaps, false, `${label}: ${s.id} scatter connectgaps false (PLAYBOOK 33)`);
      }
    }
  }
  // rangebreaks banned anywhere in any spec (PLAYBOOK 33).
  assert.ok(!JSON.stringify(specs).includes("rangebreaks"), `${label}: no rangebreaks key`);
}

// --- FULL fixture -----------------------------------------------------------

{
  const specs = specsOf(FULL);
  assertSpecInvariants(specs, "FULL");

  const trends = byId(specs, "trends");
  assert.ok(trends.figure, "FULL: trends figure built");
  assert.strictEqual(trends.figure.layout.hovermode, "x unified", "FULL: trends unified hover (32)");
  assert.strictEqual(trends.figure.layout.xaxis.showspikes, true, "FULL: trends spikelines on");
  const gross = trends.figure.data.find((t) => t.name === "Gross margin");
  assert.deepStrictEqual([...gross.y], [0.40, 0.42]);
  assert.ok(gross.hovertemplate.includes("%{customdata[2]}"), "FULL: hover carries provenance slot");
  assert.strictEqual(gross.customdata[0][2], "Fixture Statements (test)", "FULL: statement provenance from payload");
  const yoy = trends.figure.data.find((t) => t.name === "YoY revenue growth");
  assert.strictEqual(yoy.y[0], null, "FULL: YoY element 0 stays null");

  const dupont = byId(specs, "dupont");
  assert.ok(dupont.figure, "FULL: dupont figure built");
  assert.strictEqual(dupont.figure.layout.hovermode, "x unified", "FULL: dupont unified hover");

  const wf = byId(specs, "dupont-waterfall");
  assert.ok(wf.figure, "FULL: waterfall built");
  const wt = wf.figure.data[0];
  assert.deepStrictEqual([...wt.measure], ["absolute", "relative", "relative", "relative", "total"]);
  const sum = wt.y[0] + wt.y[1] + wt.y[2] + wt.y[3];
  assert.ok(Math.abs(sum - wt.y[4]) < 1e-9, `FULL: waterfall measures sum to total (${sum} vs ${wt.y[4]})`);

  const fx = byId(specs, "forensics");
  assert.ok(fx.figure, "FULL: forensics figure built");
  assert.strictEqual(fx.figure.data.length, 4, "FULL: four screen rows");
  const shapes = fx.figure.layout.shapes;
  assert.ok(shapes.some((sh) => sh.type === "line" && sh.x0 === -1.78), "FULL: Beneish flag line at −1.78");
  const anns = fx.figure.layout.annotations.map((a) => a.text);
  assert.ok(anns.includes("distress < 1.81") && anns.includes("grey 1.81–2.99") && anns.includes("safe > 2.99"), "FULL: Altman zones labelled");
  assert.ok(anns.includes("flag threshold (M > −1.78)"), "FULL: Beneish threshold labelled");
  assert.ok(anns.includes("cash = earnings"), "FULL: cash-conversion reference labelled");

  const hm = byId(specs, "valuation");
  assert.ok(hm.figure, "FULL: heatmap built");
  const ht = hm.figure.data[0];
  assert.strictEqual(ht.type, "heatmap");
  assert.strictEqual(ht.z[2][2], null, "FULL: unevaluable cell stays null, never interpolated");
  assert.strictEqual(ht.text[2][2], "n/a", "FULL: unevaluable cell prints n/a");
  assert.ok(hm.figure.layout.shapes.some((sh) => sh.type === "rect"), "FULL: base cell outlined");
  assert.ok(hm.figure.layout.annotations.some((a) => a.text === "assumption used"), "FULL: base cell labelled");
  assert.ok(hm.caption.includes("not observed market data"), "FULL: heatmap caption states model output");
  assert.ok(hm.caption.includes("Discount rate r = 9.00%"), "FULL: payload assumption rendered under the figure");

  const ev = byId(specs, "expected");
  assert.ok(ev.figure, "FULL: contributions figure built (§10 resolution — no fabricated tornado)");
  assert.deepStrictEqual([...ev.figure.data[0].x].sort((a, b) => a - b), [-2.5, 12.5]);
  assert.strictEqual(ev.figure.layout.shapes[0].x0, 10.0, "FULL: expected value marked");

  const alloc = byId(specs, "allocation");
  assert.ok(alloc.figure, "FULL: allocation figure built from non-null fields only");
  assert.strictEqual(alloc.figure.data[0].y.length, 4, "FULL: 4 non-null allocation ratios charted");
}

// --- NULL_HEAVY fixture -----------------------------------------------------

{
  const specs = specsOf(NULL_HEAVY);
  assertSpecInvariants(specs, "NULL_HEAVY");
  assert.strictEqual(byId(specs, "trends").figure, null);
  assert.ok(byId(specs, "valuation").note.includes("Sensitivity grid unavailable"), "NULL: heatmap panel-missing note");
  assert.strictEqual(byId(specs, "forensics").figure, null, "NULL: no forensics figure from all-null screens");
  assert.ok(byId(specs, "forensics").note.includes("Forensic screens unavailable"));
  assert.strictEqual(byId(specs, "dupont").figure, null, "NULL: no dupont figure without rows");
  assert.strictEqual(byId(specs, "dupont-waterfall").figure, null, "NULL: no waterfall without attribution");
  assert.strictEqual(byId(specs, "expected").figure, null, "NULL: no EV figure when expected is null — reason line stands");
  assert.strictEqual(byId(specs, "allocation").figure, null, "NULL: no allocation figure when every ratio is null");
}

// --- GAP fixture: mid-series nulls survive ----------------------------------

{
  const specs = specsOf(GAP);
  assertSpecInvariants(specs, "GAP");
  const gross = byId(specs, "trends").figure.data.find((t) => t.name === "Gross margin");
  assert.strictEqual(gross.y[1], null, "GAP: mid-series null survives as null");
  assert.ok(!gross.y.includes(0), "GAP: null never becomes 0");
  const net = byId(specs, "trends").figure.data.find((t) => t.name === "Net margin");
  assert.strictEqual(net.y[2], null, "GAP: trailing null survives");
}

// --- view line (PLAYBOOK 31) -------------------------------------------------

{
  const spec = byId(specsOf(FULL), "trends");
  assert.strictEqual(ctx.quantViewLine(spec, { data: [], layout: {} }), "Default view: " + spec.viewName);
  const changed = ctx.quantViewLine(spec, {
    data: [{ name: "Net margin", visible: "legendonly" }, { name: "Gross margin", visible: true }],
    layout: { xaxis: { range: [0.5, 1.5] } },
  });
  assert.ok(changed.includes("hidden: Net margin"), "view line names hidden series");
  assert.ok(changed.includes("window FY2024 – FY2024"), "view line names the zoom window");
  assert.ok(changed.includes("(default: " + spec.viewName + ")"), "view line keeps the default named");
}

// --- render integration: tables intact, vendor-failed named ------------------

{
  ctx.renderQuantData(FULL);
  const html = els["report-content"].innerHTML;
  for (const id of ["qchart-trends", "qchart-dupont", "qchart-dupont-waterfall", "qchart-forensics", "qchart-valuation", "qchart-allocation", "qchart-expected"]) {
    assert.ok(html.includes(`id="${id}"`), `render: panel scaffold ${id} present`);
    assert.ok(html.includes(`id="${id}-view"`), `render: view line ${id} present`);
  }
  assert.ok(html.includes("Revenue CAGR"), "render: trends table intact");
  assert.ok(html.includes("Not available: interest coverage"), "render: null allocation fields listed, not dropped");
  assert.ok(html.includes("Altman input missing") === false, "render: no chips when nothing is missing");
  // The shim has no Plotly: vendor-failed state — figure divs hidden, the
  // one-line note shown, tables untouched.
  assert.strictEqual(els["qchart-vendor-note"].textContent, "Charts unavailable — data tables below are complete.");
  assert.strictEqual(els["qchart-vendor-note"].hidden, false);
  assert.strictEqual(els["qchart-trends"].hidden, true);

  ctx.renderQuantData(NULL_HEAVY);
  const nhtml = els["report-content"].innerHTML;
  assert.ok(nhtml.includes("Altman input missing: x5_market_value_of_equity"), "render: missing-component chips visible");
  assert.ok(nhtml.includes("Beneish input missing: receivables"), "render: Beneish chips visible");
  assert.ok(nhtml.includes("Expected value: no scenarios provided"), "render: EV reason line stands when expected is null");
  assert.strictEqual(els["qchart-valuation-note"].textContent.includes("Sensitivity grid unavailable"), true, "render: panel-missing note written");
}

console.log("quant_charts.test.mjs: all Phase 1 spec assertions passed");
