"""Tests for the thinkwithfinance cross-reference layer (Phase 4 seam).

The block must be INVISIBLE until content ships (a path exists in the index) —
that is the contract with the content side: publishing an article = adding a
path to the index; no code release needed.
"""
# Module: tests/test_crossref.py | Version: 1.0 | Updated: 2026-08-31

from __future__ import annotations

import json

from research_analyst.crossref import (
    _CROSSREF_DEFAULT,
    crossref_for,
    load_crossref_index,
    render_crossref_block,
    render_section_link,
    section_crossref_links,
    section_topics,
)


def test_section_topics_fixed_for_all_seven_steps():
    """The report format is fixed (7 steps), so each section's article topic set
    is fixed too — every report type must map all 7 steps."""
    for report_type in ("comprehensive", "long_term", "tactical"):
        for step in range(1, 8):
            topics = section_topics(report_type, step)
            assert topics, f"{report_type} step {step} has no crossref topic"


def test_section_link_hidden_until_content_ships():
    assert render_section_link("comprehensive", 2) == ""
    assert section_crossref_links("comprehensive", 2) == []


def test_section_link_renders_when_path_added():
    index = load_crossref_index()
    index["fundamentals"]["path"] = "reading-financial-statements"
    md = render_section_link("comprehensive", 2, index=index)
    assert "reading-financial-statements" in md
    assert md.startswith("\n*Learn more —")


def test_section_all_seven_steps_link_when_content_ships():
    index = load_crossref_index()
    # content ships: give every section topic a path
    for key, entry in index.items():
        entry["path"] = f"article-{key}"
    for report_type in ("comprehensive", "long_term", "tactical"):
        for step in range(1, 8):
            md = render_section_link(report_type, step, index=index)
            assert md, f"{report_type} step {step} should link once content ships"


def test_etf_section_one_includes_etf_101():
    index = load_crossref_index()
    index["etf_101"]["path"] = "etf-mechanics"
    index["how_to_read"]["path"] = "how-to-read"
    links = section_crossref_links("comprehensive", 1, is_etf=True, index=index)
    assert any(link["topic"] == "etf_101" for link in links)
    assert any(link["topic"] == "how_to_read" for link in links)
    # non-ETF step 1 does NOT get etf_101
    non_etf = section_crossref_links("comprehensive", 1, is_etf=False, index=index)
    assert all(link["topic"] != "etf_101" for link in non_etf)


def test_default_index_has_no_paths():
    """Defaults are topic skeletons only — nothing renders until content ships."""
    for entry in _CROSSREF_DEFAULT.values():
        assert entry["path"] == ""


def test_block_empty_without_content():
    assert render_crossref_block("AAPL", "AAPL") == ""


def test_block_empty_when_only_some_topics_lacked_paths():
    index = load_crossref_index()  # defaults, no paths
    assert crossref_for("AAPL", "AAPL", index=index) == []


def test_load_index_additive_and_live_paths():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "index.json"
        p.write_text(
            json.dumps({
                "valuation": {"path": "how-to-think-about-valuation", "title": "Custom title"},
                "risk_management": {"path": "risk-and-position-sizing"},
            })
        )
        index = load_crossref_index(p)
        assert index["valuation"]["path"] == "how-to-think-about-valuation"
        assert index["valuation"]["title"] == "Custom title"
        assert index["etf_101"]["path"] == ""  # untouched default


def test_crossref_renders_links():
    index = load_crossref_index()
    index["valuation"]["path"] = "how-to-think-about-valuation"
    block = render_crossref_block("AAPL", "AAPL", index=index)
    assert "## Learn More — thinkwithfinance" in block
    assert "https://thinkwithfinance.com/how-to-think-about-valuation" in block


def test_load_index_bad_file_falls_back():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "index.json"
        p.write_text("not json")
        index = load_crossref_index(p)
        assert index == _CROSSREF_DEFAULT


def test_etf_report_maps_etf_101_topic():
    index = load_crossref_index()
    index["etf_101"]["path"] = "etf-mechanics"
    links = crossref_for("SPY", "SPY", report_type="comprehensive", is_etf=True, index=index)
    assert any(link["topic"] == "etf_101" for link in links)


def test_report_markdown_contains_block_when_content_ships():
    """End-to-end: ReportOutput.to_markdown() renders the crossref block once a
    path exists (the content-side contract)."""
    from research_analyst.enums import ReportType
    from research_analyst.models import ReportOutput

    report = ReportOutput(
        report_type=ReportType.COMPREHENSIVE,
        ticker="AAPL", title="AAPL — Comprehensive",
        generated_at=__import__("datetime").datetime(2026, 1, 1),
        sections=[],
    )
    md = report.to_markdown()
    assert "Learn More" not in md  # no content yet => invisible

    # simulate content shipping: monkeypatch the index with a path
    import research_analyst.crossref as crossref

    original = crossref._CROSSREF_DEFAULT
    patched = {k: dict(v) for k, v in original.items()}
    patched["valuation"]["path"] = "valuation-101"
    crossref._CROSSREF_DEFAULT = patched
    try:
        md2 = report.to_markdown()
        assert "Learn More — thinkwithfinance" in md2
        assert "valuation-101" in md2
    finally:
        crossref._CROSSREF_DEFAULT = original
