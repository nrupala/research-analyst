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

// CORS: no wildcard. An Origin is reflected only when it appears in the
// ALLOWED_ORIGINS worker var (comma-separated); the production sites are
// the default. The proxy never invents an allow-origin the backend did
// not grant, and the backend's status (including its 401 auth verdicts)
// passes through untouched.
const DEFAULT_ALLOWED_ORIGINS = 'https://ra.aimlds.org,https://ra.devinfo.dev,https://aimlds.org,https://devinfo.dev';
function allowedOrigin(request, env) {
    var origin = request.headers.get('Origin') || '';
    var allowed = ((env && env.ALLOWED_ORIGINS) || DEFAULT_ALLOWED_ORIGINS).split(',').map(function (x) { return x.trim(); }).filter(Boolean);
    return origin && allowed.indexOf(origin) !== -1 ? origin : null;
}
function corsHeaders(request, env) {
    var h = { 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-RA-Key', 'Access-Control-Expose-Headers': 'X-Provider, X-Model', 'Vary': 'Origin' };
    var origin = allowedOrigin(request, env);
    if (origin) h['Access-Control-Allow-Origin'] = origin;
    return h;
}
function json(request, env, body, status=200, extra={}) { return new Response(JSON.stringify(body), { status, headers: {'Content-Type':'application/json', ...corsHeaders(request, env), ...extra} }); }

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
            var preflight = corsHeaders(request, env);
            preflight["Access-Control-Max-Age"] = "86400";
            return new Response(null, {
                status: 204,
                headers: preflight
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

            // Pass the backend response through untouched — status (a 401
            // stays a 401), body, and the backend's own CORS headers. Only
            // reflect an allowlisted Origin if the backend sent none.
            var newResp = new Response(resp.body, resp);
            var origin = allowedOrigin(request, env);
            if (origin && !newResp.headers.get("Access-Control-Allow-Origin")) {
                newResp.headers.set("Access-Control-Allow-Origin", origin);
                newResp.headers.set("Vary", "Origin");
            }
            return newResp;

        } catch (err) {
            var errHeaders = { "Content-Type": "application/json" };
            var errOrigin = allowedOrigin(request, env);
            if (errOrigin) errHeaders["Access-Control-Allow-Origin"] = errOrigin;
            return new Response(
                JSON.stringify({ error: "backend_unreachable", detail: err.message }),
                { status: 502, headers: errHeaders }
            );
        }
    }
};
