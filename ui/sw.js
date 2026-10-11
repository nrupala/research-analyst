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

"use strict";

// Research Analyst - Service Worker v0.4.0

var CACHE_VERSION = "ra-v0.4.0";
var STATIC_CACHE = CACHE_VERSION + "-static";
var DATA_CACHE = CACHE_VERSION + "-data";
var CDN_CACHE = CACHE_VERSION + "-cdn";
var DATA_MAX = 50;
var DATA_TTL = 3600000;

var PRECACHE = [
    "/",
    "/style.css",
    "/app.js",
    "/worker.js",
    "/manifest.json",
    "/icons/icon-192x192.png",
    "/icons/icon-512x512.png",
    "/icons/favicon-32x32.png"
];

var CDN_HOSTS = ["cdn.plot.ly", "cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com"];

self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(function (cache) { return cache.addAll(PRECACHE); })
            .then(function () { return self.skipWaiting(); })
    );
});

self.addEventListener("activate", function (event) {
    var keep = [STATIC_CACHE, DATA_CACHE, CDN_CACHE];
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(keys.filter(function (k) { return keep.indexOf(k) === -1; }).map(function (k) { return caches.delete(k); }));
        }).then(function () { return self.clients.claim(); })
    );
});

self.addEventListener("fetch", function (event) {
    var url = new URL(event.request.url);

    if (url.pathname === "/api/research" && event.request.method === "POST") {
        event.respondWith(networkFirstData(event.request));
        return;
    }
    if (url.pathname.indexOf("/api/") === 0) {
        event.respondWith(fetch(event.request).catch(function () {
            return new Response(JSON.stringify({ error: "offline" }), { status: 503, headers: { "Content-Type": "application/json" } });
        }));
        return;
    }
    var isCDN = CDN_HOSTS.some(function (h) { return url.hostname === h; });
    if (isCDN) {
        event.respondWith(staleRevalidate(event.request, CDN_CACHE));
        return;
    }
    if (url.origin === self.location.origin) {
        event.respondWith(cacheFirst(event.request, STATIC_CACHE));
        return;
    }
    event.respondWith(fetch(event.request));
});

function cacheFirst(req, name) {
    return caches.match(req).then(function (cached) {
        if (cached) return cached;
        return fetch(req).then(function (resp) {
            if (resp.ok) { caches.open(name).then(function (c) { c.put(req, resp.clone()); }); }
            return resp;
        }).catch(function () { return new Response("Offline", { status: 503 }); });
    });
}

function staleRevalidate(req, name) {
    return caches.open(name).then(function (cache) {
        return cache.match(req).then(function (cached) {
            var net = fetch(req).then(function (resp) {
                if (resp.ok) cache.put(req, resp.clone());
                return resp;
            }).catch(function () { return null; });
            return cached || net.then(function (r) { return r || new Response("Offline", { status: 503 }); });
        });
    });
}

function networkFirstData(req) {
    return caches.open(DATA_CACHE).then(function (cache) {
        return req.clone().text().then(function (body) {
            var key;
            try {
                var p = JSON.parse(body);
                key = new Request("/api/research?k=" + encodeURIComponent((p.ticker || "") + "|" + (p.report_type || "") + "|" + (p.timeframe || "")));
            } catch (e) { key = req; }

            return fetch(req).then(function (resp) {
                if (resp.ok) {
                    resp.clone().blob().then(function (blob) {
                        var h = new Headers(resp.headers);
                        h.set("x-ra-ts", String(Date.now()));
                        cache.put(key, new Response(blob, { status: resp.status, headers: h }));
                        cache.keys().then(function (ks) {
                            if (ks.length > DATA_MAX) {
                                for (var i = 0; i < ks.length - DATA_MAX; i++) cache.delete(ks[i]);
                            }
                        });
                    });
                }
                return resp;
            }).catch(function () {
                return cache.match(key).then(function (c) {
                    if (c) return c;
                    return new Response(JSON.stringify({ error: "offline", detail: "No cached data for this ticker." }), { status: 503, headers: { "Content-Type": "application/json" } });
                });
            });
        });
    });
}
