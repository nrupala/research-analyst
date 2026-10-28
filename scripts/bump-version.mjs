#!/usr/bin/env node
// Copyright (C) 2026 2351485 ALBERTA INC.
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// bump-version.mjs — STANDARD app versioning (author-time bump).
//
// Sets ONE version across every web/PWA surface so a release is one command:
//   node scripts/bump-version.mjs 0.2.2
// then:
//   git commit -am "chore: v0.2.2" && git tag v0.2.2 && git push --follow-tags
//
// CI (scripts/stamp-app-version.sh) then stamps the native Android/iOS
// artifacts from that tag. See docs/VERSIONING.md for the full standard.
import { readFileSync, writeFileSync, existsSync } from "node:fs";

const ver = process.argv[2];
if (!ver || !/^\d+\.\d+\.\d+$/.test(ver)) {
  console.error("usage: node scripts/bump-version.mjs <X.Y.Z>");
  process.exit(1);
}
const log = [];

// 1) package.json — the single source of truth
const pkg = JSON.parse(readFileSync("package.json", "utf8"));
const prev = pkg.version;
pkg.version = ver;
writeFileSync("package.json", JSON.stringify(pkg, null, 2) + "\n");
log.push(`package.json  ${prev} -> ${ver}`);

// 2) on-page footer (web app)
const footer = "ui/index.html";
if (existsSync(footer)) {
  const src = readFileSync(footer, "utf8");
  const out = src.replace(/Research Analyst v\d+\.\d+\.\d+/g, `Research Analyst v${ver}`);
  writeFileSync(footer, out);
  log.push(`ui/index.html footer  ${out !== src ? "updated" : "NO MATCH"}`);
}

// 3) PWA manifest version (human-facing)
const mani = "ui/manifest.json";
if (existsSync(mani)) {
  const m = JSON.parse(readFileSync(mani, "utf8"));
  m.version = ver;
  writeFileSync(mani, JSON.stringify(m, null, 4) + "\n");
  log.push(`ui/manifest.json version -> ${ver}`);
}

// 4) service-worker cache version — forces cache invalidation on every release
const sw = "ui/sw.js";
if (existsSync(sw)) {
  const src = readFileSync(sw, "utf8");
  let out = src.replace(/CACHE_VERSION\s*=\s*"[^"]*"/, `CACHE_VERSION = "ra-v${ver}"`);
  out = out.replace(/Service Worker v[0-9][^\n]*/, `Service Worker v${ver}`);
  writeFileSync(sw, out);
  log.push(`ui/sw.js CACHE_VERSION -> ra-v${ver}  ${out !== src ? "" : "(NO MATCH)"}`);
}

// 5) CHANGELOG heading — promote Unreleased into a dated release section
const cl = "CHANGELOG.md";
if (existsSync(cl)) {
  const today = new Date().toISOString().slice(0, 10);
  const src = readFileSync(cl, "utf8");
  if (src.includes("## [Unreleased]")) {
    const out = src.replace("## [Unreleased]", `## [Unreleased]\n\n## [${ver}] - ${today}`);
    writeFileSync(cl, out);
    log.push(`CHANGELOG.md  new heading [${ver}] - ${today}`);
  }
}

// 6) pyproject.toml - the Python package version (server side)
const py = "pyproject.toml";
if (existsSync(py)) {
  const src = readFileSync(py, "utf8");
  const out = src.replace(/^version = "[^"]*"/m, `version = "${ver}"`);
  writeFileSync(py, out);
  log.push(`pyproject.toml  ${out !== src ? "version -> " + ver : "NO MATCH"}`);
}

// 7) research_analyst/__init__.py - the runtime __version__ the API serves
const init = "research_analyst/__init__.py";
if (existsSync(init)) {
  const src = readFileSync(init, "utf8");
  let out = src.replace(/__version__ = "[^"]*"/, `__version__ = "${ver}"`);
  out = out.replace(/Version: \d+\.\d+\.\d+/, `Version: ${ver}`);
  writeFileSync(init, out);
  log.push(`research_analyst/__init__.py  __version__ -> ${ver}`);
}

console.log("bumped to " + ver + ":");
for (const line of log) console.log("  " + line);
console.log(`next: git commit -am "chore: v${ver}" && git tag v${ver} && git push --follow-tags`);
