# Vendored Plotly.js — partial bundle (Quant Lab Phase 1)

`plotly-2.32.0.min.js` is a **custom partial bundle** of Plotly.js, built
in-house and committed so the app never loads charting code from a CDN or
any external host (fabric doctrine: if every external thing vanished
tonight, the app still fully works).

- **Library:** Plotly.js **2.32.0**, MIT License (Copyright Plotly, Inc.;
  full licence text ships in the `plotly.js` npm package, `LICENSE`).
- **Traces registered (exactly five):** `scatter`, `bar`, `waterfall`,
  `heatmap`, `indicator` — the Quant Lab Phase 1 inventory. Verified via
  `PlotSchema.get().traces` after the build.
- **Size:** 1,150,815 bytes (the full Plotly.js build is ~3.5 MB).
- **sha256:** `121f4c038f80179e7675c42dcfe27086616b85276a9cfebc33995fb244f486d2`
- **Build route:** the documented `plotly.js/lib/core` + `Plotly.register`
  route (entry source: `plotly-partial-entry.js` in this directory),
  bundled and minified with esbuild 0.24.2:

  ```
  npm install plotly.js@2.32.0 esbuild@0.24.2
  esbuild plotly-partial-entry.js --bundle --minify --platform=browser \
    --global-name=Plotly \
    --define:process.env.NODE_ENV='"production"' --define:global=window \
    --outfile=plotly-2.32.0.min.js
  ```

  (`--define:global=window` is the same `global` shim the official
  browserify builds apply; `--global-name=Plotly` exposes `window.Plotly`.)
- **Smoke check at build time:** scatter/bar/waterfall/indicator plotted
  headlessly (jsdom) and the registry contained exactly the five traces.
  Heatmap's module registers identically; its jsdom run needs a real
  canvas 2d context, which jsdom lacks — live rendering proof is the
  Gate 17 real-browser walk, not this build check.
