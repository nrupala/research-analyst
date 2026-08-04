"""Per-email API-key entitlements for Research Analyst (Slice 1).

Design (see docs/MONETIZATION.md, "Entitlement model"):
  - Paid unlock is a per-email API key, not accounts/OAuth.
  - Keys are secrets: stored HASHED (sha256), never in plaintext, never logged.
  - The Cloudflare Worker forwards ``Authorization: Bearer <key>`` or
    ``X-RA-Key``; the ORIGIN validates. This module is that origin-side
    validation + gate logic.
  - Enforcement is OFF by default (shadow mode): the gate resolves a tier and
    can log what it WOULD block, but does not block, until
    ``RA_ENTITLEMENTS_ENFORCE`` is turned on. Mirrors the OPA
    shadow-then-enforce pattern used elsewhere in the stack.

Framework-agnostic on purpose: no FastAPI imports, so it is fully unit-testable
offline. ``server.py`` adapts HTTP <-> these primitives.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Protocol


class Tier(str, Enum):
    """Entitlement tiers, ordered by capability."""

    FREE = "free"
    PRO = "pro"


_TIER_RANK = {Tier.FREE: 0, Tier.PRO: 1}


@dataclass(frozen=True)
class Entitlement:
    """A resolved entitlement bound to an email address."""

    email: str
    tier: Tier
    active: bool = True


@dataclass(frozen=True)
class Decision:
    """The outcome of a gate check.

    ``would_block`` records whether the resolved tier is below the required tier
    (i.e. what enforcement WOULD do). ``allowed`` is the effective decision,
    which in shadow mode (enforce=False) is always True.
    """

    tier: Tier
    required: Tier
    allowed: bool
    would_block: bool
    enforced: bool
    reason: str = ""


def hash_key(key: str) -> str:
    """Deterministic sha256 of the raw key. Only the hash is ever stored."""

    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()


def extract_key(header_get: Callable[[str], Optional[str]]) -> Optional[str]:
    """Pull the API key from an ``Authorization: Bearer`` header or ``X-RA-Key``.

    ``header_get`` is any callable shaped like ``request.headers.get``.
    Returns the raw key string, or None when absent.
    """

    auth = header_get("Authorization") or header_get("authorization")
    if auth:
        parts = auth.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            candidate = parts[1].strip()
            if candidate:
                return candidate
    x_key = header_get("X-RA-Key") or header_get("x-ra-key")
    if x_key and x_key.strip():
        return x_key.strip()
    return None


class KeyStore(Protocol):
    """Anything that can resolve a raw key to an Entitlement (or None)."""

    def verify(self, key: str) -> Optional[Entitlement]:
        ...


class InMemoryKeyStore:
    """Test/dev store. Maps hashed key -> Entitlement. Empty by default."""

    def __init__(self, entitlements_by_hash: Optional[dict] = None) -> None:
        self._by_hash: dict = dict(entitlements_by_hash or {})

    def add_key(
        self,
        key: str,
        email: str,
        tier: Tier = Tier.PRO,
        active: bool = True,
    ) -> None:
        self._by_hash[hash_key(key)] = Entitlement(email=email, tier=tier, active=active)

    def verify(self, key: str) -> Optional[Entitlement]:
        ent = self._by_hash.get(hash_key(key))
        if ent is None or ent.active is False:
            return None
        return ent


class SqliteKeyStore:
    """Box-native key store (SQLite file, no Docker). Stores only hashes."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS api_keys ("
                " key_hash TEXT PRIMARY KEY,"
                " email TEXT NOT NULL,"
                " tier TEXT NOT NULL DEFAULT 'pro',"
                " active INTEGER NOT NULL DEFAULT 1"
                ")"
            )

    def add_key(
        self,
        key: str,
        email: str,
        tier: Tier = Tier.PRO,
        active: bool = True,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO api_keys (key_hash, email, tier, active)"
                " VALUES (?, ?, ?, ?)",
                (hash_key(key), email, tier.value, 1 if active else 0),
            )

    def verify(self, key: str) -> Optional[Entitlement]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT email, tier, active FROM api_keys WHERE key_hash = ?",
                (hash_key(key),),
            ).fetchone()
        if row is None:
            return None
        email, tier_value, active = row
        if int(active) == 0:
            return None
        try:
            tier = Tier(tier_value)
        except ValueError:
            tier = Tier.FREE
        return Entitlement(email=email, tier=tier, active=True)


def build_store(config: object) -> KeyStore:
    """Pick a store from config. Empty ``db_path`` -> empty in-memory store
    (everyone resolves FREE), the safe default while enforcement is off."""

    db_path = getattr(config, "db_path", "") or ""
    if db_path:
        return SqliteKeyStore(db_path)
    return InMemoryKeyStore()


def resolve_tier(key: Optional[str], store: KeyStore) -> Tier:
    """Resolve a raw key to a Tier. No key or an unknown key -> FREE."""

    if not key:
        return Tier.FREE
    ent = store.verify(key)
    if ent is None:
        return Tier.FREE
    return ent.tier


def evaluate(required: Tier, resolved: Tier, enforce: bool) -> Decision:
    """Gate decision.

    In shadow mode (``enforce`` False) the decision is always allowed, but
    ``would_block`` still records whether enforcement would have blocked, so the
    caller can log the shadow outcome.
    """

    would_block = _TIER_RANK[resolved] < _TIER_RANK[required]
    allowed = (would_block is False) or (enforce is False)
    reason = ""
    if would_block:
        reason = (
            "Pro entitlement required for this feature. Provide a valid API key "
            "via 'Authorization: Bearer <key>' or the 'X-RA-Key' header."
        )
    return Decision(
        tier=resolved,
        required=required,
        allowed=allowed,
        would_block=would_block,
        enforced=enforce,
        reason=reason,
    )
