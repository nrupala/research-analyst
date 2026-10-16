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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""Saved scenarios + shareable links (Stream B / F1.5).

A saved scenario is a named research setup owned by an API key:
ticker, report type, timeframe, and the caller's own custom
assumptions. Saving needs a key because ownership needs an identity
— KeyStore keys are the only identities RA has (no account system).

Each scenario carries an unguessable share token. The share link
(/api/research/shared/<token>) replays the scenario for anyone
holding the link — the link IS the credential, the standard
share-link contract. What a share run can cost is bounded by
construction: the scenario's parameters are fixed, so every run
lands on the same report-cache key and the EOD cache absorbs
repeat views; an uncached run is metered to the owner as "shared".

Persistence mirrors the fleet pattern (grants/metering): a JSON
file in the state directory, best-effort load/save, in-memory when
no path is configured. Deleting a scenario kills its share link.
"""
# Module: research_analyst/scenarios.py | Version: 0.1.0 | Updated: 2026-10-15

from __future__ import annotations

import json
import logging
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_SCENARIOS_PER_KEY = 100


@dataclass
class SavedScenario:
    scenario_id: str
    key_id: str
    name: str
    ticker: str
    report_type: str | None = None
    timeframe: str = "1Y"
    custom_assumptions: dict[str, Any] = field(default_factory=dict)
    share_token: str = ""
    created_at_utc: str = ""


class ScenarioStore:
    """Persisted saved scenarios (JSON file; in-memory for tests)."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else None
        self._scenarios: dict[str, SavedScenario] = {}
        self._lock = threading.RLock()
        if self._path and self._path.exists():
            self._load()

    def create(
        self,
        *,
        key_id: str,
        name: str,
        ticker: str,
        report_type: str | None,
        timeframe: str,
        custom_assumptions: dict[str, Any],
    ) -> SavedScenario | None:
        """Insert a scenario; None when the per-key cap is reached."""
        with self._lock:
            owned = sum(1 for s in self._scenarios.values() if s.key_id == key_id)
            if owned >= MAX_SCENARIOS_PER_KEY:
                return None
            scenario = SavedScenario(
                scenario_id=f"scn_{secrets.token_urlsafe(9)}",
                key_id=key_id,
                name=name,
                ticker=ticker,
                report_type=report_type,
                timeframe=timeframe,
                custom_assumptions=custom_assumptions,
                share_token=secrets.token_urlsafe(24),
                created_at_utc=datetime.now(UTC).isoformat(),
            )
            self._scenarios[scenario.scenario_id] = scenario
            self._save()
            return scenario

    def list_for_key(self, key_id: str) -> list[SavedScenario]:
        with self._lock:
            owned = [s for s in self._scenarios.values() if s.key_id == key_id]
        return sorted(owned, key=lambda s: s.created_at_utc)

    def delete(self, scenario_id: str, key_id: str) -> bool:
        """Delete only the owner's own scenario. A foreign or missing
        id is indistinguishable — both are simply False (-> 404)."""
        with self._lock:
            scenario = self._scenarios.get(scenario_id)
            if scenario is None or scenario.key_id != key_id:
                return False
            del self._scenarios[scenario_id]
            self._save()
            return True

    def by_share_token(self, token: str) -> SavedScenario | None:
        with self._lock:
            for scenario in self._scenarios.values():
                if secrets.compare_digest(scenario.share_token, token):
                    return scenario
        return None

    def _load(self) -> None:
        try:
            assert self._path is not None
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not load scenarios file %s: %s", self._path, e)
            return
        for d in data.get("scenarios", []):
            try:
                scenario = SavedScenario(**d)
            except Exception:
                continue
            self._scenarios[scenario.scenario_id] = scenario

    def _save(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(
                    {"scenarios": [asdict(s) for s in self._scenarios.values()]},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Could not persist scenarios file %s: %s", self._path, e)


def scenario_public(scenario: SavedScenario) -> dict[str, Any]:
    """The wire shape: the scenario plus its share path."""
    data = asdict(scenario)
    data["share_path"] = f"/api/research/shared/{scenario.share_token}"
    return data
