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

"""Tests for research_analyst/entitlements.py — keys, entitlements, metering, white-label.

No network, no billing, no real keys: everything is in-memory.
"""
# Module: tests/test_entitlements.py

import hashlib
import json

import pytest

from research_analyst.entitlements import (
    API_ACCESS,
    RA_PRO,
    TWF_PRO,
    WHITE_LABEL,
    APIKeyRecord,
    KeyStore,
    MeteringRecorder,
    WhiteLabelProfile,
    effective_entitlements,
    has_entitlement,
    is_internal,
)


def test_key_issuance_returns_raw_key_once():
    store = KeyStore()
    record, raw = store.create("test", {RA_PRO})
    assert raw.startswith("ra_live_")
    # Only the hash is stored — the raw key must not appear in the record.
    assert raw not in record.to_dict().values()
    assert record.key_hash == hashlib.sha256(raw.encode()).hexdigest()


def test_verify_and_wrong_key():
    store = KeyStore()
    _, raw = store.create("test", {RA_PRO})
    assert store.verify(raw) is not None
    assert store.verify("ra_live_wrong") is None
    assert store.verify("") is None
    assert store.verify("not-a-key") is None


def test_revoke_fails_closed():
    store = KeyStore()
    record, raw = store.create("test", {RA_PRO})
    assert store.revoke(record.key_id) is True
    assert store.verify(raw) is None
    assert store.revoke(record.key_id) is False  # idempotent-ish
    assert store.revoke("key_nope") is False


def test_persistence_keeps_hashes_only(tmp_path):
    path = tmp_path / "keys.json"
    store = KeyStore(path)
    record, raw = store.create("persisted", {RA_PRO})
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    dumped = json.dumps(on_disk)
    assert raw not in dumped  # raw key never persisted
    store2 = KeyStore(path)
    assert store2.verify(raw).key_id == record.key_id


def test_twf_pro_bundle_unlocks_ra_pro():
    store = KeyStore()
    record, raw = store.create("twf", {TWF_PRO})
    verified = store.verify(raw)
    assert has_entitlement(verified, RA_PRO)  # bundle mapping
    assert has_entitlement(verified, TWF_PRO)
    assert has_entitlement(verified, API_ACCESS)  # bundled too (2026-10-15 flavors)
    assert not has_entitlement(verified, WHITE_LABEL)


def test_no_entitlement_by_default():
    store = KeyStore()
    record, raw = store.create("plain")
    verified = store.verify(raw)
    assert not has_entitlement(verified, RA_PRO)
    assert not has_entitlement(None, RA_PRO)


def test_effective_entitlements_does_not_mutate_record():
    store = KeyStore()
    record, _ = store.create("twf", {TWF_PRO})
    effective = effective_entitlements(record)
    assert RA_PRO in effective
    assert record.entitlements == {TWF_PRO}


def test_metering_counts_per_endpoint_per_day():
    meter = MeteringRecorder()
    meter.record("key_1", "research", day="2026-09-25")
    meter.record("key_1", "research", day="2026-09-25")
    meter.record("key_1", "compare", day="2026-09-25")
    meter.record("key_2", "research", day="2026-09-25")
    assert meter.usage("key_1", day="2026-09-25") == {"research": 2, "compare": 1}
    assert meter.usage("key_2", day="2026-09-25") == {"research": 1}
    assert meter.usage("key_1", day="2026-09-24") == {}
    assert meter.total_requests("key_1", day="2026-09-25") == 3


def test_metering_sink_failure_does_not_break_recording():
    def bad_sink(key_id, endpoint, day):
        raise RuntimeError("sink down")

    meter = MeteringRecorder(sink=bad_sink)
    meter.record("key_1", "research", day="2026-09-25")
    assert meter.total_requests("key_1", day="2026-09-25") == 1


def test_white_label_profile_inactive_by_default():
    assert WhiteLabelProfile().is_active() is False
    assert WhiteLabelProfile(org_name="Acme").is_active() is True
    assert WhiteLabelProfile(show_support_link=False).is_active() is True


# ---------------------------------------------------------------------------
# Key classes (§6, 2026-11-07): customer (default) vs internal/operator
# ---------------------------------------------------------------------------


def test_internal_mint_carries_the_stamp():
    store = KeyStore()
    record, raw = store.create("ops", {API_ACCESS}, kind="internal")
    assert record.kind == "internal"
    assert is_internal(record)
    assert store.verify(raw).kind == "internal"


def test_customer_is_default_and_legacy_records_read_as_customer():
    store = KeyStore()
    record, _ = store.create("plain", {RA_PRO})
    assert record.kind == "customer"
    assert not is_internal(record)
    base = record.to_dict()
    legacy = dict(base)
    del legacy["kind"]  # a record written before the class existed
    assert APIKeyRecord.from_dict(legacy).kind == "customer"
    bogus = dict(base, kind="partner")  # an unrecognized value fails safe
    assert APIKeyRecord.from_dict(bogus).kind == "customer"


def test_internal_mint_fails_closed():
    store = KeyStore()
    with pytest.raises(ValueError):
        store.create("bad", {API_ACCESS}, kind="partner")
    with pytest.raises(ValueError):
        store.create(
            "bad", {API_ACCESS}, kind="internal", monthly_call_allowance=10
        )


def test_internal_stamp_persists_in_the_key_file(tmp_path):
    path = tmp_path / "keys.json"
    store = KeyStore(path)
    record, raw = store.create("ops", {API_ACCESS}, kind="internal")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["keys"][0]["kind"] == "internal"
    fresh = KeyStore(path)
    assert fresh.verify(raw).kind == "internal"
    assert fresh.get(record.key_id).kind == "internal"
