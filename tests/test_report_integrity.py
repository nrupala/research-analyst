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

"""Evidence-integrity regression tests for issues #66-#74.

Offline, deterministic. Synthetic fixtures only — no network.

- #66 staleness visibility: freshness header, data-as-of, previous-close
  disclosure, SLA state, stale warning, TTL-bound cache stamping.
- #67 peer determinism: versioned/hashed peer map, missing-peer flagging.
- #69 input snapshot: one snapshotted input set per run, hashed.
- #70 lens transparency: inputs & calculation rendered per lens.
- #71 risk derivation: score breakdown with factors, weights, formula.
- #72 duplicate sections: template regression + runtime dedupe.
- #73 bear case: explicit bear case + falsifiability in every thesis step.
- #74 sources: every source enumerated with a link/reference.
"""
# Module: tests/test_report_integrity.py | Version: 0.1.0 | Updated: 2026-09-25

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from research_analyst.api_models import ResearchAPIResponse
from research_analyst.engines.lenses import graham
from research_analyst.engines.lenses.base import LensInput
from research_analyst.engines.risk import RiskEngine
from research_analyst.enums import ReportType, RiskCategory, RiskDuration, RiskNature, SecurityType
from research_analyst.models import (
    CompanyProfile,
    FinancialStatement,
    PeerSetProvenance,
    PriceSeries,
    ReportOutput,
    ReportSection,
    ResearchMetadata,
    ResearchRequest,
    RiskMatrix,
    RiskScoreComponent,
    SourceRecord,
    StructuredRisk,
)
from research_analyst.orchestrator import ResearchOrchestrator, _source_records
from research_analyst.providers.market_data import PEER_MAP_VERSION, peer_map_hash
from research_analyst.reports.renderer import ReportRenderer
from research_analyst.reports.templates import get_template
from research_analyst.server import stamp_cache_hit

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _profile(**kw) -> CompanyProfile:
    base = dict(ticker="TEST", name="Test Corp", security_type=SecurityType.EQUITY, sector="")
    base.update(kw)
    return CompanyProfile(**base)


def _prices(**kw) -> PriceSeries:
    base = dict(
        ticker="TEST", data=[],
        period_start=date(2025, 9, 24), period_end=date(2026, 9, 24),
        current_price=100.0,
    )
    base.update(kw)
    return PriceSeries(**base)


def _stmt(**kw) -> FinancialStatement:
    base = dict(
        period="FY2025", period_end_date=date(2025, 12, 31), is_annual=True,
        revenue=Decimal("1000000000"), net_income=Decimal("100000000"),
        eps_diluted=2.0, shares_outstanding=50_000_000,
        total_equity=Decimal("500000000"),
    )
    base.update(kw)
    return FinancialStatement(**base)


def _report(**kw) -> ReportOutput:
    base = dict(
        report_type=ReportType.COMPREHENSIVE,
        ticker="TEST",
        title="Test Corp (TEST) — Comprehensive Report",
        generated_at=datetime(2026, 9, 25, tzinfo=UTC),
        sections=[],
    )
    base.update(kw)
    return ReportOutput(**base)


def _metadata(**kw) -> ResearchMetadata:
    base = dict(
        data_sources=["yfinance (price data)"],
        data_as_of="2026-09-24 (previous close)",
    )
    base.update(kw)
    return ResearchMetadata(**base)


# ---------------------------------------------------------------------------
# #66 — staleness visibility
# ---------------------------------------------------------------------------

def test_freshness_header_shows_contract():
    md = _report().to_markdown(metadata=_metadata())
    assert "Data as of:" in md
    assert "2026-09-24 (previous close)" in md
    assert "delayed to the previous trading day" in md  # previous-close disclosure
    assert "Freshness state:" in md


def test_stale_warning_is_visible():
    m = _metadata(sla_state="stale", stale_warning="Price data is 6 days old.")
    md = _report().to_markdown(metadata=m)
    assert "STALE DATA WARNING" in md
    assert "Price data is 6 days old." in md


def test_no_metadata_keeps_legacy_body():
    md = _report().to_markdown()
    assert "Data Freshness" not in md  # backward compatible


def test_stamp_cache_hit_marks_fresh():
    resp = ResearchAPIResponse(
        request_id="r1", ticker="TEST", company_name="Test Corp",
        security_type="equity", reports=[_report()], metadata=_metadata(),
        reports_markdown=[],
    )
    stamped = stamp_cache_hit(resp, datetime.now(UTC))
    assert stamped.metadata.cache_hit is True
    assert stamped.metadata.cached_at_utc is not None
    assert stamped.metadata.sla_state == "fresh"
    assert "Served from cache" in stamped.reports_markdown[0]


def test_stamp_cache_hit_old_entry_goes_stale():
    resp = ResearchAPIResponse(
        request_id="r1", ticker="TEST", company_name="Test Corp",
        security_type="equity", reports=[_report()], metadata=_metadata(),
        reports_markdown=[],
    )
    old = datetime.now(UTC) - timedelta(days=3)
    stamped = stamp_cache_hit(resp, old)
    assert stamped.metadata.sla_state == "stale"
    assert stamped.metadata.stale_warning is not None
    assert "STALE DATA WARNING" in stamped.reports_markdown[0]


def test_original_response_not_mutated_by_stamp():
    resp = ResearchAPIResponse(
        request_id="r1", ticker="TEST", company_name="Test Corp",
        security_type="equity", reports=[_report()], metadata=_metadata(),
        reports_markdown=[],
    )
    stamp_cache_hit(resp, datetime.now(UTC))
    assert resp.metadata.cache_hit is False  # deep copy: cache stays clean


# ---------------------------------------------------------------------------
# #67 — peer determinism
# ---------------------------------------------------------------------------

def test_peer_map_hash_is_deterministic_and_versioned():
    h1 = peer_map_hash()
    h2 = peer_map_hash()
    assert h1 == h2
    assert len(h1) == 16
    assert PEER_MAP_VERSION  # non-empty version string


def test_peer_provenance_coverage_note_flags_missing():
    prov = PeerSetProvenance(
        map_version=PEER_MAP_VERSION,
        map_hash=peer_map_hash(),
        expected_tickers=["AAPL", "MSFT", "NVDA"],
        resolved_tickers=["AAPL", "MSFT"],
        missing_tickers=["NVDA"],
    )
    note = prov.coverage_note
    assert PEER_MAP_VERSION in note
    assert prov.map_hash in note
    assert "2 of 3" in note
    assert "NVDA" in note
    assert "Missing expected peers" in note


# ---------------------------------------------------------------------------
# #69 — input snapshot
# ---------------------------------------------------------------------------

def _snapshot_inputs(**kw):
    base = dict(
        ticker="TEST",
        request=ResearchRequest(ticker="TEST"),
        profile=_profile(),
        prices=_prices(),
        financials=[_stmt()],
        macro_snapshot=None,
        peers=[],
        peer_provenance=PeerSetProvenance(
            map_version=PEER_MAP_VERSION, map_hash=peer_map_hash()
        ),
    )
    base.update(kw)
    return base


def test_input_snapshot_hash_is_deterministic():
    s1 = ResearchOrchestrator._build_input_snapshot(**_snapshot_inputs())
    s2 = ResearchOrchestrator._build_input_snapshot(**_snapshot_inputs())
    assert s1.input_hash == s2.input_hash
    assert len(s1.input_hash) == 64
    assert s1.inputs["ticker"] == "TEST"
    assert s1.inputs["price"]["current_price"] == 100.0


def test_input_snapshot_hash_changes_with_inputs():
    s1 = ResearchOrchestrator._build_input_snapshot(**_snapshot_inputs())
    s2 = ResearchOrchestrator._build_input_snapshot(
        **_snapshot_inputs(prices=_prices(current_price=150.0))
    )
    assert s1.input_hash != s2.input_hash


def test_snapshot_rendered_in_markdown():
    snap = ResearchOrchestrator._build_input_snapshot(**_snapshot_inputs())
    m = _metadata(input_snapshot=snap)
    md = _report().to_markdown(metadata=m)
    assert "Input Snapshot" in md
    assert snap.input_hash in md
    assert "current_price" in md


# ---------------------------------------------------------------------------
# #70 — lens transparency
# ---------------------------------------------------------------------------

def _lens_input(**kw) -> LensInput:
    defaults = dict(
        ticker="TEST", current_price=50.0, latest=_stmt(),
        shares_outstanding=50_000_000, currency="USD",
    )
    defaults.update(kw)
    return LensInput(**defaults)


def test_lens_inputs_and_calculation_rendered():
    result = graham.run(_lens_input())
    assert result.raw_values  # the lens really computed something
    md = _report(lenses=[result]).to_markdown()
    assert "Inputs & calculation" in md
    assert "graham_number" in md  # raw input/calculation keys are visible


def test_lens_missing_inputs_stay_explicit():
    result = graham.run(_lens_input(latest=None, current_price=None))
    assert result.raw_values == {} or not result.signals
    md = _report(lenses=[result]).to_markdown()
    # The insufficient-data summary must still render (no silent empty lens).
    assert "Graham" in md
    assert result.summary in md
    # #70: missing inputs are named explicitly, not a generic "n/a".
    assert "Missing inputs" in md
    assert "financial_statements" in md
    assert "current_price" in md
    assert "eps_diluted" in md
    assert "book_value_per_share" in md
    assert result.missing_inputs  # the model itself carries the names


def test_lens_missing_inputs_named_for_all_lenses():
    # Every lens must name its missing inputs when run on empty data.
    from research_analyst.engines.lenses import run_all
    empty = LensInput(ticker="TEST")
    for result in run_all(empty):
        md = _report(lenses=[result]).to_markdown()
        if result.missing_inputs:
            assert "Missing inputs" in md, f"{result.lens} hides missing inputs"
            for name in result.missing_inputs:
                assert name in md, f"{result.lens} missing input {name!r} not rendered"


# ---------------------------------------------------------------------------
# #71 — risk derivation
# ---------------------------------------------------------------------------

def _risk(**kw) -> StructuredRisk:
    base = dict(
        title="Test Risk",
        description="A synthetic risk for derivation tests.",
        category=RiskCategory.OPERATIONAL,
        probability="High (>50%)",
        impact="High",
        timing=RiskDuration.NEAR_TERM,
        nature=RiskNature.TRANSITORY,
    )
    base.update(kw)
    return StructuredRisk(**base)


def test_risk_engine_unrated_when_no_risks():
    # Issue #71: no unsupported score — with no risks, no score is published.
    engine = RiskEngine()
    matrix = engine.assess(profile=_profile(sector=""))
    assert matrix.overall_risk_score is None
    assert matrix.score_breakdown == []
    assert "unrated" in matrix.score_baseline_note.lower()
    assert "no score" in matrix.score_baseline_note.lower()


def test_risk_engine_builds_breakdown():
    engine = RiskEngine()
    real = RiskEngine._regulatory_risks
    try:
        RiskEngine._regulatory_risks = lambda self, profile: [
            _risk(title="Risk A", probability="High (>50%)", impact="High"),
            _risk(title="Risk B", probability="Low (<20%)", impact="Low"),
        ]
        matrix = engine.assess(profile=_profile(sector=""))
    finally:
        RiskEngine._regulatory_risks = real
    assert len(matrix.score_breakdown) == 2
    a = next(c for c in matrix.score_breakdown if c.title == "Risk A")
    assert (a.probability_score, a.impact_score, a.severity) == (3, 3, 9)
    b = next(c for c in matrix.score_breakdown if c.title == "Risk B")
    assert (b.probability_score, b.impact_score, b.severity) == (1, 1, 1)
    # weights sum to 1
    assert sum(c.weight_share for c in matrix.score_breakdown) == pytest.approx(1.0)
    # score = (9+1)/(12*2)*10 = 4.166... -> 4.2
    assert matrix.overall_risk_score == pytest.approx(4.2)


def test_risk_derivation_block_renders():
    renderer = ReportRenderer()
    matrix = RiskMatrix(
        ticker="TEST",
        risks=[_risk()],
        overall_risk_score=7.5,
        score_breakdown=[
            RiskScoreComponent(title="Test Risk", probability_score=3,
                               impact_score=3, severity=9, weight_share=1.0)
        ],
    )
    block = "\n".join(renderer._risk_derivation_block(matrix))
    assert "How the Risk Score Is Derived" in block
    assert "probability_score x impact_score" in block  # formula
    assert "Test Risk" in block
    assert "9" in block  # severity
    assert "7.5/10" in block


def test_risk_derivation_block_shows_unrated_note():
    renderer = ReportRenderer()
    matrix = RiskEngine().assess(profile=_profile(sector=""))
    block = "\n".join(renderer._risk_derivation_block(matrix))
    assert "unrated" in block.lower()
    assert "no score" in block.lower()


# ---------------------------------------------------------------------------
# #72 — duplicate sections
# ---------------------------------------------------------------------------

def test_templates_have_no_duplicate_sections():
    for rt in ReportType:
        steps = get_template(rt).steps
        keys = [(s.step_number, s.title.strip().lower()) for s in steps]
        assert len(keys) == len(set(keys)), f"duplicate section in {rt.value} template"


def test_dedupe_sections_keeps_first():
    sections = [
        ReportSection(step_number=1, title="Overview", content="a"),
        ReportSection(step_number=2, title="Risks", content="b"),
        ReportSection(step_number=2, title="Risks", content="dupe"),
    ]
    out = ReportRenderer._dedupe_sections(sections, "TEST", "comprehensive")
    assert len(out) == 2
    assert out[1].content == "b"


# ---------------------------------------------------------------------------
# #73 — bear case & falsifiability
# ---------------------------------------------------------------------------

def test_bear_case_block_content():
    block = "\n".join(
        ReportRenderer._bear_case_block(
            ["Revenue declining at 8% YoY."],
            RiskMatrix(
                ticker="TEST", risks=[_risk(monitoring_triggers=["Debt covenant breach."])],
                overall_risk_score=5.0,
            ),
        )
    )
    assert "Bear Case" in block
    assert "Revenue declining at 8% YoY." in block
    assert "Falsifiability" in block
    assert "invalidat" in block.lower()  # invalidation criteria present


def test_comprehensive_thesis_renders_bear_case():
    renderer = ReportRenderer()
    step = get_template(ReportType.COMPREHENSIVE).steps[6]
    section, _ = renderer._render_comprehensive_step7(step, {"profile": _profile()})
    assert "Bear Case" in section.content
    assert "Falsifiability" in section.content


def test_tactical_and_long_term_theses_render_bear_case():
    renderer = ReportRenderer()
    ctx = {"profile": _profile()}
    t_step = get_template(ReportType.TACTICAL).steps[6]
    l_step = get_template(ReportType.LONG_TERM).steps[6]
    t_section, _ = renderer._render_tactical_step7(t_step, ctx)
    l_section, _ = renderer._render_long_term_step7(l_step, ctx)
    assert "Bear Case" in t_section.content
    assert "Bear Case" in l_section.content


# ---------------------------------------------------------------------------
# #74 — sources enumerated
# ---------------------------------------------------------------------------

def test_source_records_enumerated_with_links():
    recs = _source_records(
        "AAPL",
        ["yfinance (price data)", "yfinance (price data)", "SEC EDGAR XBRL (financial statements)"],
    )
    assert len(recs) == 2  # deduped
    assert recs[0].name == "yfinance (price data)"
    assert recs[0].url and "AAPL" in recs[0].url
    assert recs[1].url and recs[1].url.startswith("https://www.sec.gov")


def test_sources_section_lists_every_source():
    m = _metadata(
        source_records=[
            SourceRecord(name="yfinance (price data)", url="https://finance.yahoo.com/quote/TEST"),
            SourceRecord(name="Manual note", url=None),
        ]
    )
    md = _report().to_markdown(metadata=m)
    assert "## Data Sources" in md
    assert "yfinance (price data)" in md
    assert "https://finance.yahoo.com/quote/TEST" in md
    assert "Manual note" in md
    assert "Sources: 2" not in md  # never a bare count


def test_source_records_fall_back_to_labels():
    m = _metadata(data_sources=["yfinance (price data)", "SEC EDGAR (company profile)"])
    md = _report().to_markdown(metadata=m)
    assert "yfinance (price data)" in md
    assert "SEC EDGAR (company profile)" in md


# ---------------------------------------------------------------------------
# FCF deployment narrative (capital allocation chart descriptor)
# ---------------------------------------------------------------------------


def test_fcf_deployment_note_describes_flows():
    note = ReportRenderer._fcf_deployment_note(
        "META", "FY2025", "USD", 80_000_000_000.0,
        [
            ("capital expenditure", 32_100_000_000.0, 0.45),
            ("share repurchases", 39_200_000_000.0, 0.55),
            ("dividends", None, None),
        ],
    )
    assert "FY2025" in note and "META" in note
    assert "$80.0B" in note and "free cash flow" in note
    assert "$32.1B" in note and "45% of capital deployed" in note
    assert "$39.2B" in note and "55% of capital deployed" in note
    assert "$8.7B" in note and "retained" in note  # 80 - 71.3 = 8.7
    assert "of FCF" not in note.replace("of FCF) was retained", "")


def test_fcf_deployment_note_empty_when_no_amounts():
    note = ReportRenderer._fcf_deployment_note(
        "META", "FY2025", "USD", None,
        [("capital expenditure", None, None), ("share repurchases", None, None)],
    )
    assert note == ""


def test_fcf_deployment_note_flags_over_deployment():
    note = ReportRenderer._fcf_deployment_note(
        "META", "FY2025", "USD", 60_000_000_000.0,
        [("capital expenditure", 50_000_000_000.0, 0.7),
         ("share repurchases", 30_000_000_000.0, 0.3)],
    )
    assert "more than FCF" in note
