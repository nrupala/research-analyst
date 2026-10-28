<!--
Copyright (C) 2026 2351485 ALBERTA INC. — SPDX-License-Identifier: AGPL-3.0-or-later
See LICENSE and COMMERCIAL-LICENSE.md for licensing terms (commercial licenses available).
-->

# Research Analyst — API Reference & Integration Samples (Phase 9c)

The public REST surface is typed and versioned (`schema_version` on every
payload). Formats: `json` (default), `xml`, `markdown`, `html`, `ts`
(TypeScript definitions) via `?format=` or the `Accept` header.

## Endpoints

| Endpoint | Method | Purpose | Formats |
|---|---|---|---|
| `/api/research` | POST | Full 7-step research report | json, xml, markdown, html, ts, csv, pdf |
| `/api/research/quant` | GET | Quant engine results for a ticker | json |
| `/api/research/embed` | GET | Standalone embed card for a ticker's report | html |
| `/api/research/shared/{token}` | GET | A saved scenario's report via its share link (no key) | all research formats |
| `/api/scenarios` | POST / GET | Save / list your scenarios (key required) | json |
| `/api/scenarios/{id}` | DELETE | Delete your scenario (kills its share link) | json |
| `/api/watchlist` | POST / GET | Add / list your watched tickers (key required) | json |
| `/api/watchlist/{ticker}` | DELETE | Remove a ticker from your watchlist | json |
| `/api/watchlist/quotes` | GET | Current prices for your watchlist, each with its source | json |
| `/api/compare` | POST | Multi-ticker comparative (2–5) | json, xml, markdown, html, ts |
| `/api/resolve` | POST | Ticker/name resolution (+ international `X.NS`) | json, xml, ts |
| `/api/usage` | GET | Your key's plan, usage, allowance (key required) | json |
| `/api/telemetry/summary` | GET | Aggregate request counts (operator; admin key) | json |
| `/api/disclaimer` | GET | Educational disclaimer (v2) | json |

The `csv` and `pdf` formats export the report's own analysis tables —
never raw source data. The quant endpoint computes over the same
merged, first-source-led statements as the report and names that set
in `statements_source`; it also accepts `discount_rate` and a
URL-encoded JSON `scenarios` array for expected-value computation.
Saving a scenario takes a flat body (`{name, ticker, report_type?,
timeframe?, custom_assumptions?}`) and returns a `scenario_id` and a
`share_token`; the share link is the credential, so treat it like a
password.

### Request bodies

```jsonc
// /api/research
{ "ticker": "AAPL", "report_type": "comprehensive", "timeframe": "1Y" }
// report_type: comprehensive | long_term | tactical | all

// /api/compare
{ "tickers": ["AAPL", "MSFT", "NVDA"], "timeframe": "1Y" }

// /api/resolve
{ "query": "Apple" }
```

### API keys, metering and allowances

The analysis endpoints also serve a keyed lane for API plans. Send
`X-RA-Key: <key>` to attribute calls to your key:

- A valid key without `api.access` gets **403**; an invalid or revoked
  key gets **401**. Keyless calls use the free public lane, unchanged.
- API plans carry a monthly call allowance (API Pro 100,000; API Team
  1,000,000) and a per-key rate cap (60/min Pro, 300/min Team). Served
  calls count toward the allowance — a call our pipeline fails is never
  counted. Exceeding either limit returns **429**.
- `GET /api/usage` with your key returns today's and this month's
  per-endpoint counts, your plan's allowance, and the remaining calls.

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

## CLI / TUI / Sync

```bash
research-analyst serve                         # web API on 127.0.0.1:8700
research-analyst tui                           # interactive terminal
research-analyst tui --query AAPL              # headless report to stdout
research-analyst sync watchlist.json --out ./data
research-analyst schema-export --out exports/
research-analyst billing generate-key          # paid keys (operator)
```