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

"""API keys, entitlements, metering and white-label hooks for Research Analyst.

Product surface (family-mirrored pricing, adopted 2026-10-15):
- Free: reports, quant, compare — keyless.
- RA Pro (app) $19/mo, RA Team (app) $79/mo: saved scenarios, watchlists,
  alerts, exports, shareable links (the ``ra.pro`` entitlement gates the
  Pro feature surface in the app/API).
- RA API Pro $58/mo per 100,000 calls, RA API Team $198/mo per 1,000,000
  calls: metered access to RA's own analysis (reports/quant). Same tools
  on every tier; volume is the only difference.
- TWF Pro bundles RA Pro: a key carrying the ``twf.pro`` entitlement
  unlocks everything ``ra.pro`` unlocks (bundle mapping below).
- Billing rail is Stripe (decided 2026-10-14); charging itself lives
  outside this module — this module only models keys, entitlements and
  usage.
- Source data is NEVER sold (owner ruling, 2026-10-15): the datasets RA
  consumes stay under their own licenses; entitlements gate only the
  information and features RA itself produces.

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
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entitlement flags
# ---------------------------------------------------------------------------

RA_PRO = "ra.pro"  # RA Pro subscription
TWF_PRO = "twf.pro"  # TWF Pro bundle (unlocks RA Pro, see below)
API_ACCESS = "api.access"  # metered analysis-API access (Stream A): RA's own work product
WHITE_LABEL = "white.label"  # white-label branding on exports

# TWF Pro is a bundle: carrying twf.pro unlocks the RA Pro surface
# plus metered analysis-API access (owner flavors, 2026-10-15).
# (Billing rail: Stripe, decided 2026-10-14; charging is not implemented here.)
BUNDLE_UNLOCKS: dict[str, set[str]] = {
    TWF_PRO: {RA_PRO, API_ACCESS},
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
    # Billing linkage (Stream A): the paid plan that issued this key and
    # the Stripe objects behind it, so lifecycle webhooks can find and
    # suspend the key. Ids only — never secrets, never card data.
    plan: str | None = None
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    monthly_call_allowance: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "key_hash": self.key_hash,
            "label": self.label,
            "created_at_utc": self.created_at_utc,
            "entitlements": sorted(self.entitlements),
            "revoked": self.revoked,
            "revoked_at_utc": self.revoked_at_utc,
            "plan": self.plan,
            "stripe_customer_id": self.stripe_customer_id,
            "stripe_subscription_id": self.stripe_subscription_id,
            "monthly_call_allowance": self.monthly_call_allowance,
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
            plan=d.get("plan"),
            stripe_customer_id=d.get("stripe_customer_id"),
            stripe_subscription_id=d.get("stripe_subscription_id"),
            monthly_call_allowance=d.get("monthly_call_allowance"),
        )


class KeyStore:
    """Issue, verify and revoke API keys. Hashes only, in memory + JSON file.

    Freshness: when the store is file-backed, verify()/get()/revoke()
    re-read the file if its mtime changed since the last load. Keys
    minted or revoked by another process (the Stripe webhook minter, the
    ops CLI) therefore take effect without a service restart
    (Stream A design, 2026-10-15). The freshness check is one stat call
    per verify; the reload itself happens only on an actual change.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else None
        self._by_hash: dict[str, APIKeyRecord] = {}
        self._by_id: dict[str, APIKeyRecord] = {}
        self._lock = threading.RLock()
        self._file_mtime_ns: int | None = None
        if self._path and self._path.exists():
            self._load()
            self._sync_mtime()

    # -- freshness ---------------------------------------------------------
    def _stat_mtime_ns(self) -> int | None:
        if not self._path:
            return None
        try:
            return self._path.stat().st_mtime_ns
        except OSError:
            return None

    def _sync_mtime(self) -> None:
        self._file_mtime_ns = self._stat_mtime_ns()

    def _maybe_reload(self) -> None:
        """Reload from disk if another writer changed the key file."""
        if not self._path:
            return
        if self._stat_mtime_ns() == self._file_mtime_ns:
            return
        with self._lock:
            if self._stat_mtime_ns() == self._file_mtime_ns:
                return
            self._by_hash = {}
            self._by_id = {}
            if self._path.exists():
                self._load()
            self._sync_mtime()

    # -- issuance ---------------------------------------------------------
    def create(
        self,
        label: str,
        entitlements: set[str] | None = None,
        *,
        plan: str | None = None,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
        monthly_call_allowance: int | None = None,
    ) -> tuple[APIKeyRecord, str]:
        """Create a key. Returns (record, raw_key); the raw key is shown once."""
        raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
        record = APIKeyRecord(
            key_id="key_" + secrets.token_hex(6),
            key_hash=_hash_key(raw_key),
            label=label,
            created_at_utc=datetime.now(UTC).isoformat(),
            entitlements=set(entitlements or set()),
            plan=plan,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            monthly_call_allowance=monthly_call_allowance,
        )
        with self._lock:
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
        # One stat per verify: if another process minted or revoked a
        # key, the file changed and we reload before answering — a
        # cross-process revocation is honored on the very next call.
        self._maybe_reload()
        with self._lock:
            record = self._find_by_digest(digest)
        if record is None or record.revoked:
            return None
        return record

    def _find_by_digest(self, digest: str) -> APIKeyRecord | None:
        # Constant-time comparison against stored hashes.
        for stored_hash, record in self._by_hash.items():
            if hmac.compare_digest(stored_hash, digest):
                return record
        return None

    # -- revocation ----------------------------------------------------------
    def revoke(self, key_id: str) -> bool:
        self._maybe_reload()
        with self._lock:
            record = self._by_id.get(key_id)
            if record is None or record.revoked:
                return False
            record.revoked = True
            record.revoked_at_utc = datetime.now(UTC).isoformat()
            self._save()
        logger.info("API key revoked: key_id=%s", key_id)
        return True

    def get(self, key_id: str) -> APIKeyRecord | None:
        self._maybe_reload()
        return self._by_id.get(key_id)

    def persist(self, record: APIKeyRecord) -> None:
        """Save in-place changes to a record (plan / allowance updates)."""
        with self._lock:
            if record.key_id in self._by_id:
                self._save()

    def find_by_subscription(self, subscription_id: str) -> APIKeyRecord | None:
        """The key issued for a Stripe subscription, if any (Stream A).

        Used by lifecycle webhooks (cancel / lapse) to locate the key
        that must be suspended. Freshness-checked like verify().
        """
        if not subscription_id:
            return None
        self._maybe_reload()
        with self._lock:
            for record in self._by_id.values():
                if record.stripe_subscription_id == subscription_id:
                    return record
        return None

    # -- persistence (hashes only) -------------------------------------------
    def _load(self) -> None:
        try:
            assert self._path is not None  # narrowed for mypy; caught below if unset
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
            self._sync_mtime()
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
    """Record API usage. Counters per (key, endpoint, day), a pluggable
    sink, and optional JSON-file persistence.

    The sink lets a future billing backend receive usage events without
    changing call sites. The default sink is a no-op.

    Persistence (Stream B / F1.2): monthly allowance enforcement and
    /api/usage read these counters, so when a path is configured the
    counts survive restarts — a restart must never reset a customer's
    usage. Buckets older than ~92 days are pruned on load.
    """

    def __init__(
        self, sink: MeterSink | None = None, path: str | Path | None = None
    ) -> None:
        self._counts: dict[tuple[str, str, str], int] = {}
        self._sink = sink or (lambda key_id, endpoint, day: None)
        self._path = Path(path) if path else None
        if self._path is not None:
            self._load()

    def _load(self) -> None:
        assert self._path is not None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        cutoff = (datetime.now(UTC) - timedelta(days=92)).strftime("%Y-%m-%d")
        for compound, count in (raw.get("counts") or {}).items():
            parts = compound.split("|")
            if len(parts) != 3:
                continue
            key_id, endpoint, day = parts
            if day < cutoff:
                continue
            try:
                self._counts[(key_id, endpoint, day)] = int(count)
            except (TypeError, ValueError):
                continue

    def _save(self) -> None:
        if self._path is None:
            return
        data = {
            "counts": {
                f"{k}|{e}|{d}": c for (k, e, d), c in sorted(self._counts.items())
            }
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as e:
            logger.warning("Metering persistence failed: %s", e)

    @staticmethod
    def _today_utc() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def record(self, key_id: str, endpoint: str, *, day: str | None = None) -> None:
        day = day or self._today_utc()
        k = (key_id, endpoint, day)
        self._counts[k] = self._counts.get(k, 0) + 1
        self._save()
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

    @staticmethod
    def current_month_utc() -> str:
        return datetime.now(UTC).strftime("%Y-%m")

    def month_usage(self, key_id: str, month: str | None = None) -> dict[str, int]:
        """Per-endpoint request counts for a key in a UTC month."""
        month = month or self.current_month_utc()
        out: dict[str, int] = {}
        for (k, endpoint, d), count in self._counts.items():
            if k == key_id and d.startswith(month):
                out[endpoint] = out.get(endpoint, 0) + count
        return out

    def month_total(self, key_id: str, month: str | None = None) -> int:
        return sum(self.month_usage(key_id, month=month).values())


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
