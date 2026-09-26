<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Research Analyst v0.2.1 — Launch Verification & Runbook

Status date: **2026-08-04**. Author: build engine (phased delivery). This doc is the
single source of truth for the v0.2.1 robust-launch effort: what is verified live,
what shipped box-free today, and the exact staged steps for the box tomorrow (Wed 2026-08-05).

> Naming: the shipped code is **0.2.1** (= the 0.2.0 multi-ticker comparative release
> **plus** the Slice-0 data-integrity fixes). We launch as 0.2.1 rather than advertise a
> version behind the backend. "v0.2.0 launch" in the task = this 0.2.1 launch.

---

## A. Recon — live vs. main (ground truth, verified by direct `curl`)

| Surface | Result |
| --- | --- |
| `main` HEAD | `9310788` (docs). Last **code** change `a842809` = v0.2.1 (Slice-0). |
| Full test suite (sandbox) | **64 passed** on `main` as-is. |
| `https://ra.devinfo.dev/api/health` (public) | `{"status":"ok","version":"0.2.1"}` |
| `POST https://ra.devinfo.dev/api/compare` (public, multi-ticker) | **HTTP 200**, valid ComparativeReport (AAPL vs MSFT) |
| `POST https://ra.devinfo.dev/api/research` single-ticker AAPL | HTTP 200, full report, ~1.7s |
| International `RY.TO` (public) | HTTP 200, "Royal Bank of Canada", 0 warnings |
| `https://ra-origin.nrupalakolkar.com/api/health` (box origin) | `0.2.1` |

**Conclusion:** the earlier "RA v0.2.0 live" claim understates reality — the public surface is
already serving **0.2.1** with multi-ticker comparative, export, and Slice-0 fixes live. The launch
is fundamentally **in good shape**. The gaps below are robustness/coherence, not an outage.

> Cache caveat: a cached `web_fetch` initially reported the public health as `0.1.1`. Direct
> `curl` (fresh, `cf-cache-status: DYNAMIC`) is authoritative: **0.2.1**. Always verify with curl.

### Gaps found (and their disposition)

1. **Bad-ticker fabrication (quality).** `POST /api/research {"ticker":"ZZZQQXX"}` returned **HTTP 200
   with a fully fabricated report** instead of an error. → Fixed in **PR #7** (goes live on box redeploy).
2. **Version-string incoherence.** Backend 0.2.1 but UI footer / `manifest.json` / `package.json` /
   `sw.js` all said 0.2.0. → Fixed in **PR #8** (auto-ships via Pages on merge).
3. **PWA not actually installable.** `sw.js` + manifest + icons all shipped, but `app.js` never
   registered the service worker. → Fixed in **PR #8** (registration added; cache bumped ra-v3→ra-v4).
4. **Worker config drift.** `workers/api-proxy/wrangler.toml` still names the retired Fly/Render
   origins. Live routing already reaches the box (0.2.1), but a future `wrangler deploy` from the repo
   would revert routing to the dead Fly origin. → Corrected in **PR #8** (inert until deploy).
5. **CI landmines** (workflow file — staged as web-editor steps below): `ci.yml` still auto-deploys
   to Fly on every push to `main`, and runs `pytest ... || true` so **Python test failures do not
   gate** merges/deploys (only the Node UI test gates).
6. **Legacy Docker artifacts** (`Dockerfile`, `docker-compose.yml`, `fly.toml`, `render.yaml`, and the
   Docker-based `deploy/oci/setup.sh`) contradict the no-Docker reality (box runs native systemd). →
   Sequenced cleanup below.

---

## B. Shipped box-free today (open PRs — Nrupal merges; never auto-merged)

- **PR #7 — `fix/reject-unresolvable-tickers`**: resolution guard in `get_company_profile`; unknown
  symbols now return a clean 400 instead of a fabricated report. +5 offline tests. Suite **69 passed**.
  _Live effect requires the box redeploy (Section D)._
- **PR #8 — `launch/v0.2.1-coherence`**: version sync to 0.2.1, **service-worker registration**
  (makes the PWA installable), `CACHE_VERSION` ra-v3→ra-v4, `wrangler.toml` origin truth, CHANGELOG.
  _UI auto-deploys via git-connected Pages on merge; worker config is a manual `wrangler deploy`._

Merge order suggestion: **#7 first** (data path), then **#8** (presentation). Both are independent.

---

## C. Launch verification checklist

| # | Check | Method | Result |
| --- | --- | --- | --- |
| 1 | Single-ticker report | `POST /api/research {AAPL}` | ✅ 200, full report ~1.7s |
| 2 | Multi-ticker comparative | `POST /api/compare {AAPL,MSFT}` | ✅ 200, scorecard + per-dimension tables |
| 3 | International ticker | `POST /api/research {RY.TO}` | ✅ 200, RBC, yfinance sources, 0 warnings |
| 4 | PDF / HTML / MD export | client-side toolbar (v0.1.2) | ✅ present; `node ui/tests/compare.test.mjs` 6/6 |
| 5 | Bad-ticker error handling | `POST /api/research {ZZZQQXX}` | ⚠️ **200 fabricated today** → fixed by PR #7; **re-verify after box redeploy → expect 400** |
| 6 | UI smoke (ra.devinfo.dev) | load page, mode toggle, run | ✅ live UI renders; footer will read 0.2.1 after PR #8 Pages deploy |
| 7 | PWA installable/offline | manifest + registered SW + 192/512 icons over HTTPS | ⚠️ **installable only after PR #8** (SW now registered) |
| 8 | `/api/health` version | GET | ✅ 0.2.1 (box + public) |
| 9 | Full test suite | `pytest -q` | ✅ 69 passed |

**Box-pending checks** (cannot complete until the box redeploy): #5 (expect 400), and confirming the
box origin serves PR #7's guard. Everything else is verified box-free.

---

## D. Box-dependent runbook — run tomorrow (Wed 2026-08-05)

> Only needed to activate **PR #7** (bad-ticker guard) on the live origin. The public 0.2.1 comparative
> launch is already live and does **not** depend on this. No Docker. FRED/API keys stay on the box
> (`/etc/research-analyst/ra.env`) — never passed through the assistant, never committed.

**Step 1 — redeploy the native origin** (authoritative procedure per `docs/DEPLOYMENT.md`; requires
PR #7 merged to `main` first):

```bash
cd /opt/research-analyst \
  && sudo -u ra git pull \
  && sudo -u ra .venv/bin/pip install . \
  && sudo systemctl restart ra
```

**Step 2 — verify the origin locally on the box:**

```bash
# health = 0.2.1
curl -s http://127.0.0.1:8700/api/health

# bad ticker now rejected (expect 400, NOT a 200 report)
curl -s -o /dev/null -w "bad-ticker HTTP %{http_code}\n" \
  -X POST http://127.0.0.1:8700/api/research \
  -H 'Content-Type: application/json' -d '{"ticker":"ZZZQQXX"}'

# good ticker still works (expect 200)
curl -s -o /dev/null -w "AAPL HTTP %{http_code}\n" \
  -X POST http://127.0.0.1:8700/api/research \
  -H 'Content-Type: application/json' -d '{"ticker":"AAPL"}'
```

**Step 3 — verify end-to-end through the tunnel + worker:**

```bash
curl -s https://ra-origin.nrupalakolkar.com/api/health          # box origin, expect 0.2.1
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  https://ra.devinfo.dev/api/research \
  -H 'Content-Type: application/json' -d '{"ticker":"ZZZQQXX"}'   # public, expect 400
```

If Step 2 health is not 0.2.1 or the bad-ticker check is not 400: `sudo systemctl status ra` and
`journalctl -u ra -n 100 --no-pager`, confirm `git log -1` shows PR #7's commit, and that
`.venv/bin/pip install .` completed without error. Rollback = `git checkout <prev-sha> && pip install . && systemctl restart ra`.

---

## E. Box-free phased follow-ups (do off-box; each needs your go)

**E1 — Deploy the corrected Worker (Cloudflare, box-free).** After PR #8 merges, make the running
worker match the repo (box origin, not dead Fly):

```bash
cd workers/api-proxy && npx wrangler deploy
```
First confirm the live worker's current `BACKEND_PRIMARY` in the Cloudflare dashboard (Workers →
`ra-api-proxy` → Settings → Variables). If it already points at `ra-origin.nrupalakolkar.com` via a
dashboard override, this deploy is a no-op that simply pins the repo as source of truth. Re-verify
with `curl https://ra.devinfo.dev/api/health` (expect 0.2.1).

**E2 — CI hardening (GitHub web editor — the API token here lacks `workflow` scope).** Edit
`.github/workflows/ci.yml`:
- **Delete the `deploy-fly` job** (it auto-deploys every push to the retired Fly origin).
- **Remove `|| true`** from the Lint / Type check / Test steps so red tests actually block merges
  and deploys. Keep the Node UI test gate as-is.

**E3 — Retire legacy deploy/Docker artifacts (follow-up PR, _after_ E2).** Once CI no longer calls
Fly: delete `Dockerfile`, `docker-compose.yml`, `fly.toml`, `render.yaml`; rewrite or remove
`deploy/oci/setup.sh` (it is Docker-based and contradicts the native systemd reality documented in
`DEPLOYMENT.md`). Order matters — do E2 before removing `fly.toml`/`Dockerfile` or the last Fly deploy
job would fail.

---

## F. Standing rules honored

- **Market-data source rule:** yfinance (free) is primary; Alpha Vantage key + FRED are optional
  backups only. No paid feed promoted to primary. Confirmed in `config.py` (`MarketDataConfig`).
- **Secrets:** FRED key lives only in `/etc/research-analyst/ra.env` on the box. Nothing in this
  effort read, wrote, logged, or committed a key.
- **Phased delivery:** every change is a branch + PR with green local CI. No direct-to-main, no merges
  by the engine, no Docker.
