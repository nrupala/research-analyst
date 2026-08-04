"""Offline unit tests for the per-email API-key entitlement core (Slice 1).

No network, no FastAPI. Exercises key extraction, hashing, both key stores,
tier resolution, and the shadow/enforce gate decision.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from research_analyst.entitlements import (
    InMemoryKeyStore,
    SqliteKeyStore,
    Tier,
    build_store,
    evaluate,
    extract_key,
    hash_key,
    resolve_tier,
)


def _hget(headers):
    def get(name):
        return headers.get(name)

    return get


# --- hashing ---------------------------------------------------------------

def test_hash_key_is_deterministic_and_not_plaintext():
    h1 = hash_key("secret-key-abc")
    h2 = hash_key("secret-key-abc")
    assert h1 == h2
    assert len(h1) == 64
    assert "secret-key-abc" not in h1


# --- header extraction -----------------------------------------------------

def test_extract_key_bearer():
    assert extract_key(_hget({"Authorization": "Bearer abc123"})) == "abc123"


def test_extract_key_bearer_scheme_is_case_insensitive():
    assert extract_key(_hget({"Authorization": "bearer low"})) == "low"


def test_extract_key_x_ra_key():
    assert extract_key(_hget({"X-RA-Key": "xyz789"})) == "xyz789"


def test_extract_key_missing_returns_none():
    assert extract_key(_hget({})) is None


def test_extract_key_non_bearer_authorization_ignored():
    assert extract_key(_hget({"Authorization": "Basic abc"})) is None


# --- in-memory store -------------------------------------------------------

def test_in_memory_store_verify_pro():
    store = InMemoryKeyStore()
    store.add_key("prokey", email="a@example.com", tier=Tier.PRO)
    ent = store.verify("prokey")
    assert ent is not None
    assert ent.tier == Tier.PRO
    assert ent.email == "a@example.com"


def test_in_memory_store_unknown_key():
    assert InMemoryKeyStore().verify("nope") is None


def test_in_memory_store_inactive_key():
    store = InMemoryKeyStore()
    store.add_key("dead", email="a@example.com", tier=Tier.PRO, active=False)
    assert store.verify("dead") is None


# --- sqlite store ----------------------------------------------------------

def test_sqlite_store_roundtrip_and_persistence():
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "keys.db")
        store = SqliteKeyStore(path)
        store.add_key("prokey", email="b@example.com", tier=Tier.PRO)
        ent = store.verify("prokey")
        assert ent is not None
        assert ent.tier == Tier.PRO
        assert store.verify("other") is None
        # Reopen to confirm on-disk persistence
        assert SqliteKeyStore(path).verify("prokey") is not None


# --- tier resolution -------------------------------------------------------

def test_resolve_tier_no_key_is_free():
    assert resolve_tier(None, InMemoryKeyStore()) == Tier.FREE


def test_resolve_tier_invalid_key_is_free():
    assert resolve_tier("bogus", InMemoryKeyStore()) == Tier.FREE


def test_resolve_tier_valid_pro():
    store = InMemoryKeyStore()
    store.add_key("k", email="c@example.com", tier=Tier.PRO)
    assert resolve_tier("k", store) == Tier.PRO


# --- gate decision ---------------------------------------------------------

def test_evaluate_shadow_never_blocks():
    d = evaluate(Tier.PRO, Tier.FREE, enforce=False)
    assert d.would_block is True
    assert d.allowed is True
    assert d.enforced is False


def test_evaluate_enforce_blocks_free():
    d = evaluate(Tier.PRO, Tier.FREE, enforce=True)
    assert d.would_block is True
    assert d.allowed is False
    assert d.reason


def test_evaluate_enforce_allows_pro():
    d = evaluate(Tier.PRO, Tier.PRO, enforce=True)
    assert d.would_block is False
    assert d.allowed is True


# --- store construction ----------------------------------------------------

def test_build_store_empty_is_in_memory():
    class Cfg:
        db_path = ""

    assert isinstance(build_store(Cfg()), InMemoryKeyStore)


def test_build_store_with_path_is_sqlite():
    with tempfile.TemporaryDirectory() as d:
        class Cfg:
            db_path = str(Path(d) / "k.db")

        assert isinstance(build_store(Cfg()), SqliteKeyStore)


# --- shipped-off default ---------------------------------------------------

def test_default_enforcement_is_off():
    from research_analyst.config import settings

    assert settings.entitlements.enforce is False
