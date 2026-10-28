# Copyright (C) 2026 2351485 ALBERTA INC.
# SPDX-License-Identifier: AGPL-3.0-or-later
"""KeyStore freshness: cross-process mint/revoke without a restart.

Stream A design (2026-10-15): the Stripe webhook minter and the ops CLI
write the key file from other processes; the serving process must honor
those writes on the next verify, with no restart and no manual reload.
"""
from __future__ import annotations

import time
from pathlib import Path

from research_analyst.entitlements import RA_PRO, KeyStore


def _settle() -> None:
    # Filesystems may share an mtime tick between two fast writes; the
    # store keys freshness on st_mtime_ns, so a tiny pause guarantees
    # the second write lands on a distinguishable timestamp.
    time.sleep(0.01)


def test_cross_process_mint_becomes_visible(tmp_path: Path) -> None:
    path = tmp_path / "keys.json"
    server = KeyStore(path)  # the long-lived serving process
    minter = KeyStore(path)  # e.g. the webhook process

    record, raw = minter.create("buyer-1", {RA_PRO})
    _settle()
    seen = server.verify(raw)
    assert seen is not None
    assert seen.key_id == record.key_id


def test_cross_process_revoke_is_honored_on_next_verify(tmp_path: Path) -> None:
    path = tmp_path / "keys.json"
    minter = KeyStore(path)
    record, raw = minter.create("buyer-2", {RA_PRO})

    server = KeyStore(path)
    assert server.verify(raw) is not None

    assert minter.revoke(record.key_id) is True
    _settle()
    assert server.verify(raw) is None


def test_get_sees_cross_process_writes(tmp_path: Path) -> None:
    path = tmp_path / "keys.json"
    server = KeyStore(path)
    record, _raw = KeyStore(path).create("buyer-3", {RA_PRO})
    _settle()
    got = server.get(record.key_id)
    assert got is not None
    assert got.label == "buyer-3"


def test_own_writes_do_not_trigger_reload_loops(tmp_path: Path) -> None:
    path = tmp_path / "keys.json"
    store = KeyStore(path)
    record, raw = store.create("self", {RA_PRO})
    assert store.verify(raw) is not None
    assert store.revoke(record.key_id) is True
    assert store.verify(raw) is None


def test_pathless_store_unaffected() -> None:
    store = KeyStore(None)
    record, raw = store.create("memory-only", {RA_PRO})
    assert store.verify(raw) is not None
    assert store.revoke(record.key_id) is True
    assert store.verify(raw) is None
