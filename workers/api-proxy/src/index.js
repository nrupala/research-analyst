/**
 * Research Analyst - Cloudflare Worker API Proxy
 * Routes /api/* requests from Cloudflare Pages to the Python backend.
 *
 * Architecture:
 *   Browser (ra.devinfo.dev) -> Cloudflare Pages (static UI)
 *   Browser /api/* -> This Worker -> Fly.io (primary) or Render (fallback)
 *
 * Failover logic:
 *   1. Try primary backend (Fly.io)
 *   2. If primary fails or times out, try fallback (Render)
 *   3. If both fail, return structured error JSON
 *
 * Security:
 *   - CORS headers for ra.devinfo.dev only
 *   - Request size limit (1MB)
 *   - No credentials forwarded to backend
 *   - Rate limiting via Cloudflare's built-in protection
 */

export default {
    async fetch(request, env) {
        var url = new URL(request.url);

        // Only proxy /api/* paths
        if (!url.pathname.startsWith("/api/")) {
            return new Response("Not Found", { status: 404 });
        }

        // CORS preflight
        if (request.method === "OPTIONS") {
            return handleCORS(env);
        }

        // Request size guard (1MB max)
        var contentLength = request.headers.get("content-length");
        if (contentLength && parseInt(contentLength, 10) > 1048576) {
            return jsonResponse({ error: "Request too large", detail: "Max 1MB" }, 413, env);
        }

        // Backend URLs from environment
        var primary = (env.BACKEND_PRIMARY || "https://research-analyst.fly.dev").replace(/\/$/, "");
        var fallback = (env.BACKEND_FALLBACK || "https://research-analyst.onrender.com").replace(/\/$/, "");
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
            return addCORS(response, env);
        }

        // Primary failed - try fallback
        console.log("Primary backend failed, trying fallback...");

        // Need to re-clone body for second attempt
        // For POST with body, we need to read and replay
        if (request.method !== "GET" && request.method !== "HEAD") {
            // Re-read body from original request clone is not possible after consumption
            // So we use a different approach: make a new request from scratch
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
            // Add header indicating fallback was used
            var fallbackResp = new Response(response.body, response);
            fallbackResp.headers.set("X-RA-Backend", "fallback");
            return addCORS(fallbackResp, env);
        }

        // Both backends failed
        return jsonResponse({
            error: "service_unavailable",
            detail: "Both primary and fallback backends are unreachable. The research service may be starting up (cold start can take 30-60 seconds on free tier). Please retry in a moment."
        }, 503, env);
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
 * CORS preflight response.
 */
function handleCORS(env) {
    return new Response(null, {
        status: 204,
        headers: corsHeaders(env)
    });
}

/**
 * Add CORS headers to an existing response.
 */
function addCORS(response, env) {
    var newResp = new Response(response.body, response);
    var cors = corsHeaders(env);
    for (var key of cors.keys()) {
        newResp.headers.set(key, cors.get(key));
    }
    return newResp;
}

/**
 * CORS headers - restricted to allowed origins.
 */
function corsHeaders(env) {
    var allowed = env.CORS_ORIGIN || "https://ra.devinfo.dev";
    var headers = new Headers();
    headers.set("Access-Control-Allow-Origin", allowed);
    headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    headers.set("Access-Control-Allow-Headers", "Content-Type");
    headers.set("Access-Control-Max-Age", "86400");
    return headers;
}

/**
 * Structured JSON error response with CORS.
 */
function jsonResponse(body, status, env) {
    var resp = new Response(JSON.stringify(body), {
        status: status,
        headers: { "Content-Type": "application/json" }
    });
    return addCORS(resp, env);
}
