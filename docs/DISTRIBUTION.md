<!--
Copyright (C) 2026 2351485 ALBERTA INC. — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Research Analyst — Distribution & Native Package Paths (Phase 9a)

No container marketplace (no Docker rule). The engine ships natively on every
OS. Below are the install paths + what a package listing looks like per OS.

## Linux — pip + systemd (production path)

```bash
# 1) Python package (PyPI-style)
pip install research-analyst[tui]          # or from source: pip install .
# 2) Native service (systemd) — see deploy/oci-native/
sudo bash deploy/oci-native/bootstrap.sh    # user ra, 127.0.0.1:8700, hardened
# 3) Schedule sync (overnight bundles)
sudo cp deploy/native/sync-schedulers.txt /etc/systemd/system/ra-sync.*  # then enable
```

Future (when published to a repo): an `apt`/`yum` repo is a thin wrapper over
the same systemd unit + venv — no behavior change.

## macOS — pip + launchd (optional; PWA is primary)

```bash
pip install research-analyst[tui]
bash deploy/native/macos/install.sh          # LaunchAgent (com.researchanalyst.ra)
```

Homebrew-style formula (future listing) is a tap that runs the same install.sh —
again, thin wrapper over the native LaunchAgent.

## Windows — pip + NSSM

```powershell
pip install research-analyst[tui]
# deploy/native/windows/README.md — NSSM service (native, no Docker)
```

chocolatey-style package (future listing) wraps the same NSSM install.

## Everywhere — the webapp + TUI

- **PWA webapp:** https://ra.devinfo.dev (installable, offline-capable; mirror
  https://ra.aimlds.org) — the primary surface on every OS.
- **TUI / terminal:** `research-analyst tui` (keyboard-first) and
  `research-analyst tui --query TICKER` (headless/scriptable).
- **Local sync:** `research-analyst sync watchlist.json --out ./data`
  (SQLite + NDJSON, incremental, schedulable natively).

## Verifying any install

```bash
bash deploy/native/verify/verify.sh          # health + research + formats + schemas
```

## Licensing note (open-core)

The engine is **AGPL-3.0 open source**. Everything in this repo is free.
Commercial surfaces (white-label, paid API keys, source-data downloads, higher
volume) are licensed separately — see MONETIZATION.md. Native package listings
above distribute the free open-core; the paid tiers are API-key entitlements,
not binary packages.