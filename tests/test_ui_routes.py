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
