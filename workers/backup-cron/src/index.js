/**
 * backup-cron - fallback runner for the Cloudflare Workers backup.
 *
 * Primary is a GitHub Actions cron (03:00 MDT). This Worker fires at 03:30 MDT
 * and, if the primary did not already snapshot, captures the day. It is
 * independent of GitHub's Actions scheduler, so a GHA outage never loses a backup.
 *
 * Snapshots EVERY Worker (source + settings) and commits changed files to the
 * `backup` branch via the GitHub Git Data API - committing ONLY when the tree
 * actually differs (no empty commits, so a no-op after the primary is silent).
 *
 * Secrets (wrangler secret put - never committed):
 *   CF_API_TOKEN  Cloudflare token, Account > Workers Scripts > Read
 *   GITHUB_TOKEN  GitHub fine-grained PAT, contents:write on GITHUB_REPO only
 * Vars (wrangler.toml):
 *   CF_ACCOUNT_ID, GITHUB_REPO ("owner/repo"), GITHUB_BRANCH ("backup")
 *
 * STORAGE SEAM: pushSnapshot() is the ONLY GitHub-specific function. To drop the
 * PAT and store to R2 instead, replace pushSnapshot() and bind an R2 bucket.
 */

const CF_API = "https://api.cloudflare.com/client/v4";
const GH_API = "https://api.github.com";

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(run(env));
  },
  async fetch(req, env) {
    // Manual test trigger: GET ...?run=1 (kept trivial; the write path still
    // needs valid secrets, so this cannot do anything an attacker couldn't get
    // by waiting for the cron).
    const url = new URL(req.url);
    if (url.searchParams.get("run") !== "1") {
      return new Response("backup-cron: cron runner. Append ?run=1 to trigger manually.\n", { status: 200 });
    }
    const result = await run(env).catch((e) => ({ error: String(e) }));
    return new Response(JSON.stringify(result, null, 2) + "\n", {
      headers: { "content-type": "application/json" },
    });
  },
};

async function run(env) {
  const { files, workerCount } = await collectWorkerFiles(env);
  const res = await pushSnapshot(env, files);
  return { ok: true, workers: workerCount, files: files.length, ...res };
}

// ---- Cloudflare: list + download all workers ----

function cfHeaders(env) {
  return { Authorization: `Bearer ${env.CF_API_TOKEN}` };
}

async function cfJson(env, path) {
  const r = await fetch(CF_API + path, { headers: cfHeaders(env) });
  if (!r.ok) throw new Error(`CF ${path} -> ${r.status}`);
  return r.json();
}

async function collectWorkerFiles(env) {
  const acct = env.CF_ACCOUNT_ID;
  const listing = await cfJson(env, `/accounts/${acct}/workers/scripts`);
  const scripts = listing.result || [];
  const files = [];
  for (const s of scripts) {
    const name = s.id;
    try {
      const r = await fetch(`${CF_API}/accounts/${acct}/workers/scripts/${name}`, { headers: cfHeaders(env) });
      if (!r.ok) throw new Error(`download -> ${r.status}`);
      const ctype = r.headers.get("content-type") || "";
      const buf = new Uint8Array(await r.arrayBuffer());
      const modules = parseModules(buf, ctype);
      for (const [fname, text] of Object.entries(modules)) {
        files.push({ path: `workers/${name}/src/${fname}`, content: text });
      }
      const settings = (await cfJson(env, `/accounts/${acct}/workers/scripts/${name}/settings`)).result || {};
      const meta = {
        name,
        created_on: s.created_on || null,
        modified_on: s.modified_on || null,
        compatibility_date: settings.compatibility_date || null,
        compatibility_flags: settings.compatibility_flags || null,
        usage_model: settings.usage_model || null,
        bindings: settings.bindings || null,
      };
      files.push({ path: `workers/${name}/metadata.json`, content: JSON.stringify(meta, null, 2) + "\n" });
    } catch (e) {
      // fail-soft per worker: record the error, keep backing up the rest.
      files.push({ path: `workers/${name}/BACKUP_ERROR.txt`, content: `backup failed: ${String(e)}\n` });
    }
  }
  return { files, workerCount: scripts.length };
}

function parseModules(buf, ctype) {
  const dec = new TextDecoder("utf-8");
  if (!ctype.includes("boundary=")) {
    return { "worker.js": dec.decode(buf) };
  }
  const boundary = ctype.split("boundary=")[1].split(";")[0].trim().replace(/^"|"$/g, "");
  const text = dec.decode(buf);
  const out = {};
  for (const part of text.split("--" + boundary)) {
    if (!part.includes("Content-Disposition")) continue;
    const idx = part.indexOf("\r\n\r\n");
    if (idx === -1) continue;
    const head = part.slice(0, idx);
    let body = part.slice(idx + 4).replace(/\r\n$/, "");
    let filename = null;
    let partname = null;
    for (let tok of head.split(";")) {
      tok = tok.trim();
      const fm = tok.match(/^filename="(.*)"$/);
      const nm = tok.match(/^name="(.*)"$/);
      if (fm) filename = fm[1];
      else if (nm) partname = nm[1];
    }
    const key = filename || partname;
    if (!key || key === "metadata") continue;
    out[key] = body;
  }
  return out;
}

// ---- GitHub: atomic commit-on-diff to the backup branch ----

async function ghApi(env, method, path, body) {
  const r = await fetch(GH_API + path, {
    method,
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "backup-cron",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(body ? { "content-type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`GitHub ${method} ${path} -> ${r.status} ${await r.text()}`);
  return r.json();
}

async function pushSnapshot(env, files) {
  const repo = env.GITHUB_REPO;
  const branch = env.GITHUB_BRANCH;
  const ref = await ghApi(env, "GET", `/repos/${repo}/git/ref/heads/${branch}`);
  const headSha = ref.object.sha;
  const headCommit = await ghApi(env, "GET", `/repos/${repo}/git/commits/${headSha}`);
  const baseTreeSha = headCommit.tree.sha;

  const tree = [];
  for (const f of files) {
    const blob = await ghApi(env, "POST", `/repos/${repo}/git/blobs`, {
      content: b64utf8(f.content),
      encoding: "base64",
    });
    tree.push({ path: f.path, mode: "100644", type: "blob", sha: blob.sha });
  }
  const newTree = await ghApi(env, "POST", `/repos/${repo}/git/trees`, { base_tree: baseTreeSha, tree });
  if (newTree.sha === baseTreeSha) {
    return { committed: false, reason: "no changes (primary already captured today)" };
  }
  const stamp = new Date().toISOString().slice(0, 16) + "Z";
  const commit = await ghApi(env, "POST", `/repos/${repo}/git/commits`, {
    message: `chore(backup): worker snapshot ${stamp} [skip ci] (fallback)`,
    tree: newTree.sha,
    parents: [headSha],
  });
  await ghApi(env, "PATCH", `/repos/${repo}/git/refs/heads/${branch}`, { sha: commit.sha });
  return { committed: true, commit: commit.sha };
}

function b64utf8(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
