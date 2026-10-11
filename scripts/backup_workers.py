#!/usr/bin/env python3
# Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
import urllib.error
import urllib.request

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
    listing = _get_json(f"/accounts/{ACCOUNT}/workers/scripts")
    scripts = listing.get("result") or []
    print(f"Found {len(scripts)} workers")
    failures = 0
    for s in scripts:
        name = s.get("id")
        try:
            code, ctype = _get(
                f"/accounts/{ACCOUNT}/workers/scripts/{name}"
            )
            modules = parse_modules(code, ctype)
            for fname, text in modules.items():
                write_file(os.path.join(OUT, name, "src", fname), text)
            settings = _get_json(
                f"/accounts/{ACCOUNT}/workers/scripts/{name}/settings"
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
            print(f"  ok: {name} ({len(modules)} module(s))")
        except urllib.error.HTTPError as e:
            failures += 1
            print(
                f"  FAIL {name}: HTTP {e.code} {e.read()[:200]}",
                file=sys.stderr,
            )
        except Exception as e:  # noqa: BLE001 - fail-soft per worker
            failures += 1
            print(f"  FAIL {name}: {e}", file=sys.stderr)
    # Non-zero exit only if EVERY worker failed (likely auth/config), so a single
    # flaky worker never blocks the rest of the backup.
    if scripts and failures == len(scripts):
        print("All workers failed - check CF_API_TOKEN scope.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
