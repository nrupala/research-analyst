<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# research-analyst-api — Cloudflare Worker (source of record)

The edge proxy serving `ra.devinfo.dev/api/*` (devinfo.dev zone). This
directory is the source of record for the deployed worker: what is in
`src/index.js` here is what runs live (reconciled 2026-10-15, release-gate
finding M2).

## What it does
Thin edge proxy. `/api/*` requests are forwarded to the OCI origin
`https://ra-origin.nrupalakolkar.com`. The backend's status passes through
untouched — including its 401 auth verdicts — and a
`502 backend_unreachable` is returned if the origin fetch throws.

- **Single backend. No fallback. No timeout.** (If the origin is down,
  users get a 502.)
- **Rollback lever:** redeploy the previous module through the signed
  wrapper (the pre-M2 module is preserved in this repo's git history and
  in the 2026-10-15 release-gate pack). The Fly.io backend is retired and
  is not a rollback target.

## CORS — no wildcard
An `Origin` is reflected in `Access-Control-Allow-Origin` only when it
appears in the `ALLOWED_ORIGINS` worker var (comma-separated). When the
var is unset — as in production today — the defaults apply:
`https://ra.aimlds.org,https://ra.devinfo.dev,https://aimlds.org,https://devinfo.dev`.
Responses carry `Vary: Origin`, and preflight allows the `X-RA-Key`
header the API-key flow needs. An unlisted origin receives no
`Access-Control-Allow-Origin` header at all.

## Bindings
- `AI` (Workers AI) is declared in `wrangler.toml` and present in the
  live settings, but the fetch handler never calls it — a leftover from
  an earlier edge-LLM design, kept for parity with the live settings.
  The July worker's dead prompt code (`SYSTEM_PROMPT`, `buildPrompt`)
  was dropped from this source in the gated rewrite.
- `ALLOWED_ORIGINS` (plain text, optional) overrides the CORS defaults;
  it is not set in production.

## Deploy — signed wrapper only
Manual deploys go through `deploy/deploy-workers-signed.py
research-analyst-api`, which uploads via the site-integrity signed
wrapper (bindings carried forward, server-side secrets preserved, deployed
bytes re-hashed, ledger certificate minted). Running it is a production
deploy: **only with the owner's explicit go-ahead.** Do not wire CI to
deploy this worker.

Post-deploy checks (from the reconciliation checklist):
- `name = research-analyst-api`, the `AI` binding, and the
  `ra.devinfo.dev/api/*` route are unchanged.
- `ra.devinfo.dev/api/health` still serves the OCI origin
  (`cf-ray` + `server: cloudflare` present, `fly-request-id` absent).
- CORS probes: an allowlisted origin is reflected; an unlisted origin
  receives no `Access-Control-Allow-Origin`.

## Provenance / drift
Until 2026-10-15 the live worker was the 2026-07-22 Cloudflare-dashboard
deploy (wildcard CORS, dead prompt code) and this directory described
itself as a mirror of it. The gated source had been written to this repo
but never deployed; gate finding M2 carried the drift, and the owner's
go-ahead closed it. The separate `workers/api-proxy/` dir is a *different*,
more elaborate (env-driven, primary/fallback/timeout) proxy design that is
**not deployed**.
