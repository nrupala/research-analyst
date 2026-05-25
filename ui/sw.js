/**
 * Research Analyst - Service Worker v0.1.0
 * Module: ui/sw.js | Version: 0.1.0 | Updated: 2026-05-15
 *
 * Strategies:
 *   - Static assets: cache-first (app shell)
 *   - CDN assets: cache-first with network update (stale-while-revalidate)
 *   - API /api/research: network-first with offline fallback from cache
 *   - API /api/health: network-only
 *
 * Security:
 *   - Only caches same-origin + whitelisted CDN hosts
 *   - Research data cached per-ticker with 1-hour TTL
 *   - Cache versioned; stale caches purged on update
 *   - Max cache size enforced (50 research entries)
 */

"use strict";

const CACHE_VERSION = "ra-v1";
const STATIC_CACHE = CACHE_VERSION + "-static";
const DATA_CACHE = CACHE_VERSION + "-data";
const CDN_CACHE = CACHE_VERSION + "-cdn";

const DATA_CACHE_MAX_ENTRIES = 50;
const DATA_CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour

const PRECACHE_URLS = [
    "/",
    "/static/style.css",
    "/static/app.js",
    "/static/worker.js",
    "/manifest.json",
    "/static/icons/icon-192x192.png",
    "/static/icons/icon-512x512.png",
    "/static/icons/favicon-32x32.png",
];

const CDN_WHITELIST = [
    "cdn.plot.ly",
    "cdn.jsdelivr.net",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
];

// ============================================================
// Install - pre-cache app shell
// ============================================================

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => cache.addAll(PRECACHE_URLS))
            .then(() => self.skipWaiting())
    );
});

// ============================================================
// Activate - purge old caches
// ============================================================

self.addEventListener("activate", (event) => {
    const keepCaches = new Set([STATIC_CACHE, DATA_CACHE, CDN_CACHE]);
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => \!keepCaches.has(key))
                    .map((key) => caches.delete(key))
            )
        ).then(() => self.clients.claim())
    );
});

// ============================================================
// Fetch - routing by request type
// ============================================================

self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);

    // --- API: research endpoint (network-first with data cache fallback) ---
    if (url.pathname === "/api/research" && event.request.method === "POST") {
        event.respondWith(networkFirstWithDataCache(event.request));
        return;
    }

    // --- API: other endpoints (network-only) ---
    if (url.pathname.startsWith("/api/")) {
        event.respondWith(
            fetch(event.request).catch(() =>
                new Response(
                    JSON.stringify({ error: "offline", detail: "Network unavailable." }),
                    { status: 503, headers: { "Content-Type": "application/json" } }
                )
            )
        );
        return;
    }

    // --- CDN assets: stale-while-revalidate ---
    const isCDN = CDN_WHITELIST.some((host) => url.hostname === host);
    if (isCDN) {
        event.respondWith(staleWhileRevalidate(event.request, CDN_CACHE));
        return;
    }

    // --- Same-origin static assets: cache-first ---
    if (url.origin === self.location.origin) {
        event.respondWith(cacheFirst(event.request, STATIC_CACHE));
        return;
    }

    // --- Everything else: network only ---
    event.respondWith(fetch(event.request));
});

// ============================================================
// Cache Strategies
// ============================================================

/**
 * Cache-first: serve from cache, fall back to network.
 * On network success, update the cache for next time.
 */
async function cacheFirst(request, cacheName) {
    const cached = await caches.match(request);
    if (cached) return cached;

    try {
        const response = await fetch(request);
        if (response.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, response.clone());
        }
        return response;
    } catch (err) {
        // Offline and not in cache
        return new Response("Offline", { status: 503 });
    }
}

/**
 * Stale-while-revalidate: serve cached immediately,
 * fetch fresh in background to update cache.
 */
async function staleWhileRevalidate(request, cacheName) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request);

    const networkPromise = fetch(request).then((response) => {
        if (response.ok) {
            cache.put(request, response.clone());
        }
        return response;
    }).catch(() => null);

    return cached || (await networkPromise) || new Response("Offline", { status: 503 });
}

/**
 * Network-first with data cache: try network, cache successful responses,
 * fall back to cached data if offline.
 *
 * Caches POST responses by generating a cache key from the request body.
 * Enforces max entries and TTL to prevent unbounded growth.
 */
async function networkFirstWithDataCache(request) {
    const cache = await caches.open(DATA_CACHE);

    // Generate cache key from request body
    const body = await request.clone().text();
    let cacheKey;
    try {
        const parsed = JSON.parse(body);
        // Key by ticker + report_type + timeframe
        cacheKey = new Request(
            "/api/research?k=" +
            encodeURIComponent((parsed.ticker || "") + "|" + (parsed.report_type || "") + "|" + (parsed.timeframe || ""))
        );
    } catch (e) {
        cacheKey = request;
    }

    try {
        const response = await fetch(request);

        if (response.ok) {
            // Clone and add timestamp header for TTL tracking
            const responseToCache = response.clone();
            const headers = new Headers(responseToCache.headers);
            headers.set("x-ra-cached-at", Date.now().toString());

            const cachedResponse = new Response(await responseToCache.blob(), {
                status: responseToCache.status,
                statusText: responseToCache.statusText,
                headers: headers,
            });

            await cache.put(cacheKey, cachedResponse);
            await enforceMaxEntries(cache, DATA_CACHE_MAX_ENTRIES);
        }

        return response;

    } catch (err) {
        // Offline - try cache
        const cached = await cache.match(cacheKey);
        if (cached) {
            // Check TTL
            const cachedAt = parseInt(cached.headers.get("x-ra-cached-at") || "0", 10);
            if (Date.now() - cachedAt < DATA_CACHE_TTL_MS) {
                return cached;
            }
            // Expired but return anyway with warning header
            const headers = new Headers(cached.headers);
            headers.set("x-ra-stale", "true");
            return new Response(cached.body, {
                status: cached.status,
                statusText: cached.statusText,
                headers: headers,
            });
        }

        return new Response(
            JSON.stringify({
                error: "offline",
                detail: "Network unavailable and no cached data for this ticker.",
            }),
            { status: 503, headers: { "Content-Type": "application/json" } }
        );
    }
}

/**
 * Enforce maximum cache entries (LRU eviction by insertion order).
 * Cache API doesn't expose timestamps, so we evict oldest keys first.
 */
async function enforceMaxEntries(cache, maxEntries) {
    const keys = await cache.keys();
    if (keys.length > maxEntries) {
        const toDelete = keys.length - maxEntries;
        for (let i = 0; i < toDelete; i++) {
            await cache.delete(keys[i]);
        }
    }
}
