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

"""Stripe billing for Research Analyst (Stream A).

Flow: hosted Checkout (card data never touches this service) -> signed
webhook records a *grant* -> the buyer claims once from the success page
and the API key is minted at claim time. Key material therefore never
exists before the claim, and only its hash is ever persisted.

What is sold: RA's own work product — app tiers unlock ``ra.pro``
features; API tiers grant ``api.access`` with a monthly call allowance.
Source data is never sold (owner ruling, 2026-10-15): the
``source.data`` entitlement is retired and no plan grants it.

Safety properties:
- Webhook signatures are verified (HMAC-SHA256, timestamp tolerance)
  before any event is acted on; failures are rejected, never processed.
- Grant recording is idempotent per checkout session.
- A claim mints exactly one key; a second claim is refused.
- Lifecycle events suspend access: subscription deletion revokes the
  issued key immediately.
"""
# Module: research_analyst/stripe_billing.py | Stream A | 2026-10-15

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from research_analyst.entitlements import API_ACCESS, RA_PRO, KeyStore

logger = logging.getLogger(__name__)

STRIPE_API_BASE = "https://api.stripe.com/v1"
_SIGNATURE_TOLERANCE_SECONDS = 300

# ---------------------------------------------------------------------------
# Plans — the adopted family-mirrored pricing (2026-10-15). Prices live in
# Stripe; here each plan names its price-id config slot, the entitlements
# it grants, and the monthly call allowance it carries.
# ---------------------------------------------------------------------------

PLAN_APP_PRO = "app_pro"
PLAN_APP_TEAM = "app_team"
PLAN_API_PRO = "api_pro"
PLAN_API_TEAM = "api_team"


@dataclass(frozen=True)
class Plan:
    name: str
    price_config_attr: str  # BillingConfig attribute holding the price id
    entitlements: frozenset[str]
    monthly_call_allowance: int | None


PLANS: dict[str, Plan] = {
    # App Pro $19/mo, App Team $79/mo — unlock RA Pro features.
    PLAN_APP_PRO: Plan(PLAN_APP_PRO, "stripe_price_app_pro", frozenset({RA_PRO}), None),
    PLAN_APP_TEAM: Plan(PLAN_APP_TEAM, "stripe_price_app_team", frozenset({RA_PRO}), None),
    # API Pro $58/mo per 100,000 calls; API Team $198/mo per 1,000,000.
    PLAN_API_PRO: Plan(PLAN_API_PRO, "stripe_price_api_pro", frozenset({API_ACCESS}), 100_000),
    PLAN_API_TEAM: Plan(PLAN_API_TEAM, "stripe_price_api_team", frozenset({API_ACCESS}), 1_000_000),
}


def plan_for_price_id(plans_price_ids: dict[str, str], price_id: str) -> str | None:
    """Map a Stripe price id back to a plan name (for plan changes)."""
    for plan_name, pid in plans_price_ids.items():
        if pid and pid == price_id:
            return plan_name
    return None


# ---------------------------------------------------------------------------
# Grants — a paid checkout session awaiting (or having completed) its claim.
# No key material is stored here; the key is minted at claim time.
# ---------------------------------------------------------------------------


@dataclass
class Grant:
    session_id: str
    plan: str
    customer_id: str
    subscription_id: str
    created_at_utc: str
    claimed_key_id: str | None = None
    claimed_at_utc: str | None = None


class GrantStore:
    """Persisted checkout grants (JSON file; in-memory for tests)."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else None
        self._grants: dict[str, Grant] = {}
        self._lock = threading.RLock()
        if self._path and self._path.exists():
            self._load()

    def record(self, grant: Grant) -> Grant:
        """Insert a grant; idempotent per session — returns the stored one."""
        with self._lock:
            existing = self._grants.get(grant.session_id)
            if existing is not None:
                return existing
            self._grants[grant.session_id] = grant
            self._save()
            return grant

    def get(self, session_id: str) -> Grant | None:
        with self._lock:
            return self._grants.get(session_id)

    def mark_claimed(self, session_id: str, key_id: str) -> Grant | None:
        with self._lock:
            grant = self._grants.get(session_id)
            if grant is None or grant.claimed_key_id is not None:
                return None
            grant.claimed_key_id = key_id
            grant.claimed_at_utc = datetime.now(UTC).isoformat()
            self._save()
            return grant

    def _load(self) -> None:
        try:
            assert self._path is not None
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not load grants file %s: %s", self._path, e)
            return
        for d in data.get("grants", []):
            try:
                grant = Grant(**d)
            except Exception:
                continue
            self._grants[grant.session_id] = grant

    def _save(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"grants": [asdict(g) for g in self._grants.values()]}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Could not persist grants file %s: %s", self._path, e)


# ---------------------------------------------------------------------------
# Webhook signature verification (Stripe scheme, implemented directly so
# the service carries no SDK dependency).
# ---------------------------------------------------------------------------


def verify_signature(
    payload: bytes, sig_header: str, secret: str, *, now: float | None = None
) -> bool:
    """True iff the Stripe-Signature header validly signs this payload."""
    if not payload or not sig_header or not secret:
        return False
    timestamp: str | None = None
    signatures: list[str] = []
    for part in sig_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)
    if timestamp is None or not signatures:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    current = time.time() if now is None else now
    if abs(current - ts) > _SIGNATURE_TOLERANCE_SECONDS:
        return False
    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


# ---------------------------------------------------------------------------
# Checkout session creation (form-encoded POST; transport injectable).
# ---------------------------------------------------------------------------


def _stripe_post(path: str, form: dict[str, str], secret_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{STRIPE_API_BASE}{path}",
        data=urlencode(form).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (fixed https host)
        result: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        return result


def create_checkout_session(
    *,
    plan: Plan,
    price_id: str,
    secret_key: str,
    success_url: str,
    cancel_url: str,
    post: Any = _stripe_post,
) -> dict[str, Any]:
    """Create a subscription Checkout Session for a plan. Returns Stripe's JSON."""
    form = {
        "mode": "subscription",
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata[ra_plan]": plan.name,
        "subscription_data[metadata][ra_plan]": plan.name,
    }
    result: dict[str, Any] = post("/checkout/sessions", form, secret_key)
    return result


# ---------------------------------------------------------------------------
# Event handling. Every action is audit-logged with ids only.
# ---------------------------------------------------------------------------


def handle_event(
    event: dict[str, Any],
    *,
    key_store: KeyStore,
    grant_store: GrantStore,
    price_to_plan: dict[str, str],
) -> str:
    """Apply one verified Stripe event. Returns a short outcome label."""
    event_type = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    event_id = event.get("id", "")

    if event_type == "checkout.session.completed":
        if obj.get("payment_status") not in (None, "paid"):
            logger.info(
                "billing audit: event=%s session=%s outcome=unpaid-ignored", event_id, obj.get("id")
            )
            return "unpaid-ignored"
        metadata = obj.get("metadata") or {}
        plan_name = metadata.get("ra_plan", "")
        if plan_name not in PLANS:
            logger.warning(
                "billing audit: event=%s outcome=unknown-plan plan=%r", event_id, plan_name
            )
            return "unknown-plan"
        grant = grant_store.record(
            Grant(
                session_id=str(obj.get("id", "")),
                plan=plan_name,
                customer_id=str(obj.get("customer", "")),
                subscription_id=str(obj.get("subscription", "")),
                created_at_utc=datetime.now(UTC).isoformat(),
            )
        )
        logger.info(
            "billing audit: event=%s session=%s plan=%s outcome=grant-recorded claimed=%s",
            event_id,
            grant.session_id,
            grant.plan,
            grant.claimed_key_id is not None,
        )
        return "grant-recorded"

    if event_type == "customer.subscription.deleted":
        subscription_id = str(obj.get("id", ""))
        record = key_store.find_by_subscription(subscription_id)
        if record is not None and not record.revoked:
            key_store.revoke(record.key_id)
            logger.info(
                "billing audit: event=%s subscription=%s key_id=%s outcome=key-revoked",
                event_id,
                subscription_id,
                record.key_id,
            )
            return "key-revoked"
        logger.info(
            "billing audit: event=%s subscription=%s outcome=no-key", event_id, subscription_id
        )
        return "no-key"

    if event_type == "customer.subscription.updated":
        # Plan change: adjust the issued key's plan + allowance in place.
        subscription_id = str(obj.get("id", ""))
        record = key_store.find_by_subscription(subscription_id)
        if record is None:
            return "no-key"
        items = ((obj.get("items") or {}).get("data")) or []
        price_id = ""
        if items:
            price_id = str(((items[0].get("price") or {}).get("id")) or "")
        new_plan_name = plan_for_price_id(price_to_plan, price_id)
        if new_plan_name is None or new_plan_name not in PLANS:
            logger.warning(
                "billing audit: event=%s subscription=%s outcome=unknown-price price=%s",
                event_id,
                subscription_id,
                price_id,
            )
            return "unknown-price"
        new_plan = PLANS[new_plan_name]
        record.plan = new_plan.name
        record.monthly_call_allowance = new_plan.monthly_call_allowance
        record.entitlements = set(new_plan.entitlements)
        key_store.persist(record)
        logger.info(
            "billing audit: event=%s subscription=%s key_id=%s outcome=plan-updated plan=%s",
            event_id,
            subscription_id,
            record.key_id,
            new_plan.name,
        )
        return "plan-updated"

    if event_type == "invoice.payment_failed":
        logger.info(
            "billing audit: event=%s subscription=%s outcome=payment-failed-logged",
            event_id,
            obj.get("subscription"),
        )
        return "payment-failed-logged"

    return "ignored"


def claim_grant(
    session_id: str, *, key_store: KeyStore, grant_store: GrantStore
) -> tuple[str, str] | None:
    """Mint the key for a paid grant. Returns (raw_key, plan) exactly once.

    None when the session is unknown; raises ValueError when the grant
    was already claimed (the raw key is gone by design — support
    re-issues by revoking and minting a replacement).
    """
    grant = grant_store.get(session_id)
    if grant is None:
        return None
    if grant.claimed_key_id is not None:
        raise ValueError("already-claimed")
    plan = PLANS[grant.plan]
    record, raw_key = key_store.create(
        f"stripe:{grant.plan}",
        set(plan.entitlements),
        plan=plan.name,
        stripe_customer_id=grant.customer_id or None,
        stripe_subscription_id=grant.subscription_id or None,
        monthly_call_allowance=plan.monthly_call_allowance,
    )
    if grant_store.mark_claimed(session_id, record.key_id) is None:
        # Lost a claim race: revoke the just-minted key rather than leak a second one.
        key_store.revoke(record.key_id)
        raise ValueError("already-claimed")
    logger.info(
        "billing audit: session=%s key_id=%s plan=%s outcome=claimed",
        session_id,
        record.key_id,
        plan.name,
    )
    return raw_key, plan.name
