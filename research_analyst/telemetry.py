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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""First-party telemetry (Stream C) — measurement without tracking.

RA stays tracking-free for its USERS: no third-party analytics, no
cookies, no fingerprinting, nothing shipped off the box. What the
operator needs to run the service honestly — request counts, error
rates, pipeline timings — is recorded server-side, on-box, as
aggregates plus a structured request log with strict content rules:

  - route PATH only (never the query string, never a request body)
  - the key RECORD id when a valid key was presented (never the raw
    key; an invalid key records as "invalid", an absent one as
    "anonymous")
  - NO IP addresses persisted, in any form
  - status + duration, nothing about the person

The aggregates answer the pricing model's open questions (CPU-seconds
per report, cache-hit rate, per-route load) so the production-cost
model can be re-run on MEASURED numbers before live charging
(owner's production-cost rule, 2026-10-15). The summary is served
only to the operator key (RA_TELEMETRY_ADMIN_KEY).

Files (in the state directory, beside the key store by default):
  requests-YYYY-MM-DD.jsonl — one line per request, daily rotation
  telemetry.json — persisted aggregates (requests, durations,
  pipeline timings, cache hits/misses, error counts), pruned to the
  retention window on load. Retention default 90 days (operator
  proposal; the owner's pick lands in RA_TELEMETRY_RETENTION_DAYS).

Every write is best-effort: telemetry must never break a request.
"""
# Module: research_analyst/telemetry.py | Version: 0.1.0 | Updated: 2026-10-15

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


class TelemetryRecorder:
    """Thread-safe telemetry sink: JSONL request log + JSON aggregates."""

    def __init__(
        self, directory: str | Path | None = None, retention_days: int = 90
    ) -> None:
        self._dir = Path(directory) if directory else None
        self._retention_days = max(1, retention_days)
        self._lock = threading.RLock()
        # Aggregate shapes (all keyed by UTC day):
        #   requests: {day: {"route|status_class": count}}
        #   durations: {day: {route: [count, ms_sum, ms_max]}}
        #   timings: {day: {stage: [count, wall_ms_sum, cpu_ms_sum, wall_ms_max]}}
        #   cache: {day: {"hits": n, "misses": n}}
        #   errors: {day: {"route|ExceptionType": count}}
        self._agg: dict[str, dict[str, Any]] = {
            "requests": {},
            "durations": {},
            "timings": {},
            "cache": {},
            "errors": {},
        }
        # Aggregates flush at most every 25 records or 30 seconds —
        # the JSONL detail log is appended immediately, aggregates are
        # small and rebuild-tolerant, so a crash loses <30s of counts.
        self._dirty = 0
        self._last_save = time.monotonic()
        if self._dir is not None:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._load()
            self._prune_logs()

    # -- recording ----------------------------------------------------

    def record_request(
        self,
        *,
        route: str,
        method: str,
        status: int,
        duration_ms: float,
        key_id: str,
    ) -> None:
        """One request: a JSONL line + the day's aggregates."""
        day = _today()
        status_class = f"{status // 100}xx"
        with self._lock:
            req = self._agg["requests"].setdefault(day, {})
            k = f"{route}|{status_class}"
            req[k] = req.get(k, 0) + 1
            dur = self._agg["durations"].setdefault(day, {})
            slot = dur.setdefault(route, [0, 0.0, 0.0])
            slot[0] += 1
            slot[1] += duration_ms
            slot[2] = max(slot[2], duration_ms)
            self._mark_dirty()
        if self._dir is not None:
            line = json.dumps(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "route": route,
                    "method": method,
                    "status": status,
                    "ms": round(duration_ms, 1),
                    "key_id": key_id,
                }
            )
            try:
                with open(
                    self._dir / f"requests-{day}.jsonl", "a", encoding="utf-8"
                ) as fh:
                    fh.write(line + "\n")
            except OSError:
                logger.warning("telemetry: request log write failed", exc_info=True)

    def record_timing(self, stage: str, wall_ms: float, cpu_ms: float) -> None:
        """One pipeline run's wall + CPU time (the pricing-model unit)."""
        day = _today()
        with self._lock:
            tim = self._agg["timings"].setdefault(day, {})
            slot = tim.setdefault(stage, [0, 0.0, 0.0, 0.0])
            slot[0] += 1
            slot[1] += wall_ms
            slot[2] += cpu_ms
            slot[3] = max(slot[3], wall_ms)
            self._mark_dirty()

    def record_cache(self, hit: bool) -> None:
        day = _today()
        with self._lock:
            cache = self._agg["cache"].setdefault(day, {"hits": 0, "misses": 0})
            cache["hits" if hit else "misses"] += 1
            self._mark_dirty()

    def record_error(self, route: str, exc_type: str) -> None:
        day = _today()
        with self._lock:
            err = self._agg["errors"].setdefault(day, {})
            k = f"{route}|{exc_type}"
            err[k] = err.get(k, 0) + 1
            self._mark_dirty()

    # -- summary --------------------------------------------------------

    def summary(self, day: str | None = None) -> dict[str, Any]:
        """The operator summary for one UTC day (default: today)."""
        day = day or _today()
        with self._lock:
            requests = dict(self._agg["requests"].get(day, {}))
            durations = {
                route: {
                    "count": slot[0],
                    "avg_ms": round(slot[1] / slot[0], 1) if slot[0] else 0.0,
                    "max_ms": round(slot[2], 1),
                }
                for route, slot in self._agg["durations"].get(day, {}).items()
            }
            timings = {
                stage: {
                    "runs": slot[0],
                    "avg_wall_ms": round(slot[1] / slot[0], 1) if slot[0] else 0.0,
                    "avg_cpu_ms": round(slot[2] / slot[0], 1) if slot[0] else 0.0,
                    "avg_cpu_s": round(slot[2] / slot[0] / 1000, 3) if slot[0] else 0.0,
                    "max_wall_ms": round(slot[3], 1),
                }
                for stage, slot in self._agg["timings"].get(day, {}).items()
            }
            cache = dict(self._agg["cache"].get(day, {"hits": 0, "misses": 0}))
            total_cache = cache.get("hits", 0) + cache.get("misses", 0)
            errors = dict(self._agg["errors"].get(day, {}))
        return {
            "day_utc": day,
            "requests_total": sum(requests.values()),
            "requests": requests,
            "route_durations": durations,
            "pipeline_timings": timings,
            "cache": {
                **cache,
                "hit_rate": round(cache.get("hits", 0) / total_cache, 3)
                if total_cache
                else None,
            },
            "errors": errors,
        }

    # -- persistence ----------------------------------------------------

    def _path(self) -> Path | None:
        return (self._dir / "telemetry.json") if self._dir is not None else None

    def _load(self) -> None:
        path = self._path()
        if path is None or not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("telemetry: aggregate file unreadable; starting fresh")
            return
        if isinstance(raw, dict):
            for section in self._agg:
                if isinstance(raw.get(section), dict):
                    self._agg[section] = raw[section]
        self._prune()

    def _prune(self) -> None:
        cutoff = (
            datetime.now(UTC).date() - timedelta(days=self._retention_days)
        ).isoformat()
        for section in self._agg.values():
            for day in list(section):
                if day < cutoff:
                    del section[day]

    def _prune_logs(self) -> None:
        if self._dir is None:
            return
        cutoff = (
            datetime.now(UTC).date() - timedelta(days=self._retention_days)
        ).isoformat()
        try:
            for file in self._dir.glob("requests-*.jsonl"):
                day = file.stem.removeprefix("requests-")
                if day < cutoff:
                    file.unlink(missing_ok=True)
        except OSError:
            logger.warning("telemetry: log prune failed", exc_info=True)

    def _mark_dirty(self) -> None:
        """Note a change; flush when the batch threshold is reached.

        Caller must hold the lock.
        """
        self._dirty += 1
        if self._dirty >= 25 or time.monotonic() - self._last_save >= 30:
            self._save()

    def flush(self) -> None:
        """Persist aggregates now (shutdown hooks and tests)."""
        with self._lock:
            self._save()

    def _save(self) -> None:
        path = self._path()
        self._dirty = 0
        self._last_save = time.monotonic()
        if path is None:
            return
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._agg), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            logger.warning("telemetry: aggregate save failed", exc_info=True)
