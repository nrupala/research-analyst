/**
 * Research Analyst - Cloudflare Worker API Proxy
 * Routes /api/* requests from Cloudflare Pages to the sovereign Python backend.
 *
 * Architecture:
 *   Browser (ra.devinfo.dev | ra.aimlds.org) -> Cloudflare Pages (static UI)
 *   Browser /api/* -> This Worker -> sovereign origin (ra-origin.nrupalakolkar.com)
 *
 * Failover logic:
 *   1. Try primary backend
 *   2. If primary fails or times out, try fallback
 *   3. If both fail, return structured error JSON
 *
 * Security:
 *   - CORS restricted to an allow-list of mirror origins (devinfo.dev + aimlds.org)
 *   - Request size limit (1MB)
 *   - Authorization / X-RA-Key forwarded to the origin (per-email API key
 *     entitlement; validated at the origin, never in the worker)
 *   - Rate limiting via Cloudflare's built-in protection
 */

const DEFAULT_ALLOWED_ORIGINS = "https://ra.devinfo.dev,https://ra.aimlds.org";

export default {
    async fetch(request, env) {
        var url = new URL(request.url);

        // Only proxy /api/* paths
        if (!url.pathname.startsWith("/api/")) {
            return new Response("Not Found", { status: 404 });
        }

        // CORS preflight
        if (request.method === "OPTIONS") {
            return handleCORS(request, env);
        }

        // Request size guard (1MB max)
        var contentLength = request.headers.get("content-length");
        if (contentLength && parseInt(contentLength, 10) > 1048576) {
            return jsonResponse({ error: "Request too large", detail: "Max 1MB" }, 413, request, env);
        }

        // Backend URLs from environment (sovereign origin by default)
        var primary = (env.BACKEND_PRIMARY || "https://ra-origin.nrupalakolkar.com").replace(/\/$/, "");
        var fallback = (env.BACKEND_FALLBACK || "https://ra-origin.nrupalakolkar.com").replace(/\/$/, "");
        var timeout = parseInt(env.FAILOVER_TIMEOUT || "10000", 10);

        // Build backend request
        var backendPath = url.pathname + url.search;
        var headers = new Headers(request.headers);
        headers.set("X-Forwarded-For", request.headers.get("CF-Connecting-IP") || "unknown");
        headers.set("X-Forwarded-Proto", "https");
        headers.delete("Host");

        var requestInit = {
            method: request.method,
            headers: headers,
            body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
        };

        // Try primary backend
        var response = await tryBackend(primary + backendPath, requestInit, timeout);

        if (response) {
            return addCORS(response, request, env);
        }

        // Primary failed - try fallback
        console.log("Primary backend failed, trying fallback...");

        if (request.method !== "GET" && request.method !== "HEAD") {
            var bodyText = null;
            try {
                var clonedReq = request.clone();
                bodyText = await clonedReq.text();
            } catch (e) {
                // Body already consumed; fallback without body
            }
            requestInit.body = bodyText;
        }

        response = await tryBackend(fallback + backendPath, requestInit, timeout);

        if (response) {
            var fallbackResp = new Response(response.body, response);
            fallbackResp.headers.set("X-RA-Backend", "fallback");
            return addCORS(fallbackResp, request, env);
        }

        // Both backends failed
        return jsonResponse({
            error: "service_unavailable",
            detail: "Both primary and fallback backends are unreachable. The research service may be starting up (cold start can take 30-60 seconds). Please retry in a moment."
        }, 503, request, env);
    }
};

/**
 * Try a backend with timeout. Returns Response or null on failure.
 */
async function tryBackend(url, init, timeoutMs) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, timeoutMs);

    try {
        var resp = await fetch(url, Object.assign({}, init, { signal: controller.signal }));
        clearTimeout(timer);
        return resp;
    } catch (err) {
        clearTimeout(timer);
        console.log("Backend request failed:", url, err.message || err);
        return null;
    }
}

/**
 * Resolve Access-Control-Allow-Origin by matching the request Origin against
 * the configured allow-list. Falls back to the first allowed origin.
 */
function resolveAllowedOrigin(request, env) {
    var allowList = (env.CORS_ORIGINS || DEFAULT_ALLOWED_ORIGINS)
        .split(",")
        .map(function (s) { return s.trim(); })
        .filter(Boolean);
    var origin = request.headers.get("Origin");
    if (origin && allowList.indexOf(origin) > -1) {
        return origin;
    }
    return allowList[0];
}

/**
 * CORS preflight response.
 */
function handleCORS(request, env) {
    return new Response(null, {
        status: 204,
        headers: corsHeaders(request, env)
    });
}

/**
 * Add CORS headers to an existing response.
 */
function addCORS(response, request, env) {
    var newResp = new Response(response.body, response);
    var cors = corsHeaders(request, env);
    for (var key of cors.keys()) {
        newResp.headers.set(key, cors.get(key));
    }
    return newResp;
}

/**
 * CORS headers - restricted to the mirror-origin allow-list.
 */
function corsHeaders(request, env) {
    var headers = new Headers();
    headers.set("Access-Control-Allow-Origin", resolveAllowedOrigin(request, env));
    headers.set("Vary", "Origin");
    headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    headers.set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-RA-Key");
    headers.set("Access-Control-Max-Age", "86400");
    return headers;
}

/**
 * Structured JSON error response with CORS.
 */
function jsonResponse(body, status, request, env) {
    var resp = new Response(JSON.stringify(body), {
        status: status,
        headers: { "Content-Type": "application/json" }
    });
    return addCORS(resp, request, env);
}
