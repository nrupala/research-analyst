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

"""API keys, entitlements, metering and white-label hooks for Research Analyst.

Product surface (per the RA monetization plan):
- RA Pro subscription (test anchor: $15/mo or $120/yr — not a public-price
  commitment) unlocks metered API use, the source-data bundle and white-label.
- TWF Pro bundles RA Pro: a key carrying the ``twf.pro`` entitlement unlocks
  everything ``ra.pro`` unlocks (bundle mapping, no billing implemented here).
- Merchant of Record (Paddle / Lemon Squeezy) is undecided and out of scope:
  this module only models keys, entitlements and usage — never charges.

Security properties (do not weaken):
- Raw API keys are returned ONCE at issuance and never stored, logged or
  persisted. Only SHA-256 hashes are kept (in memory and in the optional
  JSON key file).
- Verification uses constant-time comparison.
- Keys are revocable; revoked keys fail closed.
- No secrets in code, tests or fixtures.
"""
# Module: research_analyst/entitlements.py | Version: 1.0 | Updated: 2026-09-25

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entitlement flags
# ---------------------------------------------------------------------------

RA_PRO = "ra.pro"  # RA Pro subscription
TWF_PRO = "twf.pro"  # TWF Pro bundle (unlocks RA Pro, see below)
SOURCE_DATA = "source.data"  # source-data bundle download
WHITE_LABEL = "white.label"  # white-label branding on exports

# TWF Pro is a bundle: carrying twf.pro unlocks the RA Pro surface.
# (Billing itself — Paddle/Lemon Squeezy — is undecided and not implemented.)
BUNDLE_UNLOCKS: dict[str, set[str]] = {
    TWF_PRO: {RA_PRO, SOURCE_DATA},
}

KEY_PREFIX = "ra_live_"


# ---------------------------------------------------------------------------
# API keys — hashed at rest, revocable, never logged
# ---------------------------------------------------------------------------


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


@dataclass
class APIKeyRecord:
    """A stored API key. Only the hash is persisted — never the raw key."""

    key_id: str
    key_hash: str
    label: str
    created_at_utc: str
    entitlements: set[str] = field(default_factory=set)
    revoked: bool = False
    revoked_at_utc: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "key_hash": self.key_hash,
            "label": self.label,
            "created_at_utc": self.created_at_utc,
            "entitlements": sorted(self.entitlements),
            "revoked": self.revoked,
            "revoked_at_utc": self.revoked_at_utc,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> APIKeyRecord:
        return cls(
            key_id=d["key_id"],
            key_hash=d["key_hash"],
            label=d.get("label", ""),
            created_at_utc=d.get("created_at_utc", ""),
            entitlements=set(d.get("entitlements", [])),
            revoked=bool(d.get("revoked", False)),
            revoked_at_utc=d.get("revoked_at_utc"),
        )


class KeyStore:
    """Issue, verify and revoke API keys. Hashes only, in memory + JSON file."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else None
        self._by_hash: dict[str, APIKeyRecord] = {}
        self._by_id: dict[str, APIKeyRecord] = {}
        if self._path and self._path.exists():
            self._load()

    # -- issuance ---------------------------------------------------------
    def create(self, label: str, entitlements: set[str] | None = None) -> tuple[APIKeyRecord, str]:
        """Create a key. Returns (record, raw_key); the raw key is shown once."""
        raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
        record = APIKeyRecord(
            key_id="key_" + secrets.token_hex(6),
            key_hash=_hash_key(raw_key),
            label=label,
            created_at_utc=datetime.now(UTC).isoformat(),
            entitlements=set(entitlements or set()),
        )
        self._by_hash[record.key_hash] = record
        self._by_id[record.key_id] = record
        self._save()
        logger.info("API key issued: key_id=%s label=%s", record.key_id, label)
        return record, raw_key

    # -- verification ------------------------------------------------------
    def verify(self, raw_key: str) -> APIKeyRecord | None:
        """Return the key record for a valid, non-revoked key, else None."""
        if not raw_key or not raw_key.startswith(KEY_PREFIX):
            return None
        digest = _hash_key(raw_key)
        # Constant-time comparison against stored hashes.
        for stored_hash, record in self._by_hash.items():
            if hmac.compare_digest(stored_hash, digest):
                if record.revoked:
                    return None
                return record
        return None

    # -- revocation ----------------------------------------------------------
    def revoke(self, key_id: str) -> bool:
        record = self._by_id.get(key_id)
        if record is None or record.revoked:
            return False
        record.revoked = True
        record.revoked_at_utc = datetime.now(UTC).isoformat()
        self._save()
        logger.info("API key revoked: key_id=%s", key_id)
        return True

    def get(self, key_id: str) -> APIKeyRecord | None:
        return self._by_id.get(key_id)

    # -- persistence (hashes only) -------------------------------------------
    def _load(self) -> None:
        if self._path is None:
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not load API key file %s: %s", self._path, e)
            return
        for d in data.get("keys", []):
            try:
                record = APIKeyRecord.from_dict(d)
            except Exception:
                continue
            self._by_hash[record.key_hash] = record
            self._by_id[record.key_id] = record

    def _save(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"keys": [r.to_dict() for r in self._by_id.values()]}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Could not persist API key file %s: %s", self._path, e)


# ---------------------------------------------------------------------------
# Entitlements — with TWF Pro bundle expansion
# ---------------------------------------------------------------------------


def effective_entitlements(record: APIKeyRecord) -> set[str]:
    """The record's entitlements plus anything unlocked via bundle mapping."""
    effective = set(record.entitlements)
    for flag, unlocks in BUNDLE_UNLOCKS.items():
        if flag in effective:
            effective.update(unlocks)
    return effective


def has_entitlement(record: APIKeyRecord | None, flag: str) -> bool:
    """Check an entitlement flag (bundle-aware). None record -> False."""
    if record is None or record.revoked:
        return False
    return flag in effective_entitlements(record)


# ---------------------------------------------------------------------------
# Metering — usage foundation (counts per key per endpoint per day)
# ---------------------------------------------------------------------------

MeterSink = Callable[[str, str, str], None]  # (key_id, endpoint, day) -> None


class MeteringRecorder:
    """Record API usage. In-memory counters with a pluggable sink.

    The sink lets a future billing backend receive usage events without
    changing call sites. The default sink is a no-op.
    """

    def __init__(self, sink: MeterSink | None = None) -> None:
        self._counts: dict[tuple[str, str, str], int] = {}
        self._sink = sink or (lambda key_id, endpoint, day: None)

    @staticmethod
    def _today_utc() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def record(self, key_id: str, endpoint: str, *, day: str | None = None) -> None:
        day = day or self._today_utc()
        k = (key_id, endpoint, day)
        self._counts[k] = self._counts.get(k, 0) + 1
        try:
            self._sink(key_id, endpoint, day)
        except Exception as e:
            logger.warning("Metering sink failed: %s", e)

    def usage(self, key_id: str, day: str | None = None) -> dict[str, int]:
        """Per-endpoint request counts for a key on a day (default today)."""
        day = day or self._today_utc()
        out: dict[str, int] = {}
        for (k, endpoint, d), count in self._counts.items():
            if k == key_id and d == day:
                out[endpoint] = count
        return out

    def total_requests(self, key_id: str, day: str | None = None) -> int:
        return sum(self.usage(key_id, day=day).values())


# ---------------------------------------------------------------------------
# White-label — branding hooks that never alter evidence
# ---------------------------------------------------------------------------


@dataclass
class WhiteLabelProfile:
    """Branding overrides for exported reports.

    Only chrome changes (name, URLs, footer, accent color, support link).
    Report evidence — numbers, sources, methodology, disclaimers — is never
    touched by white-labeling.
    """

    org_name: str = ""
    prepared_on_url: str = ""  # replaces the default "prepared on" link
    footer_note: str = ""  # appended to the export footer
    show_support_link: bool = True  # show the default support/donate link
    accent_color: str = ""  # CSS accent override, e.g. "#0b5fff"

    def is_active(self) -> bool:
        return bool(
            self.org_name
            or self.prepared_on_url
            or self.footer_note
            or self.accent_color
            or not self.show_support_link
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "org_name": self.org_name,
            "prepared_on_url": self.prepared_on_url,
            "footer_note": self.footer_note,
            "show_support_link": self.show_support_link,
            "accent_color": self.accent_color,
        }
