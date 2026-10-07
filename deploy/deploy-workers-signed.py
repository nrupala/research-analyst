# Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
"""Deploy a research-analyst Cloudflare Worker — SIGNED ONLY.

Portfolio Certification Program (2026-10-05): manual deploys of the
research-analyst edge Workers go through the site-integrity signed-deploy
wrapper. There is no unsigned path: this script uploads the worker module via
deploy_signed.py, which carries forward non-secret bindings, preserves
server-side secrets, re-hashes the deployed bytes, and mints a signed ledger
certificate. The integrity watcher treats any deploy without a ledger
certificate as unauthorized.

Usage:
  deploy-workers-signed.py <worker> [--note TEXT]

  worker: research-analyst-api | backup-cron

Notes:
- Both modules are single files (no imports, no build step) — safe for the
  wrapper's single-file upload.
- This covers the edge Workers only. The main app deploys to Fly.io from CI
  (.github/workflows/ci.yml) — a signed path for Fly.io needs the owner's
  decision (see PR body).
- Running this script is a production deploy: only with the owner's explicit
  go-ahead.
"""
from __future__ import annotations

import subprocess
import sys

DEPLOY_SIGNED = "/home/hatch/workspace/site-integrity/deploy_signed.py"

WORKERS = {
    "research-analyst-api": "workers/research-analyst-api/src/index.js",
    "backup-cron": "workers/backup-cron/src/index.js",
}


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] not in WORKERS:
        raise SystemExit(
            "usage: deploy-workers-signed.py <{}> [--note TEXT]".format("|".join(WORKERS)))
    name = args[0]
    module = WORKERS[name]
    note = f"{name} deploy via signed wrapper"
    i = 1
    while i < len(args):
        if args[i] == "--note" and i + 1 < len(args):
            note = args[i + 1]
            i += 2
        else:
            i += 1

    r = subprocess.run(
        [sys.executable, DEPLOY_SIGNED, name, module,
         "--main-module", "index.js", "--note", note])
    if r.returncode != 0:
        raise SystemExit(f"signed deploy failed (exit {r.returncode})")
    print(f"{name} SIGNED DEPLOY OK")


if __name__ == "__main__":
    main()
