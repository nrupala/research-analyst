# Research Analyst — Deployment & Serving Topology

Build-history record for how `ra.devinfo.dev` is served. Update this file whenever the
serving path, host, or ingress changes.

## Serving path

```
User ──> ra.devinfo.dev (Cloudflare Pages, UI/PWA)
             └─ /api/*  ──> Worker `ra-api-proxy` (thin proxy, no data logic; 10s failover)
                              ├─ PRIMARY   : <see below>
                              └─ FALLBACK  : Render (research-analyst-*.onrender.com, free)
```

### History of the primary backend
| Date | Primary | Notes |
| --- | --- | --- |
| — 2026-07 | Fly (`research-analyst.fly.dev`) | paid; built from a Dockerfile. Being retired. |
| 2026-07-21 → | **OCI native (in progress)** | Aetheris box, systemd + venv, no Docker. See below. |

## OCI-native origin (Slice 1, started 2026-07-21)

Migrating the primary off paid Fly onto the sovereign OCI ARM box ("Aetheris" / `oracle-aetheris`,
internal name `llmvm`). Fly is kept warm as an instant-rollback lever through a 5-day soak,
then retired. Render stays as the free fallback. **No Docker** (hard constraint).

- **Host:** Ampere ARM, 4 OCPU / 24 GB RAM, Ubuntu, Python 3.12.
- **Service:** systemd unit `ra.service` — venv + `uvicorn research_analyst.server:app`,
  bound to `127.0.0.1:8700`, non-root user `ra`.
  - Resource caps (RA must never starve co-tenant Ollama): `MemoryHigh=3G`, `MemoryMax=4G`, `CPUQuota=200%`.
  - Hardening: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`,
    `ReadWritePaths=/var/lib/research-analyst`.
- **Config/secrets:** `/etc/research-analyst/ra.env` (`root:ra`, `chmod 640`), never committed:
  `RA_MARKET_FRED_API_KEY`, `RA_MARKET_CACHE_DIR=/var/lib/research-analyst/cache`,
  `RA_SEC_USER_AGENT`, `RA_SERVER_HOST=127.0.0.1`, `RA_SERVER_PORT=8700`, `RA_DEBUG=false`.
- **Ingress:** Cloudflare Tunnel id **`c12afde0-a01d-485d-aed6-3dddb3282069`** — the box's **primary**
  tunnel. It also fronts every other production hostname (`dev`, `ai`, `rag`, `agents`, `oracle`,
  `git`, `ci`, and the apex `nrupalakolkar.com`), all routed to the box's Docker nginx (`llmvm_nginx`)
  on `localhost:9080` / `localhost:9443`. The tunnel is **dashboard-managed** (Zero Trust; no local
  `config.yml`). A Public Hostname **`ra-origin.nrupalakolkar.com`** maps to `http://localhost:8700`
  — RA's own systemd service — so it reaches RA directly and **bypasses the Docker nginx** the other
  vhosts use.
  - Hostname is deliberately in the `nrupalakolkar.com` zone (the tunnel's own account/zone) — it is
    a **backend-only** origin the Worker calls; end users only ever see `ra.devinfo.dev`.
  - **No inbound port is opened** — the tunnel is outbound-only; OCI security lists unchanged.
  - Verified 2026-07-22: `https://ra-origin.nrupalakolkar.com/api/health` returns `0.2.1` end-to-end.
    (An earlier on-box probe misreported the tunnel id as `267e8c28`; the live id is `c12afde0`,
    confirmed by the working route and the shared ingress list above.)

## Update procedure (on-box; run by OpenCode / Nrupal)

```bash
cd /opt/research-analyst \
  && sudo -u ra git pull \
  && sudo -u ra .venv/bin/pip install . \
  && sudo systemctl restart ra
```

## Follow-ups
- **Origin auth:** currently parity-open (same exposure as Fly/Render today). Fast-follow = a shared-secret
  header the Worker sends and RA validates, to lock the origin to the Worker only.
- **Docker removal:** RA itself is Docker-free. Fully removing Docker from the box is a *separate* effort —
  the other `nrupalakolkar.com` vhosts still run through the Docker nginx and must be migrated first.
