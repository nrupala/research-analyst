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
internal tunnel name `llmvm`). Fly is kept warm as an instant-rollback lever through a 5-day soak,
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
- **Ingress:** Cloudflare Tunnel `llmvm-tunnel` (id `267e8c28-fc70-4a0d-9c65-1790d6b14477`),
  **dashboard-managed** (Zero Trust; no local `config.yml`). A Public Hostname
  **`ra-origin.nrupalakolkar.com`** maps to `http://localhost:8700`. cloudflared runs on the host,
  so it reaches the RA service directly and **bypasses the box's Docker nginx** (`llmvm_nginx`,
  which serves the other `nrupalakolkar.com` vhosts).
  - Hostname is deliberately in the `nrupalakolkar.com` zone (the tunnel's own account/zone) — it is
    a **backend-only** origin the Worker calls; end users only ever see `ra.devinfo.dev`.
  - **No inbound port is opened** — the tunnel is outbound-only; OCI security lists unchanged.

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
