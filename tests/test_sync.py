# Copyright (C) 2026 Nrupal Akolkar <nrupalakolkar@gmail.com>
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

"""Tests for the local-first sync CLI (Phase 2).

* watchlist parsing (validation)
* full sync run with a stubbed orchestrator -> SQLite sink + NDJSON bundles
* incremental skip (fresh tickers skipped on the second run)
* per-ticker failure isolation
"""
# Module: tests/test_sync.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from research_analyst.enums import ReportType, SecurityType
from research_analyst.models import (
    ReportOutput,
    ResearchMetadata,
    ResearchResponse,
)
from research_analyst.sync import SyncResult, _read_watchlist, run_sync


class StubOrchestrator:
    """Stands in for ResearchOrchestrator — returns a typed ResearchResponse."""

    def __init__(self, fail: set[str] | None = None) -> None:
        self.fail = fail or set()

    async def run(self, request):
        if request.ticker in self.fail:
            raise RuntimeError("boom")
        report = ReportOutput(
            report_type=ReportType.COMPREHENSIVE,
            ticker=request.ticker,
            title=f"{request.ticker} — Comprehensive",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            sections=[],
        )
        return ResearchResponse(
            ticker=request.ticker,
            security_type=SecurityType.EQUITY,
            company_name="Stub Corp",
            currency="USD",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            reports=[report],
            metadata=ResearchMetadata(data_sources=["stub"]),
        )


def _watchlist(tmp_path: Path, tickers: list[str]) -> Path:
    p = tmp_path / "wl.json"
    p.write_text(json.dumps({"tickers": tickers}), encoding="utf-8")
    return p


def _sync(tmp_path: Path, tickers: list[str], fail: set[str] | None = None):
    """Run a sync against a stub orchestrator (asyncio runner)."""
    wl = _watchlist(tmp_path, tickers)
    out = tmp_path / "data"
    result = run_sync(
        wl, out,
        orchestrator=StubOrchestrator(fail),
        runner=asyncio.run,
        max_age_hours=0.0,  # always stale -> never skips
    )
    return result, out


def test_read_watchlist_valid():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "wl.json"
        p.write_text(json.dumps({"tickers": ["aapl", "msft"]}), encoding="utf-8")
        data = _read_watchlist(p)
        assert data["tickers"] == ["AAPL", "MSFT"]


def test_read_watchlist_invalid():
    import tempfile

    import pytest

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "wl.json"
        p.write_text(json.dumps({"tickers": []}), encoding="utf-8")
        with pytest.raises(ValueError):
            _read_watchlist(p)


def test_sync_writes_sqlite_and_ndjson(tmp_path):
    result, out = _sync(tmp_path, ["AAPL", "MSFT"])
    assert result.succeeded == ["AAPL", "MSFT"]
    assert result.failed == {}
    assert (out / "bundle.db").exists()
    assert (out / "AAPL.ndjson").exists()
    assert (out / "MSFT.ndjson").exists()

    conn = sqlite3.connect(out / "bundle.db")
    rows = conn.execute("SELECT ticker FROM bundles ORDER BY ticker").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["AAPL", "MSFT"]

    payload = json.loads((out / "AAPL.ndjson").read_text().strip().split("\n")[0])
    assert payload["ticker"] == "AAPL"
    assert payload["reports"][0]["report_type"] == "comprehensive"


def test_sync_incremental_skip(tmp_path):
    _, out = _sync(tmp_path, ["AAPL"])
    # second run with a positive max-age skips the fresh ticker
    wl = _watchlist(tmp_path, ["AAPL"])
    result = run_sync(
        wl, out,
        orchestrator=StubOrchestrator(),
        runner=asyncio.run,
        max_age_hours=24.0,
    )
    assert result.skipped_fresh == ["AAPL"]
    assert result.succeeded == []


def test_sync_isolates_failures(tmp_path):
    result, out = _sync(tmp_path, ["AAPL", "BROKEN"], fail={"BROKEN"})
    assert result.succeeded == ["AAPL"]
    assert "BROKEN" in result.failed
    assert not (out / "BROKEN.ndjson").exists()


def test_sync_result_serializable():
    r = SyncResult()
    r.succeeded = ["A"]
    r.failed = {"B": "err"}
    d = r.to_dict()
    assert d["summary"] == {"ok": 1, "skipped": 0, "failed": 1}
    assert d["schema_version"] == "1.0"
