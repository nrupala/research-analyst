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

## CLI / TUI / Sync

```bash
research-analyst serve                         # web API on 127.0.0.1:8700
research-analyst tui                           # interactive terminal
research-analyst tui --query AAPL              # headless report to stdout
research-analyst sync watchlist.json --out ./data
research-analyst schema-export --out exports/
research-analyst billing generate-key          # paid keys (operator)
```