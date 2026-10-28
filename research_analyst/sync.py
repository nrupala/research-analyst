# Copyright (C) 2026 2351485 ALBERTA INC.
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

"""Local-first sync CLI (Phase 2).

``research-analyst sync`` pulls structured bundles for a watchlist into a local
sink with zero cloud telemetry — the sovereign batch-export story.

  * Input: a watchlist JSON file ({tickers: [...], report_type, timeframe})
  * Output: SQLite (stdlib sqlite3, zero-dep) + NDJSON/JSON bundle per ticker
  * Incremental: reuses the market provider's _DiskCache so overnight runs
    only fetch what's fresh
  * Never raises on a single ticker failure — the run continues and reports
    per-ticker status

The orchestrator is injectable so tests can run the full sync without network.
"""
# Module: research_analyst/sync.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from .enums import ReportType
from .models import ResearchRequest
from .orchestrator import ResearchOrchestrator


class SyncResult:
    """Per-run outcome summary (typed, serializable)."""

    def __init__(self) -> None:
        self.succeeded: list[str] = []
        self.failed: dict[str, str] = {}
        self.skipped_fresh: list[str] = []
        self.schema_version = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "succeeded": self.succeeded,
            "skipped_fresh": self.skipped_fresh,
            "failed": self.failed,
            "summary": {
                "ok": len(self.succeeded),
                "skipped": len(self.skipped_fresh),
                "failed": len(self.failed),
            },
        }


def _read_watchlist(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    tickers = data.get("tickers")
    if not isinstance(tickers, list) or not tickers:
        raise ValueError("watchlist must contain a non-empty 'tickers' list")
    return {
        "tickers": [str(t).upper() for t in tickers],
        "report_type": data.get("report_type", "comprehensive"),
        "timeframe": data.get("timeframe", "1Y"),
    }


def _open_sink(out_dir: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(out_dir / "bundle.db")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bundles (
            ticker TEXT PRIMARY KEY,
            report_type TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            synced_at TEXT NOT NULL
        )
        """
    )
    return conn


def _emit_bundle(
    out_dir: Path,
    ticker: str,
    report_type: str,
    payload: dict[str, Any],
    conn: sqlite3.Connection,
) -> None:
    import datetime as _dt

    now = _dt.datetime.now(_dt.UTC).isoformat()
    row = (
        ticker,
        report_type,
        payload.get("generated_at", ""),
        json.dumps(payload),
        now,
    )
    conn.execute(
        "INSERT INTO bundles (ticker, report_type, generated_at, payload_json, synced_at) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(ticker) DO UPDATE SET "
        "report_type=excluded.report_type, generated_at=excluded.generated_at, "
        "payload_json=excluded.payload_json, synced_at=excluded.synced_at",
        row,
    )
    conn.commit()
    # NDJSON line for scriptable pipelines / DuckDB ingestion
    ndjson = out_dir / f"{ticker}.ndjson"
    with ndjson.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


async def _sync_one(
    orchestrator: ResearchOrchestrator,
    ticker: str,
    report_type: str,
    timeframe: str,
) -> dict[str, Any]:
    """Run one research request, returning the typed bundle payload."""
    from .enums import Timeframe

    tf_map = {
        "1M": Timeframe.ONE_MONTH, "3M": Timeframe.THREE_MONTHS,
        "6M": Timeframe.SIX_MONTHS, "1Y": Timeframe.ONE_YEAR,
        "3Y": Timeframe.THREE_YEARS, "5Y": Timeframe.FIVE_YEARS,
        "10Y": Timeframe.TEN_YEARS,
    }
    request = ResearchRequest(
        ticker=ticker,
        report_types=ReportType.from_user_input(report_type),
        timeframe=tf_map.get(timeframe.upper(), Timeframe.ONE_YEAR),
    )
    result = await orchestrator.run(request)
    return {
        "ticker": result.ticker,
        "company_name": result.company_name,
        "security_type": result.security_type.value if result.security_type else "",
        "generated_at": result.generated_at.isoformat(),
        "currency": result.currency,
        "reports": [r.model_dump(mode="json") for r in result.reports],
    }


def _is_fresh(
    out_dir: Path, ticker: str, cache: Any, max_age_hours: float = 24.0
) -> bool:
    """True when the ticker was synced within max_age_hours (incremental skip)."""
    import time

    path = out_dir / f"{ticker}.ndjson"
    if not path.exists():
        return False
    try:
        age_h = (time.time() - path.stat().st_mtime) / 3600
    except OSError:
        return False
    return age_h < max_age_hours


def run_sync(
    watchlist_path: Path,
    out_dir: Path,
    *,
    orchestrator: ResearchOrchestrator | None = None,
    max_age_hours: float = 24.0,
    runner: Callable[[Any], Any] = asyncio.run,
) -> SyncResult:
    """Synchronous entry point (calls the async pipeline)."""
    return cast("SyncResult", runner(_run_sync_async(
        watchlist_path, out_dir,
        orchestrator=orchestrator, max_age_hours=max_age_hours,
    )))


async def _run_sync_async(
    watchlist_path: Path,
    out_dir: Path,
    *,
    orchestrator: ResearchOrchestrator | None = None,
    max_age_hours: float = 24.0,
) -> SyncResult:
    result = SyncResult()
    watchlist = _read_watchlist(watchlist_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    orch = orchestrator or ResearchOrchestrator()

    cache = getattr(getattr(orch, "market", None), "cache", None)
    conn = _open_sink(out_dir)

    for ticker in watchlist["tickers"]:
        if _is_fresh(out_dir, ticker, cache, max_age_hours):
            result.skipped_fresh.append(ticker)
            continue
        try:
            payload = await _sync_one(
                orch, ticker, watchlist["report_type"], watchlist["timeframe"]
            )
            _emit_bundle(out_dir, ticker, watchlist["report_type"], payload, conn)
            result.succeeded.append(ticker)
        except Exception as e:
            result.failed[ticker] = f"{type(e).__name__}: {e}"[:200]

    conn.close()
    return result
