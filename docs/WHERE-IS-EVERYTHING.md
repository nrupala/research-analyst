<!--
Copyright (C) 2026 2351485 ALBERTA INC. — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Research Analyst — Where Is Everything

_Last updated: 2026-08-04. Maintained by Milo. This is the RA-specific map. The portfolio-wide index for all repos lives in `nrupala/strategy-documents` → `docs/WHERE-IS-EVERYTHING.md`._

## Live app (public)
- Primary: https://ra.devinfo.dev
- Mirror:  https://ra.aimlds.org  — public, same infrastructure, no fork
- API health: `/api/health` → v0.2.1

Both hostnames call `/api/*` **same-origin**, so the mirror works without redeploying the prod worker (zero blast radius). The merged multi-origin CORS code only matters for cross-origin / API-key callers.

## Cloudflare (account `2edd59d09fd816187b47afbb9ea43af1`)
- **UI** — Pages project `research-analyst` (`research-analyst.pages.dev`), git-connected to `main`, auto-deploys on merge. Custom domains: `ra.devinfo.dev`, `ra.aimlds.org`.
- **API** — Worker `research-analyst-api` ( dashboard-managed; has AI binding, `nodejs_compat`, compat `2024-12-01`). Routes: `ra.devinfo.dev/api/*`, `ra.aimlds.org/api/*`.
- **DNS** — `ra.aimlds.org` → proxied CNAME → `research-analyst.pages.dev`.

## Origin (the Python backend)
- Box **oracle-aetheris**, systemd `ra.service` (user `ra`), `127.0.0.1:8700`, venv + uvicorn, at `/opt/research-analyst`.
- Fronted by Cloudflare Tunnel → `ra-origin.nrupalakolkar.com` (what the worker proxies to).

## Code (this repo — private, branch `main`, AGPL-3.0)
- App engines: `research_analyst/` (7 engines, `server.py`, `config.py`)
- Entitlements (shadow, `enforce=False`): `research_analyst/entitlements.py`, `tests/test_entitlements.py`
- Worker source: `workers/api-proxy/` (`wrangler.toml`, `src/index.js`)
- Docs: `docs/LAUNCH_VERIFICATION.md`, `PACKAGING.md`, `MONETIZATION.md`, `MIRROR-aimlds.md`, `BLOG_EXPLAINER_SERIES.md`

## PRs (all merged as of 2026-08-04)
`#7` bad-ticker fix · `#8` v0.2.1 coherence · `#9` launch/packaging/monetization docs · `#10` explainer series · `#11` distribution+entitlement+mirror docs · `#12` mirror worker wiring · `#13` entitlement core (shadow) · `#14` wrangler reconcile

## Known caveat — worker code parity is UNVERIFIED
The live `research-analyst-api` worker is dashboard-managed. Its **script body cannot be read or written via the Cloudflare API** on either MCP server — both the OAuth server and the API-token server return `10405: Method not allowed for this authentication scheme` on `/accounts/{acct}/workers/scripts/{name}/content`. (`/settings` reads fine via OAuth and confirms compat `2024-12-01` + `nodejs_compat`.) That endpoint is writable only via `wrangler` or the dashboard.

Consequence: repo `workers/api-proxy/src/index.js` is **config-reconciled but its code is not proven to match the live version**. Do NOT `wrangler deploy` over the live worker without first diffing — a deploy would overwrite the dashboard version (including the AI binding). Update the worker via the Cloudflare dashboard, or via `wrangler` only after confirming code parity by hand.

## Pending (box-dependent — Wed Aug 5, box was off-limits until then)
- Box redeploy: `cd /opt/research-analyst && sudo -u ra git pull && sudo -u ra .venv/bin/pip install . && sudo systemctl restart ra` — activates `#7` fix + `#12` CSP + `#13` shadow gate.
- `ci.yml` web-editor edits (drop the `deploy-fly` job; remove `|| true` so tests gate the pipeline) — the API token lacks `workflow` scope.
- `bee.devinfo.dev → bee.aimlds.org` and apex `devinfo.dev → aimlds.org` tunnel mirrors.
