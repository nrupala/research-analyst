"""Stream D — every file the UI references must actually serve.

The help page, theme script, social image, and crawler files all
existed in ui/ with no route: the app header's Help link 404'd and
the theme toggle's script never loaded. These tests pin the routes
so the surfaces the pages link to cannot silently die again.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from research_analyst.server import create_app

client = TestClient(create_app(), raise_server_exceptions=False)


def test_help_page_serves():
    r = client.get("/help.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Research Analyst" in r.text


def test_privacy_page_serves_and_states_the_telemetry_truth():
    r = client.get("/privacy.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # The page must describe the logging design as built: route/status/
    # timing + key record id, never raw keys, IPs, or query strings.
    assert "never the key itself" in r.text
    assert "90 days" in r.text
    assert "info@aimlds.org" in r.text


def test_theme_script_serves():
    r = client.get("/theme.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]


def test_og_image_serves():
    r = client.get("/og-image.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_crawler_files_serve():
    for path in ("/robots.txt", "/sitemap.xml", "/llms.txt"):
        r = client.get(path)
        assert r.status_code == 200, path


SELLER_STRIP = "Sold by 2351485 ALBERTA INC. (AIMLDS)"


def test_pricing_page_serves_with_the_transaction_standard():
    r = client.get("/pricing.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # The standard's fixed items: the plain-terms buying section naming
    # the seller of record, and the seller strip in the footer.
    assert "Buying, in plain terms" in r.text
    assert "2351485 ALBERTA INC." in r.text
    assert "seller of record" in r.text
    assert SELLER_STRIP in r.text
    # The adopted plans and prices (the per-product variables).
    for text in ("$19", "$79", "$58", "$198", "100,000", "1,000,000"):
        assert text in r.text, text
    # Buy buttons post the plan keys the checkout endpoint accepts.
    for plan in ("app_pro", "app_team", "api_pro", "api_team"):
        assert f'data-plan="{plan}"' in r.text, plan


def test_terms_page_serves():
    r = client.get("/terms.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "9. Paid tiers, the API, and data licensing" in r.text
    assert "never sold, redistributed, or exported as raw source data" in r.text
    assert SELLER_STRIP in r.text


def test_seller_strip_on_every_page():
    # Transaction-page standard: the strip rides in the footer of every
    # page of the product — app, help, privacy, pricing, terms.
    for path in ("/", "/help.html", "/privacy.html", "/pricing.html", "/terms.html"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert SELLER_STRIP in r.text, path
        assert "Payments by Stripe" in r.text, path


def test_checkout_return_panel_is_wired_in_the_app():
    # The Stripe success URL lands on / with ?checkout=success and a
    # session id; the app must consume it and claim the key there.
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="checkout-result"' in r.text
    assert "/api/billing/claim" in r.text
    assert "/pricing.html" in r.text
