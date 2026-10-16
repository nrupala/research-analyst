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

"""Stream A billing: webhook signature, grant -> claim -> key, lifecycle.

Offline: Stripe is never called — webhook payloads are fabricated and
signed in-test with a throwaway secret; the checkout transport is
faked. The invariants under test: no valid signature, no action; a
grant mints exactly one key, at claim time; cancellation revokes.
"""
# Module: tests/test_stripe_billing.py

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from research_analyst import server as server_module
from research_analyst.config import settings
from research_analyst.entitlements import API_ACCESS, RA_PRO, KeyStore
from research_analyst.server import create_app
from research_analyst.stripe_billing import GrantStore, verify_signature

WH_SECRET = "whsec_test_only"
API_SECRET = "sk_test_only"


class _BoomOrchestrator:
    async def run(self, request):  # noqa: ARG002
        raise RuntimeError("STOP — pipeline must not run in billing tests")


def _sign(payload: bytes, secret: str = WH_SECRET, ts: int | None = None) -> str:
    ts = int(time.time()) if ts is None else ts
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _event(event_type: str, obj: dict, event_id: str = "evt_1") -> bytes:
    return json.dumps({"id": event_id, "type": event_type, "data": {"object": obj}}).encode()


def _completed(session: str = "cs_test_123", plan: str = "api_pro") -> bytes:
    return _event(
        "checkout.session.completed",
        {
            "id": session,
            "payment_status": "paid",
            "metadata": {"ra_plan": plan},
            "customer": "cus_1",
            "subscription": "sub_1",
        },
    )


@pytest.fixture()
def billing(monkeypatch):
    monkeypatch.setattr(settings.billing, "stripe_secret_key", API_SECRET)
    monkeypatch.setattr(settings.billing, "stripe_webhook_secret", WH_SECRET)
    monkeypatch.setattr(settings.billing, "stripe_price_app_pro", "price_app_pro")
    monkeypatch.setattr(settings.billing, "stripe_price_app_team", "price_app_team")
    monkeypatch.setattr(settings.billing, "stripe_price_api_pro", "price_api_pro")
    monkeypatch.setattr(settings.billing, "stripe_price_api_team", "price_api_team")
    keys = KeyStore()
    grants = GrantStore()
    app = create_app(orchestrator=_BoomOrchestrator(), key_store=keys, grant_store=grants)
    return TestClient(app, raise_server_exceptions=False), keys, grants


def _post_event(client: TestClient, payload: bytes, secret: str = WH_SECRET):
    headers = {"Stripe-Signature": _sign(payload, secret)}
    return client.post("/api/billing/webhook", content=payload, headers=headers)


class TestSignature:
    def test_valid_signature(self):
        payload = b'{"id":"evt"}'
        assert verify_signature(payload, _sign(payload), WH_SECRET)

    def test_tampered_payload_rejected(self):
        payload = b'{"id":"evt"}'
        assert not verify_signature(payload + b" ", _sign(payload), WH_SECRET)

    def test_wrong_secret_rejected(self):
        payload = b'{"id":"evt"}'
        assert not verify_signature(payload, _sign(payload, "whsec_other"), WH_SECRET)

    def test_stale_timestamp_rejected(self):
        payload = b'{"id":"evt"}'
        old = int(time.time()) - 3600
        now = float(int(time.time()))
        assert not verify_signature(payload, _sign(payload, ts=old), WH_SECRET, now=now)

    def test_garbage_header_rejected(self):
        assert not verify_signature(b"{}", "not-a-signature", WH_SECRET)
        assert not verify_signature(b"{}", "", WH_SECRET)


class TestGrantClaimLifecycle:
    def test_completed_then_claim_mints_once(self, billing):
        client, keys, _grants = billing
        resp = _post_event(client, _completed())
        assert resp.status_code == 200
        assert resp.json()["outcome"] == "grant-recorded"

        claim = client.get("/api/billing/claim", params={"session_id": "cs_test_123"})
        assert claim.status_code == 200
        body = claim.json()
        assert body["plan"] == "api_pro"
        record = keys.verify(body["api_key"])
        assert record is not None
        assert API_ACCESS in record.entitlements
        assert record.monthly_call_allowance == 100_000
        assert record.plan == "api_pro"
        assert record.stripe_subscription_id == "sub_1"

        second = client.get("/api/billing/claim", params={"session_id": "cs_test_123"})
        assert second.status_code == 409

    def test_claim_unknown_session_404(self, billing):
        client, _keys, _grants = billing
        resp = client.get("/api/billing/claim", params={"session_id": "cs_nope"})
        assert resp.status_code == 404

    def test_duplicate_completed_is_idempotent(self, billing):
        client, _keys, grants = billing
        _post_event(client, _completed())
        resp = _post_event(client, _completed(), )
        assert resp.json()["outcome"] == "grant-recorded"
        assert grants.get("cs_test_123") is not None
        claim = client.get("/api/billing/claim", params={"session_id": "cs_test_123"})
        assert claim.status_code == 200

    def test_unknown_plan_records_nothing(self, billing):
        client, _keys, grants = billing
        resp = _post_event(client, _completed(plan="platinum"))
        assert resp.json()["outcome"] == "unknown-plan"
        assert grants.get("cs_test_123") is None

    def test_unpaid_session_ignored(self, billing):
        client, _keys, grants = billing
        payload = _event(
            "checkout.session.completed",
            {
                "id": "cs_unpaid",
                "payment_status": "unpaid",
                "metadata": {"ra_plan": "api_pro"},
                "customer": "cus_1",
                "subscription": "sub_1",
            },
        )
        resp = _post_event(client, payload)
        assert resp.json()["outcome"] == "unpaid-ignored"
        assert grants.get("cs_unpaid") is None

    def test_bad_signature_no_action(self, billing):
        client, _keys, grants = billing
        resp = _post_event(client, _completed(), secret="whsec_forged")
        assert resp.status_code == 400
        assert grants.get("cs_test_123") is None

    def test_cancellation_revokes_key(self, billing):
        client, keys, _grants = billing
        _post_event(client, _completed())
        claim = client.get("/api/billing/claim", params={"session_id": "cs_test_123"})
        raw = claim.json()["api_key"]
        assert keys.verify(raw) is not None
        deleted = _event("customer.subscription.deleted", {"id": "sub_1"}, event_id="evt_2")
        resp = _post_event(client, deleted)
        assert resp.json()["outcome"] == "key-revoked"
        assert keys.verify(raw) is None

    def test_plan_change_updates_allowance(self, billing):
        client, keys, _grants = billing
        _post_event(client, _completed())
        claim = client.get("/api/billing/claim", params={"session_id": "cs_test_123"})
        raw = claim.json()["api_key"]
        updated = _event(
            "customer.subscription.updated",
            {"id": "sub_1", "items": {"data": [{"price": {"id": "price_api_team"}}]}},
            event_id="evt_3",
        )
        resp = _post_event(client, updated)
        assert resp.json()["outcome"] == "plan-updated"
        record = keys.verify(raw)
        assert record is not None
        assert record.plan == "api_team"
        assert record.monthly_call_allowance == 1_000_000

    def test_app_plan_grants_ra_pro(self, billing):
        client, keys, _grants = billing
        _post_event(client, _completed(session="cs_app", plan="app_pro"))
        raw = client.get("/api/billing/claim", params={"session_id": "cs_app"}).json()["api_key"]
        record = keys.verify(raw)
        assert record is not None
        assert RA_PRO in record.entitlements
        assert record.monthly_call_allowance is None


class TestDormantAndCheckout:
    def test_endpoints_dormant_when_unconfigured(self):
        app = create_app(orchestrator=_BoomOrchestrator())
        client = TestClient(app, raise_server_exceptions=False)
        assert client.post("/api/billing/checkout", json={"plan": "api_pro"}).status_code == 503
        assert client.post("/api/billing/webhook", content=b"{}").status_code == 503
        assert client.get("/api/billing/claim", params={"session_id": "x"}).status_code == 503

    def test_checkout_unknown_plan_400(self, billing):
        client, _keys, _grants = billing
        assert client.post("/api/billing/checkout", json={"plan": "platinum"}).status_code == 400

    def test_checkout_returns_session_url(self, billing, monkeypatch):
        client, _keys, _grants = billing

        def fake_create(**kwargs):
            assert kwargs["price_id"] == "price_api_pro"
            return {"id": "cs_fake", "url": "https://checkout.stripe.com/pay/cs_fake"}

        monkeypatch.setattr(server_module, "create_checkout_session", fake_create)
        resp = client.post("/api/billing/checkout", json={"plan": "api_pro"})
        assert resp.status_code == 200
        assert resp.json()["checkout_url"].endswith("cs_fake")


class TestGrantStorePersistence:
    def test_round_trip(self, tmp_path):
        from research_analyst.stripe_billing import Grant

        path = tmp_path / "grants.json"
        store = GrantStore(path)
        store.record(
            Grant(
                session_id="cs_1",
                plan="api_pro",
                customer_id="cus_1",
                subscription_id="sub_1",
                created_at_utc="2026-10-15T00:00:00+00:00",
            )
        )
        reloaded = GrantStore(path)
        grant = reloaded.get("cs_1")
        assert grant is not None
        assert grant.plan == "api_pro"
        assert reloaded.mark_claimed("cs_1", "key_abc") is not None
        assert GrantStore(path).get("cs_1").claimed_key_id == "key_abc"
        assert reloaded.mark_claimed("cs_1", "key_second") is None
