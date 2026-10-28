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

"""Watchlists (Stream B / F1.7).

A watchlist is the set of tickers an API key is watching. Like saved
scenarios, ownership needs an identity — KeyStore keys are the only
identities RA has (no account system). The quotes view prices the
list through the same labelled cascade as reports, so a watched
price always carries the source that served it.

Alerts evaluate this list; the alert channel is the owner's open
choice (email vs in-app) and plugs in above this store — the store
itself is channel-free.

Persistence mirrors the fleet pattern (scenarios/grants/metering):
a JSON file in the state directory, best-effort load/save, in-memory
when no path is configured.
"""
# Module: research_analyst/watchlists.py | Version: 0.1.0 | Updated: 2026-10-16

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_WATCHLIST_TICKERS_PER_KEY = 100


@dataclass
class WatchEntry:
    key_id: str
    ticker: str
    added_at_utc: str = ""


class WatchlistStore:
    """Persisted per-key watchlists (JSON file; in-memory for tests)."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else None
        self._entries: dict[tuple[str, str], WatchEntry] = {}
        self._lock = threading.RLock()
        if self._path and self._path.exists():
            self._load()

    def add(self, key_id: str, ticker: str) -> tuple[WatchEntry, bool] | None:
        """Add a ticker to the key's watchlist.

        Returns (entry, created): created is False when the ticker was
        already watched (the add is idempotent). None when the per-key
        cap is reached.
        """
        with self._lock:
            existing = self._entries.get((key_id, ticker))
            if existing is not None:
                return existing, False
            owned = sum(1 for e in self._entries.values() if e.key_id == key_id)
            if owned >= MAX_WATCHLIST_TICKERS_PER_KEY:
                return None
            entry = WatchEntry(
                key_id=key_id,
                ticker=ticker,
                added_at_utc=datetime.now(UTC).isoformat(),
            )
            self._entries[(key_id, ticker)] = entry
            self._save()
            return entry, True

    def list_for_key(self, key_id: str) -> list[WatchEntry]:
        with self._lock:
            owned = [e for e in self._entries.values() if e.key_id == key_id]
        return sorted(owned, key=lambda e: e.added_at_utc)

    def remove(self, key_id: str, ticker: str) -> bool:
        """Remove the key's own entry. Absent is simply False (-> 404)."""
        with self._lock:
            if (key_id, ticker) not in self._entries:
                return False
            del self._entries[(key_id, ticker)]
            self._save()
            return True

    def _load(self) -> None:
        try:
            assert self._path is not None
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not load watchlists file %s: %s", self._path, e)
            return
        for d in data.get("entries", []):
            try:
                entry = WatchEntry(**d)
            except Exception:
                continue
            self._entries[(entry.key_id, entry.ticker)] = entry

    def _save(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(
                    {"entries": [asdict(e) for e in self._entries.values()]},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Could not persist watchlists file %s: %s", self._path, e)


def watch_entry_public(entry: WatchEntry) -> dict[str, Any]:
    """The wire shape for one watched ticker."""
    return {"ticker": entry.ticker, "added_at_utc": entry.added_at_utc}
