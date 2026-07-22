const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type, Authorization', 'Access-Control-Expose-Headers': 'X-Provider, X-Model' };
function json(body, status=200, extra={}) { return new Response(JSON.stringify(body), { status, headers: {'Content-Type':'application/json', ...CORS, ...extra} }); }

const SYSTEM_PROMPT = `You are Research Analyst, an institutional-grade equity and ETF research agent.

Generate a structured research report following this methodology:

## 1. Executive Summary
Key thesis, variant perception, risk/reward framing.

## 2. Fundamental Analysis
Revenue, margins, balance sheet, earnings quality, capital allocation.

## 3. Technical Analysis
Price action, momentum, support/resistance, trend.

## 4. Macro Context
Economic regime, sector sensitivity, rates, geopolitical.

## 5. Competitive Positioning
Moat, peers, market share, disruption risk.

## 6. Valuation & Scenarios
Bull/Base/Bear with explicit assumptions and targets.

## 7. Risk Assessment
Table: Risk | Probability | Impact | Timing

RULES:
- Trace conclusions to assumptions
- Missing data: state "assumption used: ..."
- NO recommendations - use "favors" / "disfavors"
- Use markdown tables and bullets
- Be concise: 800-1200 words
- End with disclaimer
`;

function buildPrompt(ticker, reportType, timeframe) {
  let t = 'COMPREHENSIVE';
  if (reportType === 'long_term') t = 'LONG-TERM (business model, moat, multi-year)';
  else if (reportType === 'tactical') t = 'TACTICAL (technical setup, catalysts, near-term)';
  return t + ' report for ' + ticker + '. Timeframe: ' + timeframe + '. Use training knowledge. State assumptions if real-time data unavailable.';
}
export default {
    async fetch(request, env) {
        var url = new URL(request.url);

        if (!url.pathname.startsWith("/api/")) {
            return new Response("Not Found", { status: 404 });
        }

        if (request.method === "OPTIONS") {
            return new Response(null, {
                status: 204,
                headers: {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Max-Age": "86400"
                }
            });
        }

        var backend = "https://ra-origin.nrupalakolkar.com";
        var backendUrl = backend + url.pathname + url.search;

        var headers = new Headers(request.headers);
        headers.delete("Host");

        try {
            var resp = await fetch(backendUrl, {
                method: request.method,
                headers: headers,
                body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined
            });

            var newResp = new Response(resp.body, resp);
            newResp.headers.set("Access-Control-Allow-Origin", "*");
            return newResp;

        } catch (err) {
            return new Response(
                JSON.stringify({ error: "backend_unreachable", detail: err.message }),
                { status: 502, headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } }
            );
        }
    }
};
