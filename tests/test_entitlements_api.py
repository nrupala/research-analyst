"""Server wiring tests for entitlements: source-data gate, /api/usage, metering.

Offline: the pipeline is stubbed to fail fast so gate behavior (401 vs 500)
can be asserted without running any provider.
"""
# Module: tests/test_entitlements_api.py

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from research_analyst.entitlements import (
    RA_PRO,
    SOURCE_DATA,
    TWF_PRO,
    KeyStore,
    MeteringRecorder,
    WhiteLabelProfile,
)
from research_analyst.reports.comparative_renderer import render_html
from research_analyst.server import create_app


class _BoomOrchestrator:
    async def run(self, request):  # noqa: ARG002
        raise RuntimeError("STOP — pipeline must not run in gate tests")


def _app(**kwargs):
    store = kwargs.pop("key_store", None)
    metering = kwargs.pop("metering", None)
    app = create_app(orchestrator=_BoomOrchestrator(), key_store=store, metering=metering)
    return TestClient(app, raise_server_exceptions=False)


def _issue(entitlements):
    store = KeyStore()
    _, raw = store.create("test", entitlements)
    return store, raw


def test_source_data_open_when_nothing_configured():
    client = _app()
    r = client.post("/api/research/data", json={"ticker": "AAA"})
    # Gate passes (open), pipeline booms -> 500, not 401.
    assert r.status_code == 500


def test_source_data_requires_key_when_store_configured():
    store, _ = _issue({RA_PRO})
    client = _app(key_store=store)
    r = client.post("/api/research/data", json={"ticker": "AAA"})
    assert r.status_code == 401


def test_source_data_rejects_key_without_entitlement():
    store, raw = _issue({RA_PRO})  # no source.data
    client = _app(key_store=store)
    r = client.post("/api/research/data", json={"ticker": "AAA"}, headers={"x-ra-key": raw})
    assert r.status_code == 401


def test_source_data_accepts_entitled_key():
    store, raw = _issue({SOURCE_DATA})
    client = _app(key_store=store)
    r = client.post("/api/research/data", json={"ticker": "AAA"}, headers={"x-ra-key": raw})
    assert r.status_code == 500  # gate passed; pipeline boomed


def test_source_data_accepts_twf_bundle_key():
    store, raw = _issue({TWF_PRO})  # twf.pro unlocks source.data via bundle
    client = _app(key_store=store)
    r = client.post("/api/research/data", json={"ticker": "AAA"}, headers={"x-ra-key": raw})
    assert r.status_code == 500


def test_source_data_rejects_revoked_key():
    store = KeyStore()
    record, raw = store.create("test", {SOURCE_DATA})
    store.revoke(record.key_id)
    client = _app(key_store=store)
    r = client.post("/api/research/data", json={"ticker": "AAA"}, headers={"x-ra-key": raw})
    assert r.status_code == 401


def test_usage_requires_key():
    store, raw = _issue({RA_PRO})
    client = _app(key_store=store)
    assert client.get("/api/usage").status_code == 401
    r = client.get("/api/usage", headers={"x-ra-key": raw})
    assert r.status_code == 200
    data = r.json()
    assert data["entitlements"] == [RA_PRO]
    assert "raw" not in str(data).lower()
    assert data["total_requests"] == 0


def test_usage_reflects_metered_calls():
    store, raw = _issue({RA_PRO})
    metering = MeteringRecorder()
    client = _app(key_store=store, metering=metering)
    headers = {"x-ra-key": raw}
    metering.record("key_x", "research")  # someone else's usage
    record = store.verify(raw)
    metering.record(record.key_id, "resolve")
    r = client.get("/api/usage", headers=headers)
    data = r.json()
    assert data["usage"] == {"resolve": 1}
    assert data["total_requests"] == 1


def test_white_label_footer_chrome_only():
    from research_analyst.comparative import ComparativeReport

    report = ComparativeReport(
        requested_tickers=["AAA"],
        generated_at=datetime(2026, 9, 25, tzinfo=UTC),
        tickers=["AAA"],
    )

    profile = WhiteLabelProfile(
        org_name="Acme Advisory",
        footer_note="Prepared for Acme clients.",
        show_support_link=False,
        accent_color="#0b5fff",
    )
    html = render_html(report, white_label=profile)
    assert "Acme Advisory" in html
    assert "Prepared for Acme clients." in html
    assert "buymeacoffee" not in html.lower()
    assert "#0b5fff" in html
    # Evidence chrome untouched: disclaimer + compliance still present.
    assert "disclaimer" in html.lower()
    assert "Compliance:" in html

    plain = render_html(report)
    assert "ra.devinfo.dev" in plain
    assert "Buy Me a Coffee" in plain
