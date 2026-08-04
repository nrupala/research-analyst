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
sudo -u ra git pull --ff-only
sudo -u ra .venv/bin/pip install .
sudo systemctl restart ra
```

## Verify

```bash
# direct origin (OCI):
curl -s https://ra-origin.nrupalakolkar.com/api/health          # -> {"status":"ok",...,"version":"0.2.1"}

# which backend is serving the public route? (header signature)
curl -sI https://ra.devinfo.dev/api/health | grep -iE 'fly-request-id|via|server|cf-ray'
#   has  fly-request-id / via: fly.io   => served by FLY
#   only cf-ray + server: cloudflare    => served by OCI
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
