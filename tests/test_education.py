"""Tests for the Educational Context Layer (Phase 4).

* Metric context blocks render clean markdown (no HTML that could escape)
* Playbooks render as structured walkthrough sections
* The extended disclaimer (v2) is single-source and educational-framed
* End-to-end: a rendered report carries context + playbook + educational note
"""
# Module: tests/test_education.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from research_analyst import education
from research_analyst.disclaimer import DISCLAIMER_FULL, DISCLAIMER_SHORT, DISCLAIMER_VERSION


def test_context_block_known_metric():
    block = education.context_block("pe_ratio")
    assert "Why this metric matters" in block
    assert "What it can indicate" in block
    assert block.startswith("*"), "must be markdown, not HTML"
    assert "<details" not in block and "<div" not in block


def test_context_block_unknown_metric_empty():
    assert education.context_block("not_a_metric") == ""


def test_context_block_with_value_label():
    block = education.context_block("pe_ratio", value_label="P/E 25.0x")
    assert "P/E 25.0x" in block


def test_metric_context_covers_key_metrics():
    for metric in ("pe_ratio", "peg_ratio", "debt_to_equity", "roe",
                   "gross_margin", "operating_margin", "net_margin",
                   "free_cash_flow", "current_yield", "payout_ratio",
                   "expense_ratio", "aum", "beta"):
        assert metric in education.METRIC_CONTEXT, f"missing context for {metric}"


def test_playbook_renders():
    pb = education.render_playbook("valuation_sanity")
    assert "Playbook" in pb
    assert "Margin of safety" in pb
    assert pb.startswith("### ")


def test_playbook_unknown_empty():
    assert education.render_playbook("nope") == ""


def test_educational_note_present():
    assert "educational" in education.EDUCATIONAL_NOTE
    assert "recommendation" in education.EDUCATIONAL_NOTE


def test_disclaimer_v2_educational_framing():
    assert DISCLAIMER_VERSION == "2"
    assert "educational" in DISCLAIMER_SHORT.lower()
    assert "educational" in DISCLAIMER_FULL.lower()
    assert "not endorsed by or affiliated with" in DISCLAIMER_FULL


def test_context_block_survives_mdtohtml():
    """The context markdown is pure markdown (no HTML), so mdToHTML cannot
    escape it — covered by the markdown_links/education UI tests."""
    block = education.context_block("roe")
    assert "<" not in block, "context block must contain no HTML tags"
    assert "[" not in block, "context block must contain no link syntax"
