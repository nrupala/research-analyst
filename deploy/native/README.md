<!--
Copyright (C) 2026 2351485 ALBERTA INC. — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Research Analyst — Sovereign Packaging (native, NO Docker)

One engine, native deployable anywhere. Every path uses the OS's own service
manager + a Python venv — no containers, no Kubernetes.

| OS | Service manager | Files | Notes |
|---|---|---|---|
| **Linux** (primary — production) | systemd | `../oci-native/ra.service` + `bootstrap.sh` | The live sovereign origin on oracle-aetheris. User `ra`, 127.0.0.1:8700, MemoryMax 4G, hardening. |
| **macOS** | launchd | `macos/com.researchanalyst.ra.plist` + `install.sh` | Optional local instance. **Primary macOS surface = the installable PWA** (ra.devinfo.dev) + TUI/terminal — no native install needed. |
| **Windows** | NSSM | `windows/README.md` | Native service (no Docker). PWA/TUI remain the primary surfaces. |
| All | native schedulers | `sync-schedulers.txt` | systemd timer / cron / launchd / Task Scheduler for `research-analyst sync`. |

## Offline / air-gapped profile
- Run the API or TUI with the **cache-backed** providers: `research-analyst serve` /
  `research-analyst tui --query TICKER` reuse `_DiskCache`; with no network the
  engine serves whatever is cached and clearly labels stale data.
- The local **sync** bundles (SQLite + NDJSON) are fully readable offline.
- No telemetry, no external CDN requirement for the report content itself.

## Verify any install
```bash
bash deploy/native/verify/verify.sh                    # Linux/macOS (base URL arg)
deploy\native\windows\README.md  (curl the same checks) # Windows
```
Checks: health 200, one research call generates reports, formats json/xml/ts
respond, schema-export artifacts emit.

## Webapp-first (every OS)
The installable **PWA** at https://ra.devinfo.dev (and mirror ra.aimlds.org)
works identically on Linux/macOS/Windows/Android/iOS — offline-capable,
service-worker cached. The TUI and terminal headless mode cover power users
everywhere. Native services above are for always-on local instances, not a
requirement for day-to-day use.