# Research Analyst as an AIOA/OGSA Agency

Research Analyst (RA) operates as the **`research-intel`** agency inside an
OGSA-governed AllinOneAgency deployment — without any modification to AIOA
itself. The contract lives in `research_analyst/agency.py` (RA-owned).

## Wiring

AIOA's OGSA core dispatches tasks shaped like:

```json
{"id": "...", "sourceAgent": "ogsa", "targetAgent": "research-intel",
 "action": "research:analyze",
 "payload": {"ticker": "AAPL", "report_type": "comprehensive",
             "timeframe": "1Y", "assumptions": {}},
 "tokenId": "...", "priority": 1, "createdAt": 1720000000000}
```

Point the `research-intel` handler at `research_analyst.agency.handle_ogsa_task`
(an `async` function taking the task dict and returning a `TaskResult` dict):

```python
from research_analyst.agency import handle_ogsa_task

result = await handle_ogsa_task(task)
# {"taskId": ..., "status": "success"|"error"|"timeout",
#  "output": {...}, "error": {...}?, "completedAt": <epoch ms>}
```

The legacy in-AIOA placeholder called `analyze(text, urls)`; payloads in that
old shape are mapped explicitly onto the versioned contract with a warning —
never silently.

## Actions

| Action | Payload | Result |
|---|---|---|
| `research:analyze` | `ticker`, `report_type`, `timeframe`, `assumptions` | Structured report |
| `research:compare` | `tickers` (2–5), `timeframe` | Side-by-side comparison |
| `research:resolve` | `query` | Ticker resolution |

## Output contract

Every success returns:

- `schema_version`, `agency`, `capability`
- `report` / `comparison` / `resolution` (structured, JSON-safe)
- `warnings` (pipeline + mapping warnings)
- `provenance` (sources, `data_as_of`, engine version)
- `audit`: `request_id`, `task_id`, `source_agent`, `engine_version`,
  `data_timestamp`, `report_hash` (SHA-256 over canonical report JSON),
  `outcome`, `duration_seconds`

## Failure contract

Typed errors, no silent fallback. Every error carries `retryable`:

| Code | Meaning | Retryable |
|---|---|---|
| `INVALID_TASK` | Malformed task envelope | no |
| `UNKNOWN_TARGET` | Not addressed to this agency | no |
| `UNKNOWN_ACTION` | Action not supported | no |
| `INVALID_INPUT` | Payload validation failed | no |
| `RESOLUTION_FAILED` | Ticker unresolvable | no |
| `PROVIDER_ERROR` | Upstream market/filing data failed | **yes** |
| `TIMEOUT` | Exceeded task deadline (default 300 s) | **yes** |
| `INTERNAL_ERROR` | Unexpected failure | no |

Safe retry policy: only `PROVIDER_ERROR` and `TIMEOUT` are retryable.
`status` is `"timeout"` (not `"error"`) on deadline expiry, matching the
OGSA `TaskResult` union.

## Manifest

`research_analyst.agency.agency_manifest()` returns the JSON-serializable
self-description (agency id, OGSA category/capabilities, action schemas,
capability and audit contracts, constraints) for registration/discovery.

## Guarantees

- Educational output only: never buy/sell/hold guidance, never executes trades.
- Ad-free, affiliate-free output.
- Capabilities are limited to market read, filing read, model inference and
  report write — no ambient access.
