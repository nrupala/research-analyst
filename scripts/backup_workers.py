#!/usr/bin/env python3
# Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""Snapshot all Cloudflare Workers (source + settings) into the repo for backup.

Auth (env):
  CF_API_TOKEN   Cloudflare API token, scope: Account > Workers Scripts > Read
  CF_ACCOUNT_ID  Cloudflare account id
  OUT_DIR        output dir (default: "workers")

Writes, per worker <name>:
  <OUT_DIR>/<name>/src/<module...>   deployed source module(s)
  <OUT_DIR>/<name>/metadata.json     compat date/flags, usage model, bindings (NAMES/types only)

Stdlib only. No secret VALUES are ever written: the /settings endpoint returns
secret bindings by name+type, never their contents.
"""
import json
import os
import sys
import urllib.request
import urllib.error

API = "https://api.cloudflare.com/client/v4"
TOKEN = os.environ["CF_API_TOKEN"]
ACCOUNT = os.environ["CF_ACCOUNT_ID"]
OUT = os.environ.get("OUT_DIR", "workers")


def _get(path):
    req = urllib.request.Request(
        API + path, headers={"Authorization": "Bearer " + TOKEN}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), r.headers.get("Content-Type", "")


def _get_json(path):
    data, _ = _get(path)
    return json.loads(data)


def parse_modules(data, ctype):
    """Return {filename: text} for a worker script download (multipart or raw)."""
    if "boundary=" not in ctype:
        return {"worker.js": data.decode("utf-8", "replace")}
    boundary = ctype.split("boundary=", 1)[1].strip().strip('"')
    sep = ("--" + boundary).encode()
    out = {}
    for part in data.split(sep):
        if b"Content-Disposition" not in part:
            continue
        try:
            head, body = part.split(b"\r\n\r\n", 1)
        except ValueError:
            continue
        headtext = head.decode("utf-8", "replace")
        filename = None
        partname = None
        for tok in headtext.split(";"):
            tok = tok.strip()
            if tok.startswith('filename="') and tok.endswith('"'):
                filename = tok[len('filename="'):-1]
            elif tok.startswith('name="') and tok.endswith('"'):
                partname = tok[len('name="'):-1]
        key = filename or partname
        if not key or key == "metadata":
            continue
        out[key] = body.rstrip(b"\r\n").decode("utf-8", "replace")
    return out


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    listing = _get_json("/accounts/{}/workers/scripts".format(ACCOUNT))
    scripts = listing.get("result") or []
    print("Found {} workers".format(len(scripts)))
    failures = 0
    for s in scripts:
        name = s.get("id")
        try:
            code, ctype = _get(
                "/accounts/{}/workers/scripts/{}".format(ACCOUNT, name)
            )
            modules = parse_modules(code, ctype)
            for fname, text in modules.items():
                write_file(os.path.join(OUT, name, "src", fname), text)
            settings = _get_json(
                "/accounts/{}/workers/scripts/{}/settings".format(ACCOUNT, name)
            ).get("result", {})
            meta = {
                "name": name,
                "created_on": s.get("created_on"),
                "modified_on": s.get("modified_on"),
                "compatibility_date": settings.get("compatibility_date"),
                "compatibility_flags": settings.get("compatibility_flags"),
                "usage_model": settings.get("usage_model"),
                "bindings": settings.get("bindings"),
            }
            write_file(
                os.path.join(OUT, name, "metadata.json"),
                json.dumps(meta, indent=2, sort_keys=True) + "\n",
            )
            print("  ok: {} ({} module(s))".format(name, len(modules)))
        except urllib.error.HTTPError as e:
            failures += 1
            print(
                "  FAIL {}: HTTP {} {}".format(name, e.code, e.read()[:200]),
                file=sys.stderr,
            )
        except Exception as e:  # noqa: BLE001 - fail-soft per worker
            failures += 1
            print("  FAIL {}: {}".format(name, e), file=sys.stderr)
    # Non-zero exit only if EVERY worker failed (likely auth/config), so a single
    # flaky worker never blocks the rest of the backup.
    if scripts and failures == len(scripts):
        print("All workers failed - check CF_API_TOKEN scope.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
