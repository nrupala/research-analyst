# aimlds.org — true mirror of devinfo.dev (plan)

**Decision (2026-08-04): both `devinfo.dev` and `aimlds.org` are co-equal, true mirrors.** `.dev` is
HSTS-preloaded and newer gTLDs get flagged by conservative corporate IT proxies; `.org` reads as
institutional. Everything on devinfo.dev is replicated on aimlds.org from the **same** build — no fork,
no drift.

**Status: PLAN ONLY.** Nothing built or deployed. Cloudflare/worker steps are box-free but still phased
(need your go). Box-side steps are staged for the box (off-limits until Wed 8/5).

---

## Architecture — one build, two hostnames

Attach **both** custom domains to the **same** Cloudflare Pages and Worker projects. Do **not** create a
second deployment.

```
User ─┬─ ra.devinfo.dev ─┐
      └─ ra.aimlds.org  ─┴─> same `research-analyst` Pages project (UI/PWA)
                              └─ /api/* ─> same `ra-api-proxy` Worker ─> box origin (ra-origin.nrupalakolkar.com)
```

The box origin is unchanged — the Worker calls it regardless of which front-end domain the user came from.

## RA pilot — box-free changes (each phased; do on your go)

1. **Cloudflare zone:** add `aimlds.org` (free plan). Point nameservers.
2. **Pages:** add `ra.aimlds.org` (and any other RA subdomains) as a custom domain on the existing
   `research-analyst` Pages project. DNS: `ra.aimlds.org` CNAME → the Pages project.
3. **Worker `ra-api-proxy`:**
   - Allow **both** origins in CORS (`CORS_ORIGIN` → a set: `ra.devinfo.dev`, `ra.aimlds.org`), returning
     the caller's origin.
   - Add route `ra.aimlds.org/api/*` → the same worker.
4. **Origin CSP (box-side, minor):** `server.py` `connect-src` add `https://ra.aimlds.org` (and drop the
   dead fly/render entries). Takes effect on the next **box redeploy** — stage it, don't run today.

## PWA on a mirror
- A PWA's identity is **per-origin**, so `ra.devinfo.dev` and `ra.aimlds.org` are **two installable apps**.
  That's fine. The manifest is already relative (`start_url:"/"`, `scope:"/"`), so **one manifest works on
  both** unchanged.
- Install CTAs reference the canonical mirror pair; keep in-app API calls same-origin relative (`/api/*`)
  so each origin is self-contained.

## Stores / app packaging on a mirror
- **Digital Asset Links:** host `/.well-known/assetlinks.json` on **both** domains and associate the
  Android app with both origins (TWA + Play App Signing key SHA-256). The F-Droid WebView flavor and the
  direct APK are domain-agnostic.
- Pick which domain the store listing's primary URL uses (recommend the institutional `aimlds.org` for
  the Play/F-Droid listings; keep both in the app's verified origins).

## SEO / canonical (both first-class)
- Both live and indexable. Use **self-referential canonical per origin** + cross-`alternate` links, and
  submit **both** to Google Search Console. Duplicate-content risk is low (same owner, mirrored, alternate
  refs). If Google must collapse to one, nominate `aimlds.org` as the preferred property.

## Blog explainers on the mirror
- The twf explainer series (`BLOG_EXPLAINER_SERIES.md`) posts live on `blog.thinkwithfinance.com` and may
  also be surfaced on the canonical domain; RA→blog "How this is computed" links and blog→RA CTAs use the
  canonical mirror pair.

## Full-site mirror (beyond RA) — scope note
You said **everything** on devinfo.dev mirrors to aimlds.org, not just RA. RA is the **pilot**. The rest is
a broader phased effort:
- **Box-free:** apex + each Pages/Worker property (`dev`, `bee`, `ra`, blog, etc.) → add the aimlds.org
  custom domain; add worker routes; extend CORS/CSP allow-lists.
- **Box-side (staged for the box; off-limits today):** the box's nginx `server_name`s and the
  dashboard-managed **Cloudflare Tunnel public hostnames** (`ai`, `rag`, `agents`, `oracle`, `git`, `ci`,
  apex) need aimlds.org equivalents added so the tunnel fronts both zones. No inbound ports change.
- Track this as its own plan doc when you're ready; this doc covers the **RA** mirror concretely.

## Cost
`.org` registration ~$12/yr + free Cloudflare zone + free multi-domain on Pages/Workers. No new compute.

## Open follow-ups (need your go to build, not decide)
- Confirm you want me to stage the worker CORS/route change + the `server.py` CSP change as a **branch +
  PR** (inert until deploy), plus a `/.well-known/assetlinks.json` served on both origins.
- Everything above stays plan until then.
