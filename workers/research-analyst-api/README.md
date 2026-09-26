<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# research-analyst-api — live Worker mirror (backup)

Faithful snapshot of the **deployed** Cloudflare Worker serving `ra.devinfo.dev/api/*`
(devinfo.dev zone). Captured **2026-07-22** via `GET /accounts/{acc}/workers/scripts/{name}`
(the `/content` download endpoint is blocked for the API token — `10405` — but the script
GET returns the source in a multipart body).

## What it does
Thin edge proxy. `/api/*` requests are forwarded to the OCI origin
`https://ra-origin.nrupalakolkar.com`, `Access-Control-Allow-Origin: *` is set on the
response, and a `502 backend_unreachable` is returned if the origin fetch throws.

- **Single backend. No fallback. No timeout.** (If the origin is down, users get a 502 —
  rollback is manual: point `backend` back at Fly.)
- **Rollback lever:** change the `backend` constant in `src/index.js` back to
  `https://research-analyst.fly.dev` and redeploy.

## Dead code (mirrored intentionally)
`SYSTEM_PROMPT`, `json()`, `buildPrompt()`, and the `AI` binding are defined but **never
called** by the `fetch` handler — vestigial from an earlier edge-LLM design. Kept here so
this is an exact mirror; safe to delete in a future cleanup.

## Provenance / drift
Last deployed from the **Cloudflare dashboard quick-editor** (not from this repo). This dir
mirrors what is actually live. The separate `workers/api-proxy/` dir is a *different*,
more elaborate (env-driven, primary/fallback/timeout) proxy design that is **not deployed**.

## Do NOT auto-deploy without reconciliation
The GitHub auto-deploy link was intentionally removed. Before ever wiring CI to deploy this:
verify `name = research-analyst-api`, the `AI` binding, and the `ra.devinfo.dev/api/*` route;
do one **manual** test deploy; then confirm `ra.devinfo.dev/api/health` still serves OCI
(header check: `fly-request-id` absent, `cf-ray` + `server: cloudflare` present).
