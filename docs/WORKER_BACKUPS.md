# Cloudflare Workers — automated backup

Daily, versioned snapshots of **every** Cloudflare Worker on the account (source +
config) are committed to the **`backup`** branch of this repo. Purpose: disaster
recovery and drift detection — the live workers are edited in several places
(dashboard quick-editor, wrangler, this repo), so `main` is not a reliable mirror.

## Two independent runners (belt & suspenders)

| Runner | Trigger | Independent of | Status |
| --- | --- | --- | --- |
| **Primary** — GitHub Actions (`.github/workflows/backup-workers.yml`) | cron `0 9 * * *` = 03:00 MDT + manual `workflow_dispatch` | Cloudflare | this PR |
| **Fallback** — Cloudflare Worker cron (`workers/backup-cron/`) | cron 09:30 UTC = 03:30 MDT | GitHub Actions scheduler | separate PR |

Both run the same logic and commit **only on diff** to the same `backup` branch.
If the primary already snapshotted at 03:00, the 03:30 fallback finds no diff and
no-ops. If GitHub Actions is down/disabled, the fallback still captures the day.

## What each snapshot contains

Per worker `<name>` under `workers/<name>/`:
- `src/<module...>` — the deployed source module(s), exact bytes.
- `metadata.json` — `compatibility_date`, `compatibility_flags`, `usage_model`, and
  `bindings` (**names and types only** — the Cloudflare API never returns secret
  values, so no secrets are ever committed).

Routes are **not** captured in v1 (they need a separate Zone-scoped read). Documented
as a v2 add so the backup token can stay minimal (Workers Scripts → Read only).

## Secrets (added by Nrupal — never by the assistant)

GitHub → repo **Settings → Secrets and variables → Actions**:
- `CF_API_TOKEN` — Cloudflare API token, scope **Account → Workers Scripts → Read**.
  Least privilege: can download worker code + settings, cannot edit/deploy/delete or
  touch DNS.
- `CF_ACCOUNT_ID` — `2edd59d09fd816187b47afbb9ea43af1`.

The fallback Worker additionally needs (as encrypted Worker secrets): the same
`CF_API_TOKEN`, plus a GitHub fine-grained PAT (`contents:write` on this repo only)
to push commits — a Worker cannot use Actions' built-in token. That extra PAT is the
one real cost of the second runner.

## Activation order

1. Merge this PR to `main` (GitHub only fires `schedule` from the default branch).
2. Ensure the `backup` branch exists (created alongside this PR).
3. Add `CF_API_TOKEN` + `CF_ACCOUNT_ID` secrets.
4. Trigger once manually (Actions tab → this workflow → **Run workflow**) to prove it,
   then let the daily cron take over.

## Failure behavior

- Per-worker fail-soft: one flaky worker is logged and skipped; the rest still back up.
- The job exits non-zero **only** if every worker fails (i.e. an auth/config problem),
  so a broken run is visible in the Actions tab rather than silently green.
- Commits are tagged `[skip ci]` so backup commits never trigger other workflows.
