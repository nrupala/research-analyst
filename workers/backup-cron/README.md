<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# backup-cron — fallback Workers backup (Cloudflare Worker)

Second, independent runner behind the GitHub Actions primary
(`.github/workflows/backup-workers.yml`). See `docs/WORKER_BACKUPS.md` for the
whole-system picture.

- **Fires** at 09:30 UTC (03:30 MDT) — 30 min after the primary.
- **Independent of** GitHub's Actions scheduler: if Actions is down/disabled, this
  still captures the day.
- **Commit-on-diff:** compares the freshly built tree against the current `backup`
  branch tree; if identical (primary already ran at 03:00), it makes **no** commit.
- **Same snapshot format** as the primary: `workers/<name>/src/<module>` +
  `workers/<name>/metadata.json` (bindings by name/type only — no secret values).

## Deploy (Nrupal — not the assistant)

```
cd workers/backup-cron
wrangler deploy
wrangler secret put CF_API_TOKEN     # Account > Workers Scripts > Read
wrangler secret put GITHUB_TOKEN     # fine-grained PAT, contents:write on this repo ONLY
```

`CF_ACCOUNT_ID`, `GITHUB_REPO`, `GITHUB_BRANCH` are non-secret vars in `wrangler.toml`.

## The one real cost

Unlike the GitHub Actions primary (which commits with Actions' built-in token), a
Worker cannot use that token, so this runner needs a **GitHub PAT** as a second
secret. If you'd rather not manage a PAT, the `pushSnapshot()` function is the only
GitHub-specific code — swap it to write the same snapshot to an **R2** bucket
(sovereign, no PAT) and bind the bucket in `wrangler.toml`. Everything else is unchanged.

## Not deployed by CI

This directory is source-of-record only. It is deployed manually (above). Do not wire
it to auto-deploy without a controlled test.
