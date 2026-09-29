<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Research Analyst — OCI-Native Sovereign Origin (reloadable image)

This directory is the **reloadable image** of the Research Analyst (RA) backend running natively on
the **oracle-aetheris** OCI box. It replaces the old paid **Fly** origin. No Docker (the legacy
`deploy/oci/setup.sh` Docker path is superseded and should not be used).

Files:
- `ra.service` — systemd unit (uvicorn, localhost:8700, user `ra`, resource caps + hardening)
- `ra.env.example` — env template (FRED key **redacted** — set on box only)
- `bootstrap.sh` — one-shot recreate script (user + clone + venv + install + env + service)

## Architecture

```
Browser
  -> Cloudflare Pages           ra.devinfo.dev              (static UI, unchanged)
  -> /api/*  Worker             research-analyst-api        (Cloudflare edge proxy, failover)
        PRIMARY   -> https://ra-origin.nrupalakolkar.com    (this box, via Cloudflare Tunnel)
        FALLBACK  -> https://research-analyst.onrender.com  (Render free tier)
```

- **Box:** oracle-aetheris (24 GB / 4 OCPU), Python 3.12.3.
- **Service:** `ra.service` -> `uvicorn research_analyst.server:app` on `127.0.0.1:8700` (localhost-only).
- **App:** `/opt/research-analyst` (git checkout, `main`). **Env:** `/etc/research-analyst/ra.env`
  (root:ra, 640). **Cache:** `/var/lib/research-analyst/cache`.
- RA co-locates with Ollama/OPA/Chroma, so the unit hard-caps it: `MemoryMax=4G`, `MemoryHigh=3G`,
  `CPUQuota=200%` (up to 2 of 4 cores), `OOMPolicy=stop`.

## Cloudflare Tunnel (dashboard-managed — no local config.yml)

- Tunnel: **`llmvm-tunnel`**, id **`c12afde0-a01d-485d-aed6-3dddb3282069`** (the box's primary tunnel;
  also fronts dev/ai/rag/agents/oracle/git/ci + the apex).
- Public Hostname: **`ra-origin.nrupalakolkar.com`** -> service `HTTP` `localhost:8700`.
  Add/edit under **Zero Trust -> Networks -> Tunnels -> llmvm-tunnel -> Public Hostnames**.
- cloudflared runs on the **host**, so `localhost:8700` reaches uvicorn directly and **bypasses** the
  Docker nginx (`llmvm_nginx`) that fronts the other nrupalakolkar.com vhosts.
- `ra-origin` is a **backend-only** hostname — the customer never sees it (they use ra.devinfo.dev).

## Recreate the box from scratch

```bash
# on oracle-aetheris, as a sudo user:
git clone https://github.com/nrupala/research-analyst.git /tmp/ra-src   # or use the /opt clone
cd /tmp/ra-src/deploy/oci-native && sudo bash bootstrap.sh
# then set the FRED key:
sudoedit /etc/research-analyst/ra.env      # RA_MARKET_FRED_API_KEY=<real 32-char key>
sudo systemctl restart ra
```
Then re-add the `ra-origin.nrupalakolkar.com` Public Hostname in Zero Trust (above).

## Update (routine deploy)

```bash
cd /opt/research-analyst
sudo -u ra git fetch origin && sudo -u ra git checkout main && sudo -u ra git pull --ff-only origin main
sudo -u ra git rev-parse HEAD          # <- ALWAYS assert this equals the commit you intend to ship
sudo -u ra .venv/bin/pip install --no-deps .
sudo systemctl restart ra
```

Run Git and pip as `ra`; `systemctl restart` needs root even when the rest runs as `ra`.

### Why `--no-deps`, and what actually fails if you skip it

`--no-deps` keeps the install from re-resolving the dependency set against the index (use
`pip install .` only when deliberately changing dependencies). It is *not* the load-bearing step
for serving, and the commonly-repeated "skip it and the box silently no-ops" claim is **wrong for
this deployment**:

`ra.service` sets `WorkingDirectory=/opt/research-analyst`, so `sys.path[0]` is the repo root and
uvicorn imports the **repo source tree** (`/opt/research-analyst/research_analyst/`), which
shadows the venv's `site-packages` copy. The pull alone therefore serves the new code. The install
is kept as insurance so the installed copy cannot drift from the checkout.

Verify which copy is actually loaded rather than assuming:

```bash
SP=$(cd / && /opt/research-analyst/.venv/bin/python -c \
  "import research_analyst,os;print(os.path.dirname(research_analyst.__file__))")
echo "$SP"                    # -> .../.venv/lib/python3.12/site-packages/research_analyst
ls -1 "$SP" | head
```

Run that from `/`, not from the repo root — from the repo root `import` resolves to the source tree
and will misleadingly print `/opt/research-analyst/research_analyst`.

## Verify

```bash
# direct origin (OCI):
curl -s https://ra-origin.nrupalakolkar.com/api/health
#   -> {"status":"ok","version":"0.4.0","service":"research-analyst","commit":"<sha>"}

# deploy marker: version stays 0.4.0 across deploys, so `commit` is the exact-build
# signal. The served commit must equal the box's git HEAD.
curl -s https://ra-origin.nrupalakolkar.com/api/health | grep -o '"commit":"[^"]*"'
sudo -u ra git -C /opt/research-analyst rev-parse --short HEAD      # <- must match

# which backend is serving the public route? (header signature)
# NOTE: use a GET. `curl -sI` sends HEAD, which this API rejects with 405, so the
# check silently reports nothing useful. -D - dumps response headers on the GET.
curl -s -D - -o /dev/null https://ra.devinfo.dev/api/health | grep -iE 'fly-request-id|^via|^server|cf-ray'
#   has  fly-request-id / via: fly.io   => served by FLY
#   only cf-ray + server: cloudflare    => served by OCI

# both public hostnames must be 200:
for d in ra.devinfo.dev ra.aimlds.org; do
  curl -s -o /dev/null -w "$d %{http_code}\n" "https://$d/api/health"
done

# service state:
systemctl is-active ra && systemctl show ra -p NRestarts --value   # want: active, 0
```

### Quant engine (shipped in #84, `6cff51aa`)

```bash
curl -s "http://127.0.0.1:8700/api/research/quant?ticker=AAPL" -o /tmp/q.json -w "HTTP %{http_code}\n"
/opt/research-analyst/.venv/bin/python -c "
import json; d=json.load(open('/tmp/q.json'))
print('schema  :', d['schema_version'])   # currently 1.0
print('ticker  :', d['ticker'], d['periods'])
print('missing :', len(d['missing_inputs']), 'inputs')
print('sections:', [k for k in ('trends','dupont','forensics','valuation','allocation','expected_value') if k in d])"
```

Expect **HTTP 200** (not 404) and **six** analytical sections — `trends`, `dupont`, `forensics`,
`valuation`, `allocation`, `expected_value`. Earlier runbook drafts said "five sections"; the engine
has six phases, so six is correct.

The response is `schema_version` **1.0** on this release train. On #84 (initial release) it
shipped **16 `missing_inputs`** and Forensics rendered hollow; the quant provider-wiring change
closed that: every engine input (interest/tax/SGA/D&A, EBIT, current assets/liabilities, retained
earnings, net PP&E, receivables, shares outstanding) is mapped through yfinance (primary) and SEC
companyfacts (fallback), and `price` is injected at the server boundary. `missing_inputs` now
lists only the keys genuinely absent for the ticker, one entry per key (e.g. `altman_z: price`).
For a large cap like AAPL expect the wired keys to be absent from the listing. Missing stays
missing - no value is fabricated - but the reason each remaining entry exists is now a real
upstream data gap, not a porting gap.

Frontend bundle must carry the quant tab:

```bash
curl -s http://127.0.0.1:8700/app.js | grep -c -i quant   # -> 37 on #84
```

FRED liveness: a report's macro table shows a specific **Inflation %** and **Economic Growth %**
(e.g. 3.7% / 2.1%) only when FRED is active. yfinance proxies (^TNX/^VIX) can supply interest rate +
VIX but never inflation/GDP — so those two cells are the FRED tell.

## Rollback (single lever)

Point the Worker primary back to Fly. Fly is kept warm through the ~5-day soak precisely for this.

## KNOWN GAP — Worker code drift (not yet captured here)

The live proxy Worker `research-analyst-api` (route `ra.devinfo.dev/api/*`, devinfo.dev zone) was
**last edited in the Cloudflare dashboard quick-editor**. Its code **hardcodes the Fly URL and does
not read `env` vars** (confirmed: setting `BACKEND_PRIMARY`/`FAILOVER_TIMEOUT` had no effect). The
deployed script body is **not readable via API token** (`10405 Method not allowed for this
authentication scheme`), so it is **not yet mirrored in this repo**.

To make repo == live (drift-cleanup slice):
1. Copy the live code from CF dashboard -> `workers/api-proxy/src/index.js`.
2. Refactor to env-driven (`env.BACKEND_PRIMARY || <default>`), matching the reference version already
   in `workers/api-proxy/`.
3. Fix `workers/api-proxy/wrangler.toml`: `name` is stale (`ra-api-proxy`) — set to
   `research-analyst-api`; add the `AI` binding the live worker carries; set
   `BACKEND_PRIMARY=https://ra-origin.nrupalakolkar.com`, `FAILOVER_TIMEOUT=60000`.
4. Deploy via `wrangler` so future cutovers are a one-line config change, not a dashboard code edit.
