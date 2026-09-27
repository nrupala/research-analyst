<!--
Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com> — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Research Analyst — API Reference & Integration Samples (Phase 9c)

The public REST surface is typed and versioned (`schema_version` on every
payload). Formats: `json` (default), `xml`, `markdown`, `html`, `ts`
(TypeScript definitions) via `?format=` or the `Accept` header.

## Endpoints

| Endpoint | Method | Purpose | Formats |
|---|---|---|---|
| `/api/research` | POST | Full 7-step research report | json, xml, markdown, ts |
| `/api/compare` | POST | Multi-ticker comparative (2–5) | json, xml, markdown, html, ts |
| `/api/resolve` | POST | Ticker/name resolution (+ international `X.NS`) | json, xml, ts |
| `/api/disclaimer` | GET | Educational disclaimer (v2) | json |
| `/api/research/data` | POST | **Paid:** source-data bundle (CSV/JSON) behind a report | json, csv |

### Request bodies

```jsonc
// /api/research
{ "ticker": "AAPL", "report_type": "comprehensive", "timeframe": "1Y" }
// report_type: comprehensive | long_term | tactical | all

// /api/compare
{ "tickers": ["AAPL", "MSFT", "NVDA"], "timeframe": "1Y" }

// /api/resolve
{ "query": "Apple" }

// /api/research/data (paid — X-RA-Key header when gating is on)
{ "ticker": "AAPL", "report_type": "comprehensive" }
```

### Typed schemas

```bash
research-analyst schema-export --out exports/
# -> exports/research.schema.json, compare.schema.json, resolve.schema.json
# -> exports/types.d.ts   (TypeScript definitions for every payload)
```

## Python sample

```python
import urllib.request, json

def research(ticker, report_type="comprehensive", fmt="json"):
    body = json.dumps({"ticker": ticker, "report_type": report_type}).encode()
    url = f"https://ra.devinfo.dev/api/research?format={fmt}"
    req = urllib.request.Request(url, data=body,
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)

data = research("AAPL")
print(data["schema_version"], data["reports"][0]["title"])
```

## TypeScript sample

```typescript
// types come from: research-analyst schema-export --out exports/
import type { ResearchAPIResponse } from "./exports/types";

const resp = await fetch("https://ra.devinfo.dev/api/research", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ ticker: "MSFT", report_type: "tactical" }),
});
const data = (await resp.json()) as ResearchAPIResponse;
console.log(data.schema_version, data.ticker);
```

## Paid data download (CSV)

```bash
curl -X POST https://ra.devinfo.dev/api/research/data?format=csv \
  -H "content-type: application/json" \
  -H "X-RA-Key: <your-paid-key>" \
  -d '{"ticker":"AAPL","report_type":"comprehensive"}' \
  -o AAPL_source_data.csv
```

### Bundle schema (`POST /api/research/data`, JSON)

The JSON body is the canonical form; `?format=csv` flattens the same structure
with one `section, key, value` triplet per leaf.

| Key | Type | Notes |
|---|---|---|
| `schema_version` | string | `"1.1"`. Bumped when a key is removed or its meaning changes. |
| `ticker`, `company_name`, `currency`, `generated_at`, `security_type` | string | Request identity. `generated_at` is ISO-8601, `""` if unset. |
| `tables` | array | `{title, rows}` where `rows` is an array of cell arrays parsed from the report's markdown tables. Header and alignment rows are stripped. |
| `metrics` | object | Flat key/value map, merged across every report in the request. See precedence below. |
| `scenarios` | array | Valuation scenarios, one per scenario type. Deduplicated by `scenario_type`. |
| `peers` | array | Peer rows, verbatim cells, header stripped. Deduplicated by ticker. |

#### `metrics` precedence

A request may return several reports. Metrics **accumulate** across them rather
than the last report winning:

1. A key already holding a non-null value is never overwritten.
2. A key holding `null` may be filled by a later report.
3. Two non-null values for the same key: the first wins, so the result does not
   depend on report ordering.

This matters because the reports describe the same security — a later, sparser
report must not erase a metric an earlier one computed.

#### Legitimately-null `metrics` keys

Not every `null` is a defect. These are `null` **by design** and carry meaning:

| Key | Why it can be null |
|---|---|
| `risk_score` | No score is published when no material risks were identified (a 1–10 score over an empty risk set would be arbitrary). `risk_score_note` is present whenever the value is null, and the full risk inventory is always in `tables`. |
| `dividend_yield`, `payout_ratio_eps`, `payout_ratio_fcf`, … | The security pays no dividend, or the basis is unavailable. |
| `peer_median_yield` | No dividend-paying peer in the comparison universe. `peer_yields` holds the per-peer values when they are available. |
| `fcf_deployment.*_pct_of_fcf` | Free cash flow or the deployment figure is unavailable for the period. |

A `null` is never emitted for a key that simply failed to resolve a field name.
If a key appears here it is one the model actually defines.

#### Field-name traps

`payout_ratio_eps` and `payout_ratio_fcf` are **different numbers on different
bases** (dividends ÷ net income vs dividends ÷ free cash flow) and are always
both emitted. There is deliberately no combined `payout_ratio`: a single
unqualified figure hides which basis produced it.

`annual_dividends` is split into `annual_dividends_complete_years` and, when the
current calendar year is in progress, `annual_dividends_partial`. The partial
year is dividends received to date, not a full-year total, and must not be
plotted beside completed years without that caveat.

`peer_median_yield` is computed over the whole competitor universe, which is a
different population from the eight rows in `peers`. `peer_yields` carries the
per-peer trailing yields so the median can be reproduced; without it the figure
is unverifiable.

#### Scenarios

Each entry carries `scenario_type`, `label`, `price_low`, `price_high`,
`revenue_growth`, `operating_margin`, `pe_multiple`, `ev_ebitda_multiple`,
`implied_upside_low`, `implied_upside_high`, and an `assumptions` array
(`label`, `value`, `source`, `confidence`).

`pe_multiple` and `ev_ebitda_multiple` are the multiples actually applied,
published on the model rather than narrated in prose only. Each corresponding
`assumptions` entry states the base multiple and its source — for example that
the base P/E blends the company's own trailing P/E with the peer median when the
two are far apart. Read the `assumptions` entry to know where the number came
from; the numeric field tells you what was used.

A `null` `pe_multiple` therefore means the P/E method did not apply (no positive
EPS, or a revenue-multiple fallback was used), not that a number was lost.

## CLI / TUI / Sync

```bash
research-analyst serve                         # web API on 127.0.0.1:8700
research-analyst tui                           # interactive terminal
research-analyst tui --query AAPL              # headless report to stdout
research-analyst sync watchlist.json --out ./data
research-analyst schema-export --out exports/
research-analyst billing generate-key          # paid keys (operator)
```