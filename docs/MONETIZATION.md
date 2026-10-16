<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Research Analyst — Monetization Cut (refinement, not final)

Working draft for "what can we sell with v0.2.0/0.2.1 on?" This is a **refinement pass**: it proposes an
open-core model, an ICP, a feature-gating map, and **pricing options** — but two things are explicitly
left for Nrupal to decide (Sections 5 and 6). Nothing here is a committed price or a public number.

---

## 1. Model: open-core / freemium (hosted SaaS on top of an AGPL core)

Sell the **hosted, higher-capability service**, not the code. The engine can stay open; the money is in
the managed origin + premium features + convenience.

- **Free tier** — the on-ramp and the credibility demo:
  - Single-ticker report (the existing `/api/research`), basic/comprehensive.
  - Rate-limited (the token-bucket limiter already exists), a few reports/day.
  - Watermarked export footer (already: "prepared on ra.devinfo.dev").
- **Paid tier(s)** — unlock the v0.2.0/0.2.1 differentiators + retention features:
  - **Multi-ticker comparative** (`/api/compare`, 2–5 tickers, scorecard + per-dimension tables).
  - **International markets** (non-US listings via yfinance, e.g. `RY.TO`).
  - **PDF / self-contained HTML export** (client-side today — gate behind auth for paid).
  - **Saved watchlists + report history** (net-new; drives retention and recurring value).
  - **Scheduled / emailed reports** (net-new; the strongest recurring-revenue hook, and the native
    feature that also unblocks the iOS App Store review — see PACKAGING.md).

Why this shape: the free single-ticker report is genuinely useful (it converts skeptics), while the
**comparative + international + export + scheduling** bundle is exactly what a serious user pays to keep.

---

## 2. ICP (who pays)

Grounded in real usage, not a persona invented from nothing:

1. **Prosumer retail investors** — self-directed, run multi-name comparisons, want a clean exportable
   report. The comparative scorecard is the wedge vs. free screeners.
2. **Independent financial advisors / RIAs** — need defensible, branded, client-ready research on
   demand. **Direct evidence this is real:** Nrupal already shares RA reports with his BMO advisor
   **Tracy Liew** — that is the advisor workflow in miniature. Advisors value: PDF/HTML export,
   multi-ticker comparatives, scheduled reports, and (later) white-label footers.

Secondary: finance content creators / newsletter writers who want repeatable, citable analysis.

---

## 3. Feature-gating map (v0.2.0/0.2.1 capabilities → tier)

| Capability | Free | Pro (self-serve) | Advisor/Team |
| --- | --- | --- | --- |
| Single-ticker report (`/api/research`) | ✅ (rate-limited) | ✅ | ✅ |
| Comprehensive / long-term / tactical types | basic only | ✅ all | ✅ all |
| **Multi-ticker comparative** (`/api/compare`) | — | ✅ (2–5) | ✅ (2–5, higher volume) |
| **International markets** | — | ✅ | ✅ |
| **PDF / HTML export** | MD only, watermarked | ✅ clean PDF/HTML | ✅ + white-label footer |
| **Saved watchlists + history** | — | ✅ | ✅ shared/team |
| **Scheduled / emailed reports** | — | ✅ (limited cadence) | ✅ (higher cadence, multi-recipient) |
| Rate limits | tight | generous | highest |
| Seats | 1 | 1 | multiple |

Gating is enforced at the API/auth layer (there is no auth yet — building accounts + entitlements is the
main net-new engineering for monetization; comparative/international/export already exist).

---

## 4. Pricing OPTIONS (recommendation, not final — do **not** publish without the Section 5 decision)

Present as options with rationale; anchored to comparable retail-research/screener tools. Numbers are a
**private starting recommendation**, to be validated, not hardcoded.

- **Option A — simple two-tier (recommended start):**
  - Free; **Pro ≈ $12–19/mo** or **≈ $99–149/yr** (annual discount to smooth churn).
  - Rationale: single obvious upgrade; low friction; the annual plan is the real target for advisors.
- **Option B — three-tier (add Advisor/Team):**
  - Free; Pro (as A); **Advisor/Team ≈ $39–79/mo** (multi-seat, higher cadence, white-label).
  - Rationale: captures RIA willingness-to-pay without pricing out prosumers; defer until there's one
    paying advisor to design around (Tracy-style workflow).
- **Option C — credit/usage add-on:** flat Pro + metered scheduled-report volume. Rationale: aligns cost
  (each report = compute on the box) with revenue; more complexity, defer.

**Private recommendation:** launch **Option A**, annual-forward, **$15/mo or $120/yr** as the anchor to
test; layer in Advisor/Team (Option B) only after the first advisor commits. Keep this number private
until Section 5 is decided. Billing: LemonSqueezy or Stripe (LemonSqueezy is already the chosen rail for
vault-tracker — reuse it as merchant-of-record to avoid tax/VAT overhead).

---

## 5. ⚠️ DECISION TO SURFACE — public pricing (do not resolve unilaterally)

There is a **direct conflict with a standing rule** and it needs Nrupal's explicit call:

- **Standing rule:** the **consulting** page shows **no public pricing** (quoted privately).
- **Reality of self-serve SaaS:** a self-serve product with a free tier and a "Pro" upgrade button
  almost always needs a **public price** to convert — hiding it kills self-serve funnels.

**Options for Nrupal to choose from:**
1. **Public price for RA-the-product** (treat RA as a distinct SaaS brand, separate from the consulting
   practice) — recommended if self-serve conversion is the goal.
2. **"Contact for access" / waitlist** (keeps pricing private, matches the consulting rule) — fine for an
   advisor-only, high-touch launch; poor for prosumer self-serve.
3. **Hybrid:** public price for Pro (prosumer), private/quoted for Advisor/Team.

This is a positioning decision (is RA a self-serve product or an extension of the private practice?), so
it is surfaced, not assumed. **No pricing has been or will be published pending this call.**

---

## 6. ⚠️ Licensing reality — reconcile before selling

The general note is "code MIT + content CC BY-NC 4.0 sitewide," but **the RA repo does not match that**:

- `LICENSE`, `pyproject.toml`, and `package.json` all declare **AGPL-3.0**. RA is **not** MIT.

This is actually **favorable** for open-core and should probably be kept:

- **AGPL-3.0 is the classic open-core lever.** Its network-copyleft clause means anyone running a
  modified RA as a service must publish their source — which deters a competitor from hosting your code
  as a rival paid service, and pushes commercial users toward your hosted tier or a **commercial
  license**.
- **Open-core boundary to define:**
  - **Open (AGPL):** the engine / report pipeline in `research_analyst/` — self-hosting is allowed and
    welcome (it's the credibility + community surface), subject to AGPL's share-alike.
  - **Paid / proprietary:** the **hosted service** (accounts, entitlements, scheduling, watchlists, the
    managed box origin) and any premium closed modules — these are the product. A **dual-license /
    commercial license** covers users who want RA embedded without AGPL obligations.
- **CC BY-NC 4.0** governs devinfo.dev **written content** (articles), not RA's code — so "sell RA" does
  not conflict with the content license, but the **NC (non-commercial)** clause is a reason to keep
  product code and site content licensed separately and explicitly.

**Action for Nrupal:** confirm RA stays **AGPL-3.0** (recommended) and that the paid offering is the
**hosted service + commercial license**, not a relicense of the core. Update the sitewide "MIT" statement
to note RA's AGPL exception so the public claim matches the repo.

---

## 7. What to build next for monetization (engineering, not in this cut)

Comparative/international/export already ship. The net-new work to actually charge:
1. Accounts + auth + entitlement checks at the API layer (the real gate).
2. Billing integration (LemonSqueezy/Stripe) + webhook → entitlement.
3. Saved watchlists + report history (storage; box-native, no Docker).
4. Scheduled/emailed reports (a small scheduler on the box + email send) — also the iOS-review unlock.
Each is a separate phased plan; none is started. This doc is the "what to sell," not the build order.

---

## Entitlement model (LOCKED 2026-08-04): API key per email

Paid unlock is a **per-email API key**, not full accounts/OAuth.

**Flow:** user enters email on the site → pays (LemonSqueezy/Stripe) → the payment webhook **generates a
Pro API key bound to that email** → the key is emailed (magic-link style) → the user pastes it into the
PWA/app once → the API validates the key on each request and unlocks Pro (multi-ticker comparative,
international, PDF/HTML export, saved watchlists, scheduled/emailed reports). **Free tier = no key** (or a
free-tier key): rate-limited single-ticker.

**Why this is the right call:**
- **No auth infra** — no OAuth, sessions, or password reset to build and secure.
- **Identical across every channel** — PWA, Play (TWA), F-Droid (WebView), direct APK all just accept a
  key; no per-store login.
- **Purchase stays on the web** → **zero Apple/Google cut and no store-billing-policy conflict** (the app
  never shows an in-app purchase).
- **Device-agnostic, portable, revocable/rotatable**; matches the sovereign ethos.
- **Clean AGPL open-core boundary** — the key + entitlement service is the paid hosted layer; the engine
  stays AGPL and self-hostable.

**Design / security:**
- Keys are secrets: HTTPS only; store **hashed** server-side; per-key tier + rate limit; one active key
  per email (rotatable); key-gen endpoint gated behind the payment webhook; **never committed or logged**.
- Transport: `Authorization: Bearer <key>` (or `X-RA-Key`) forwarded by the worker to the origin; origin
  middleware checks entitlement before running the pipeline.
- Storage on the box: a small key store (**SQLite/file, no Docker**) + validation middleware — box-native,
  fits the existing systemd `ra.service`.

**Build order (future, phased — not started):** (1) key store + validation middleware on the origin;
(2) key-gen endpoint + payment webhook; (3) UI "enter your key" + gated feature flags; (4) key email
delivery. Each is a separate branch + PR; box-side pieces go live via the box redeploy. Keys never pass
through the assistant.

---

## Implementation status (2026-09-25) — key store v1, metering, white-label

Step (1) of the build order is now implemented in `research_analyst/entitlements.py`
+ `server.py` wiring (offline-tested; no billing yet):

- **Key store**: `KeyStore.create(label, entitlements)` issues `ra_live_…` keys;
  only SHA-256 hashes are stored (memory + optional JSON file via
  `RA_BILLING_API_KEYS_FILE`); verification is constant-time; keys are
  revocable and fail closed. Raw keys are returned once at issuance and never
  logged or persisted. The legacy `RA_BILLING_PAID_KEYS` shared-secret list
  keeps working in legacy paid-keys mode.
- **Entitlements**: flags `ra.pro`, `twf.pro`, `api.access`, `white.label`.
  `twf.pro` is a bundle: it unlocks `ra.pro` + `api.access`. (Billing rail:
  Stripe, decided 2026-10-14. The paid source-data download was retired
  2026-10-15 — data RA consumes under license is never sold.)
- **Metering**: `MeteringRecorder` counts requests per key per endpoint per day
  (UTC), with a pluggable sink for a future billing backend. `/api/research`,
  `/api/compare` and `/api/resolve` are metered;
  `GET /api/usage` (key-gated) returns the caller's counts + effective
  entitlements.
- **White-label**: `WhiteLabelProfile` (org name, prepared-on URL, footer note,
  support-link toggle, accent color) via `RA_BILLING_WHITE_LABEL_*` settings;
  applied to the comparative HTML export's chrome only — numbers, sources,
  methodology, disclaimers and compliance lines are never altered.

Still future (unchanged): payment webhook → key-gen, UI key entry + feature
flags, key email delivery.
