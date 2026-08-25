# Slice B-B - ETF Metadata Integration

Status: shipped (branch `feat/intl-etf-metadata`, PR pending review). Builds on
Slice B-A (ETF-as-subject minimal), which is merged into `main`.

## Goal

Replace the Slice B-A profile-only ETF surface (fund overview + AUM proxy) with
a real ETF-metadata source, and extend ETF coverage beyond the comprehensive
report to the other single-subject report types.

## What shipped

- **`ETFMetadata` + `ETFTopHolding` models** (`models.py`): expense ratio,
  distribution yield, AUM, tracking index / category, fund family, top holdings,
  sector weights, plus explicit `data_gaps`. Every field is optional and
  degrades to None / empty with a recorded gap - no invented ETF facts.
- **Market-data provider** (`providers/market_data.py`):
  - `_extract_etf_metadata(ticker, info, holdings, sector_weights)` - a pure,
    deterministic function mapping a yfinance `.info` dict (plus normalised
    holdings/sector weights) to `ETFMetadata`. No network, no pandas - fully
    unit-testable.
  - `fetch_etf_metadata(ticker)` - async wrapper reading `.info` and best-effort
    `.funds_data` (holdings, sector weightings) via `asyncio.to_thread`,
    normalising to plain Python and calling the pure extractor. Never raises;
    degrades to a gapped `ETFMetadata`.
  - Expense ratio prefers `annualReportExpenseRatio`, falls back to
    `netExpenseRatio`; yield prefers `yield`, falls back to
    `trailingAnnualDividendYield`; AUM prefers `totalAssets`, falls back to
    `netAssets`.
- **ETF engine** (`engines/etf.py`): `analyze(profile, metadata=None)` - with
  metadata surfaces the real fields; without it falls back to the Slice B-A
  profile-only surface (backward compatible). AUM prefers real net assets and
  falls back to the `market_cap` proxy. Carries the provider per-field data gaps
  forward.
- **Renderer** (`reports/renderer.py`): `render()` accepts `etf=` and packs
  `ctx["etf"]`. `_build_etf_block` renders the enriched surface (expense ratio /
  yield as percentages, index/category, fund family, top holdings, sector
  weights, AUM) when the engine result is present, and falls back to the B-A
  surface otherwise. Wired into comprehensive, tactical, and long-term step 1.
  Equity path unchanged (block returns empty for non-ETF).
- **Orchestrator** (`orchestrator.py`): for ETF subjects, fetches metadata, runs
  the ETF engine, extends `all_assumptions`, and threads `etf=` into `render()`.

## Tests

`tests/test_etf_metadata.py` - fully mocked / deterministic (no network): pure
extractor (full / fallback keys / empty), enriched engine, AUM proxy fallback,
data-gap carry-forward, backward compatibility without metadata, enriched
renderer block, equity gate, and long-term step-1 threading. One
`test_live_etf_metadata_smoke` is marked and skipped unless the RA_LIVE_SMOKE
env var is set. The Slice B-A tests (`tests/test_etf_subject.py`) remain green
unchanged.

## Deferred follow-up (scoped)

- **Comparative report ETF rows.** `reports/comparative_renderer.py` is a
  metric-ranking structure across peers with no per-subject narrative block and
  no `security_type` handling. Surfacing ETF metadata there needs its own design
  pass (per-subject ETF metric rows carried through the comparative pipeline),
  tracked separately rather than forced into the metrics table.
- **A.3d currency sweep** for `visuals.py` / `comparative_renderer.py` is
  independent of this slice.
