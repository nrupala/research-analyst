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

"""Tests for the thinkwithfinance cross-reference layer.

Content has shipped: every default topic now carries a published article path,
so the "Learn More - thinkwithfinance" block renders by default across all
report types. The unit-level contract still holds - a topic with an empty path
does not render - and is exercised here with explicit path-less indexes.
"""
# Module: tests/test_crossref.py | Version: 2.0 | Updated: 2026-08-31

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


def _empty_index() -> dict[str, dict[str, str]]:
    """Default skeleton with every path blanked - used to assert the
    'hidden until a path exists' unit behavior independent of shipped content."""
    return {k: {**v, "path": ""} for k, v in _CROSSREF_DEFAULT.items()}


def test_section_topics_fixed_for_all_seven_steps():
    """The report format is fixed (7 steps), so each section's article topic set
    is fixed too - every report type must map all 7 steps."""
    for report_type in ("comprehensive", "long_term", "tactical"):
        for step in range(1, 8):
            topics = section_topics(report_type, step)
            assert topics, f"{report_type} step {step} has no crossref topic"


def test_section_link_hidden_when_path_absent():
    idx = _empty_index()
    assert render_section_link("comprehensive", 2, index=idx) == ""
    assert section_crossref_links("comprehensive", 2, index=idx) == []


def test_section_link_renders_when_path_present():
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


def test_default_index_populated_after_launch():
    """Content has shipped - every default topic now points at a published
    thinkwithfinance article (the block renders without a runtime index)."""
    assert set(_CROSSREF_DEFAULT) == {
        "how_to_read", "business_model", "fundamentals", "valuation",
        "dividends", "etf_101", "technical_analysis", "macro",
        "risk_management", "competitive_moat", "capital_allocation",
        "decision_framework",
    }
    for key, entry in _CROSSREF_DEFAULT.items():
        assert entry["path"].startswith("p/"), f"{key} has no published path"


def test_block_renders_by_default_now_content_shipped():
    block = render_crossref_block("AAPL", "AAPL")
    assert "## Learn More — thinkwithfinance" in block
    assert "https://thinkwithfinance.com/p/" in block


def test_block_hidden_when_index_has_no_paths():
    idx = _empty_index()
    assert render_crossref_block("AAPL", "AAPL", index=idx) == ""
    assert crossref_for("AAPL", "AAPL", index=idx) == []


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
        # untouched topic keeps its shipped default path
        assert index["etf_101"]["path"] == _CROSSREF_DEFAULT["etf_101"]["path"]


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


def test_report_markdown_contains_block_by_default():
    """End-to-end: ReportOutput.to_markdown() renders the crossref block by
    default now that content has shipped; blanking the paths hides it again."""
    from research_analyst.enums import ReportType
    from research_analyst.models import ReportOutput

    report = ReportOutput(
        report_type=ReportType.COMPREHENSIVE,
        ticker="AAPL", title="AAPL - Comprehensive",
        generated_at=__import__("datetime").datetime(2026, 1, 1),
        sections=[],
    )
    md = report.to_markdown()
    assert "Learn More — thinkwithfinance" in md  # content shipped => visible

    # blank every path => block disappears again (unit contract preserved)
    import research_analyst.crossref as crossref

    original = crossref._CROSSREF_DEFAULT
    crossref._CROSSREF_DEFAULT = {k: {**v, "path": ""} for k, v in original.items()}
    try:
        md2 = report.to_markdown()
        assert "Learn More" not in md2
    finally:
        crossref._CROSSREF_DEFAULT = original
