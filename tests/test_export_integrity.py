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

"""Export-integrity tests for the paid source-data bundle.

Every test here corresponds to a defect observed in a real downloaded bundle
(META, 2026-09-27). Each test was written to fail *before* the corresponding
fix. Where a defect is "a real number is computed and then dropped", the test
asserts the value, not merely that the key exists.

Fixture note: the pre-existing fixture in ``test_data_export.py`` passed
``payout_ratio=0.15`` to a Pydantic model that does not define that field, so
the kwarg was silently discarded and the suite passed against a model with no
payout ratio at all. Fixtures here use only field names that exist on the
model, and ``test_fixture_fields_all_exist`` guards against a regression.
"""
# Module: tests/test_export_integrity.py | Version: 1.0 | Updated: 2026-09-27

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from research_analyst.data_export import build_bundle, bundle_to_csv
from research_analyst.enums import ReportType, SecurityType
from research_analyst.models import (
    CapitalAllocation,
    Competitor,
    DividendAnalysis,
    FinancialStatement,
    ReportOutput,
    ReportSection,
    ReportVisual,
    ResearchMetadata,
    ResearchResponse,
    RiskMatrix,
    ValuationRange,
    ValuationScenario,
)
from research_analyst.reports.visuals import VisualEngine

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PEER_MD = (
    "| Ticker | Name | Mkt Cap ($B) | Gross Margin | Op Margin | P/E | EV/EBITDA "
    "| Rev Growth | ROE | D/E | Div Yield |\n"
    "|:------|:-----|-----------:|------------:|----------:|----:|----------:"
    "|-----------:|----:|----:|----------:|\n"
    "| **CHTR** | Charter Communications, Inc. | $14.7 | 55.2% | 23.5% | 2.9x "
    "| 5.3x | -1.7% | 27.2% | 4.42x | N/A |\n"
    "| **NFLX** | Netflix, Inc. | $296.2 | 49.1% | 33.4% | 22.4x | 20.6x "
    "| 13.4% | 49.5% | 0.55x | N/A |\n"
    "| **VZ** | Verizon Communications Inc. | $195.6 | 59.5% | 23.0% | 12.3x "
    "| 7.6x | -0.7% | 15.8% | 1.84x | 6.42% |"
)


def _scenario(label: str, stype: str) -> ValuationScenario:
    """A scenario shaped like the ones the engine produces after the fix.

    ``pe_multiple`` is populated because the engine now publishes the multiple
    it applies instead of only narrating it (defect 3).
    """
    return ValuationScenario(
        scenario_type=stype,
        label=label,
        assumptions=[],
        revenue_growth=0.25,
        operating_margin=0.43,
        pe_multiple=28.4,
        ev_ebitda_multiple=19.1,
        implied_price_low=100.0,
        implied_price_high=130.0,
    )


def _report(
    *,
    report_type: ReportType = ReportType.COMPREHENSIVE,
    with_valuation: bool = False,
    with_dividend: bool = False,
    with_risk: bool = False,
    with_capital: bool = False,
    with_peers: bool = False,
) -> ReportOutput:
    valuation = None
    if with_valuation:
        valuation = ValuationRange(
            ticker="META",
            current_price=751.66,
            primary_methodology="Hybrid (PE + EV/EBITDA)",
            scenarios=[
                _scenario("Bear Case", "bear"),
                _scenario("Base Case", "base"),
                _scenario("Bull Case", "bull"),
            ],
        )
    dividend = None
    if with_dividend:
        dividend = DividendAnalysis(
            ticker="META",
            pays_dividend=True,
            current_yield=0.0028,
            trailing_yield=0.0028,
            annual_dividend_rate=2.10,
            payout_ratio_eps=0.08,
            payout_ratio_fcf=0.10,
            fcf_coverage=9.64,
            consecutive_increase_years=1,
            safety_score=90.0,
            safety_grade="Very Safe",
            peer_median_yield=0.0341,
            yield_vs_peers="below",
            us_10y_yield=0.0518,
            yield_vs_treasury_spread=0.0028 - 0.0518,
            attractiveness_rating="Unattractive",
            annual_dividends={"2024": 2.0, "2025": 2.1, "2026": 1.575},
        )
    risk = None
    if with_risk:
        risk = RiskMatrix(ticker="META", overall_risk_score=4.0)
    capital = None
    if with_capital:
        capital = CapitalAllocation(
            ticker="META",
            period="FY2025",
            capex_pct_of_fcf=0.35,
            buyback_pct_of_fcf=0.20,
            dividend_pct_of_fcf=0.05,
        )
    visuals = []
    if with_peers:
        visuals.append(
            ReportVisual(
                visual_type="table", title="Peer Comparison", content=PEER_MD,
                ties_to="Competitive analysis",
            )
        )
    sections = [ReportSection(step_number=1, title="Step 1", content="x", visuals=visuals)]
    return ReportOutput(
        report_type=report_type, ticker="META", title="META",
        generated_at=datetime(2026, 9, 27, tzinfo=UTC),
        sections=sections, valuation=valuation, dividend=dividend,
        risk_matrix=risk, capital_allocation=capital,
    )


def _response(reports: list[ReportOutput]) -> ResearchResponse:
    return ResearchResponse(
        ticker="META", security_type=SecurityType.EQUITY,
        company_name="Meta Platforms, Inc.", currency="USD",
        generated_at=datetime(2026, 9, 27, tzinfo=UTC),
        reports=reports, metadata=ResearchMetadata(data_sources=["stub"]),
    )


@pytest.fixture
def meta_bundle() -> dict:
    """Single-report bundle mirroring the real META download."""
    return build_bundle(
        _response([_report(
            with_valuation=True, with_dividend=True,
            with_risk=True, with_capital=True, with_peers=True,
        )])
    )


# ---------------------------------------------------------------------------
# Defect 1: payout_ratio is a phantom attribute name
# ---------------------------------------------------------------------------

def test_payout_ratio_uses_real_model_field_names(meta_bundle):
    """`payout_ratio` does not exist on DividendAnalysis -> always null.

    The real fields are payout_ratio_eps / payout_ratio_fcf.
    """
    m = meta_bundle["metrics"]
    assert m["payout_ratio_eps"] == 0.08
    assert m["payout_ratio_fcf"] == 0.10


def test_payout_ratio_never_exported_as_permanent_null(meta_bundle):
    """No key in metrics may be present-but-always-null.

    `payout_ratio` is a phantom name: DividendAnalysis has no such field, so
    `getattr(d, "payout_ratio", None)` can only ever return None.
    """
    m = meta_bundle["metrics"]
    assert "payout_ratio" not in m, (
        "metrics.payout_ratio is a phantom key: it can only ever be null. A "
        "consumer cannot distinguish 'not computed' from 'dropped by a typo'."
    )
    for phantom in ("capex", "buybacks", "dividends"):
        assert phantom not in m["fcf_deployment"], (
            f"fcf_deployment.{phantom} is a phantom key: the model field is "
            f"{phantom}_pct_of_fcf"
        )


# ---------------------------------------------------------------------------
# Defect 2: fcf_deployment reads *_pct, model has *_pct_of_fcf
# ---------------------------------------------------------------------------

def test_fcf_deployment_uses_real_model_field_names(meta_bundle):
    d = meta_bundle["metrics"]["fcf_deployment"]
    assert d["capex_pct_of_fcf"] == 0.35
    assert d["buyback_pct_of_fcf"] == 0.20
    assert d["dividend_pct_of_fcf"] == 0.05


# ---------------------------------------------------------------------------
# Defect 3: the computed scenario P/E is discarded by the engine
# ---------------------------------------------------------------------------

def test_scenario_carries_the_multiple_the_engine_computed():
    """The engine computes scenario_pe; the model must keep it.

    Asserted at the engine boundary, because the exporter simply mirrors the
    model. A fix in the exporter alone would leave the HTML report and the SVG
    chart still reporting null.
    """
    from research_analyst.engines.valuation import ValuationEngine
    from research_analyst.models import ScenarioType

    result = ValuationEngine()._build_scenario(
        label="Base Case",
        scenario_type=ScenarioType.BASE,
        eps=10.0,
        revenue=Decimal("100.0"),
        ebitda=None,
        shares=100,
        op_margin=0.30,
        rev_growth=0.05,
        current_price=200.0,
        pe_comps=20.0,
        ev_ebitda_comps=None,
        enterprise_value=Decimal("1200.0"),
        market_cap=Decimal("1000.0"),
        rev_growth_adj=0.0,
        margin_adj=0.0,
        multiple_adj=1.0,
    )
    assert result.pe_multiple is not None
    assert result.pe_multiple > 0


def test_scenario_multiple_is_exported(meta_bundle):
    assert meta_bundle["scenarios"][0]["pe_multiple"] is not None
    assert meta_bundle["scenarios"][0]["pe_multiple"] > 0


def test_scenario_assumptions_are_exported_for_provenance(meta_bundle):
    """Provenance must ship with the number, not only in the HTML report."""
    s = meta_bundle["scenarios"][0]
    assert "assumptions" in s


# ---------------------------------------------------------------------------
# Defect 4: metrics are last-report-wins while tables accumulate
# ---------------------------------------------------------------------------

def test_metrics_survive_a_later_sparse_report():
    """A second report with no dividend must not erase the first report's.

    Before the fix, _extract_metrics assigned `bundle["metrics"] = out` on every
    report, so the last report wins wholesale and `risk_score` disappears while
    the risk table persists in `tables`.
    """
    b = build_bundle(_response([
        _report(report_type=ReportType.COMPREHENSIVE,
                with_valuation=True, with_dividend=True,
                with_risk=True, with_capital=True, with_peers=True),
        _report(report_type=ReportType.TACTICAL),  # sparse: no analyses
    ]))
    assert b["metrics"]["current_price"] == 751.66
    assert b["metrics"]["dividend_yield"] == 0.0028
    assert b["metrics"]["risk_score"] == 4.0
    assert b["metrics"]["fcf_deployment"]["capex_pct_of_fcf"] == 0.35


def test_populated_metric_is_never_overwritten_by_null():
    """Precedence rule: a real value must not be replaced by a null."""
    b = build_bundle(_response([
        _report(report_type=ReportType.COMPREHENSIVE, with_dividend=True),
        _report(report_type=ReportType.TACTICAL, with_dividend=True),
    ]))
    assert b["metrics"]["dividend_yield"] == 0.0028


# ---------------------------------------------------------------------------
# Defect 5: scenarios and peers are duplicated per report
# ---------------------------------------------------------------------------

def test_scenarios_are_not_duplicated_across_reports():
    b = build_bundle(_response([
        _report(report_type=ReportType.COMPREHENSIVE, with_valuation=True),
        _report(report_type=ReportType.COMPREHENSIVE, with_valuation=True),
    ]))
    assert len(b["scenarios"]) == 3
    assert len({s["label"] for s in b["scenarios"]}) == 3


def test_peers_are_not_duplicated_across_reports():
    b = build_bundle(_response([
        _report(report_type=ReportType.COMPREHENSIVE, with_peers=True),
        _report(report_type=ReportType.COMPREHENSIVE, with_peers=True),
    ]))
    # Three distinct peers in the fixture, not six.
    assert len(b["peers"]) == 3
    assert len({r[0] for r in b["peers"]}) == 3


# ---------------------------------------------------------------------------
# Defect 6: peer_median_yield is never exported
# ---------------------------------------------------------------------------

def test_peer_median_yield_is_exported(meta_bundle):
    assert meta_bundle["metrics"]["peer_median_yield"] == 0.0341


def test_peer_yields_keys_are_clean_tickers(meta_bundle):
    """`peer_yields` keys are programmatic identifiers, not markdown.

    The peer table bolds the ticker (`| **VZ** |`), so the exporter has to
    strip the emphasis from BOTH ends. Stripping only the leading run left
    the closing `**` attached and shipped keys like `VZ**` on the live
    download -- caught against the deployed service, not by the unit tests.
    """
    keys = list(meta_bundle["metrics"]["peer_yields"])
    assert keys == ["VZ"], f"expected clean ticker(s), got {keys}"
    assert all("*" not in k for k in keys)


def test_peer_yields_values_match_the_exported_row(meta_bundle):
    """Each per-peer yield is the Div Yield of the row it is keyed by."""
    rows = {r[0].strip().strip("*"): r for r in meta_bundle["peers"]}
    yields = meta_bundle["metrics"]["peer_yields"]
    assert yields  # only peers with a yield land in the map
    div_col = [c.strip() for c in PEER_MD.splitlines()[0].split("|")].index("Div Yield") - 1
    for ticker, frac in yields.items():
        row = rows[ticker]
        assert frac == round(float(row[div_col].rstrip("%")) / 100, 6)


def test_peer_median_yield_ships_with_per_peer_yields(meta_bundle):
    """The median is over a wider population than the exported peer rows.

    `peer_median_yield` is computed by the engine over the whole competitor
    universe, including peers whose Div Yield cell is N/A and therefore has no
    exported row. So the median is deliberately NOT recomputable from
    `peer_yields` alone -- that gap is documented in docs/API-REFERENCE.md.
    What must hold is that the per-peer yields ship alongside it, so a
    consumer can see which peers contributed and that the number is
    derived from peer dividend data at all.
    """
    m = meta_bundle["metrics"]
    assert "peer_yields" in m
    assert m["peer_median_yield"] is not None
    # 2 of the 3 fixture peers are N/A -> the exported map is strictly smaller
    # than the peer list, which is exactly the population mismatch.
    assert len(m["peer_yields"]) < len(meta_bundle["peers"])


# ---------------------------------------------------------------------------
# Defect 7: peer names truncated at 20 chars, and the truncation reaches
#            the paid export because the exporter re-parses the markdown
# ---------------------------------------------------------------------------

def test_peer_name_is_not_truncated_in_the_exported_rows():
    b = build_bundle(_response([_report(with_peers=True)]))
    assert b["peers"][0][1] == "Charter Communications, Inc."
    # The bundle must not carry a name that is a truncated fragment of the
    # model's real name. Asserted against the model, not a literal.
    peers = [
        Competitor(ticker="CHTR", name="Charter Communications, Inc.",
                   market_cap=Decimal("14.7e9"), pe_ratio=2.9),
        Competitor(ticker="NFLX", name="Netflix, Inc.",
                   market_cap=Decimal("296.2e9"), pe_ratio=22.4),
    ]
    v = VisualEngine.table_peer_comparison("META", peers, "USD")
    assert "Charter Communications, Inc." in v.content


def test_full_peer_name_survives_the_export_path():
    """The exporter re-parses the markdown, so a truncated name reaches the
    customer. Assert the exported value equals the model's full name."""
    long_name = "Charter Communications, Inc."
    peers = [
        Competitor(ticker="CHTR", name=long_name,
                   market_cap=Decimal("14.7e9"), pe_ratio=2.9),
    ]
    v = VisualEngine.table_peer_comparison("META", peers, "USD")

    # Feed the real table through a report so the export actually parses it.
    report = _report()
    report.sections[0].visuals.append(v)
    b = build_bundle(_response([report]))
    assert b["peers"][0][1] == long_name


# ---------------------------------------------------------------------------
# Defect 8: an all-null financial period becomes an all-N/A column
# ---------------------------------------------------------------------------

def test_all_null_period_is_excluded_from_the_financial_summary():

    empty = FinancialStatement(
        period="FY2021",
        period_end_date=date(2021, 12, 31),
        revenue=None, gross_profit=None, operating_income=None,
        net_income=None, gross_margin=None, operating_margin=None,
        net_margin=None, eps_diluted=None, free_cash_flow=None,
        roe=None, debt_to_equity=None,
    )
    good = FinancialStatement(
        period="FY2022",
        period_end_date=date(2022, 12, 31),
        revenue=Decimal("116.61e9"),
        gross_profit=Decimal("91.36e9"),
        operating_income=Decimal("28.94e9"),
        net_income=Decimal("23.20e9"),
        gross_margin=0.783, operating_margin=0.248, net_margin=0.199,
        eps_diluted=8.59, free_cash_flow=Decimal("19.29e9"),
        roe=0.185, debt_to_equity=0.21,
    )
    v = VisualEngine.table_financial_summary([empty, good], "USD")
    assert "FY2021" not in v.content
    assert "FY2022" in v.content


def test_omitted_period_is_disclosed_in_the_caption():
    """Silently dropping a year would itself be dishonest.

    The period range in the caption also contains "FY2021", so this asserts the
    *reason* is stated, not merely that the string appears somewhere.
    """
    empty = FinancialStatement(
        period="FY2021", period_end_date=date(2021, 12, 31),
    )
    good = FinancialStatement(
        period="FY2022", period_end_date=date(2022, 12, 31),
        revenue=Decimal("116.61e9"), net_income=Decimal("23.20e9"), eps_diluted=8.59,
    )
    v = VisualEngine.table_financial_summary([empty, good], "USD")
    cap = v.caption.lower()
    assert "omitted" in cap
    assert "fy2021" in cap
    assert "no data" in cap or "unavailable" in cap


# ---------------------------------------------------------------------------
# Defect 9: implausible P/E rendered as a plain number
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [0.0, -45.0, -0.5])
def test_non_positive_peer_pe_renders_as_not_meaningful(bad):
    c = Competitor(ticker="XYZ", name="Example Co", market_cap=Decimal("1e9"),
                   pe_ratio=bad)
    v = VisualEngine.table_peer_comparison("META", [c], "USD")
    assert f"{bad:.1f}x" not in v.content
    assert "n/m" in v.content


def test_positive_low_peer_pe_is_still_shown():
    """A low but positive P/E is real (CHTR 2.9x) and must stay visible.

    Only non-positive P/E is treated as not-meaningful. Flagging low-positive
    multiples as outliers is a separate design decision, recorded as a
    follow-up rather than silently implemented here.
    """
    c = Competitor(ticker="CHTR", name="Charter Communications, Inc.",
                   market_cap=Decimal("14.7e9"), pe_ratio=2.9)
    v = VisualEngine.table_peer_comparison("META", [c], "USD")
    assert "2.9x" in v.content
    assert "n/m" not in v.content


# ---------------------------------------------------------------------------
# Defect 10: 'vs 10Y Treasury' row conflates two different numbers
# ---------------------------------------------------------------------------

def test_treasury_row_does_not_present_the_treasury_yield_as_the_companys():
    from research_analyst.models import DividendAnalysis
    div = DividendAnalysis(
        ticker="META", pays_dividend=True, current_yield=0.0028,
        us_10y_yield=0.0518, yield_vs_treasury_spread=0.0028 - 0.0518,
    )
    v = VisualEngine.table_dividend_summary(div, "USD")
    # The old combined row conflated the Treasury's level with the company's
    # spread. Assert the exact old label is gone (not a substring, since the
    # replacement row is "Spread vs 10Y Treasury").
    assert "| **vs 10Y Treasury** |" not in v.content
    # The Treasury's own level and the company's spread must be separate rows.
    assert "**10Y Treasury Yield**" in v.content
    assert "**Spread vs 10Y Treasury**" in v.content


def test_treasury_spread_keeps_its_signed_basis_points():
    from research_analyst.models import DividendAnalysis
    div = DividendAnalysis(
        ticker="META", pays_dividend=True, current_yield=0.0028,
        us_10y_yield=0.0518, yield_vs_treasury_spread=0.0028 - 0.0518,
    )
    v = VisualEngine.table_dividend_summary(div, "USD")
    assert "-490 bps" in v.content


def test_spread_parenthetical_states_the_spread_not_the_companys_yield():
    """The spread row's parenthetical is the spread magnitude in percentage
    points, not the company's own yield.

    Regression guard: an earlier version of this fix printed
    ``-490 bps (0.28% below 10Y)`` -- the 0.28% is META's *dividend yield*, so
    the row said the spread was 0.28% while simultaneously printing 490 bps. It
    also dereferenced ``current_yield`` unconditionally, raising TypeError when
    the yield was None and a spread was present.
    """
    from research_analyst.models import DividendAnalysis

    div = DividendAnalysis(
        ticker="META", pays_dividend=True, current_yield=0.0028,
        us_10y_yield=0.0518, yield_vs_treasury_spread=-0.049,
    )
    content = VisualEngine.table_dividend_summary(div, "USD").content
    row = next(
        ln for ln in content.splitlines() if ln.startswith("| **Spread vs 10Y Treasury**")
    )
    assert "-490 bps (4.90 pp below 10Y)" in row
    # The company's yield must not appear as the spread magnitude.
    assert "0.28% below 10Y" not in row

    # Same value, no company yield at all -- must render, not raise.
    no_yield = DividendAnalysis(
        ticker="META", pays_dividend=True, current_yield=None,
        us_10y_yield=0.0518, yield_vs_treasury_spread=-0.049,
    )
    assert "-490 bps (4.90 pp below 10Y)" in (
        VisualEngine.table_dividend_summary(no_yield, "USD").content
    )


def test_spread_above_direction_reads_above_not_below():
    from research_analyst.models import DividendAnalysis

    div = DividendAnalysis(
        ticker="XYZ", pays_dividend=True, current_yield=0.08,
        us_10y_yield=0.0518, yield_vs_treasury_spread=0.0282,
    )
    row = next(
        ln
        for ln in VisualEngine.table_dividend_summary(div, "USD").content.splitlines()
        if ln.startswith("| **Spread vs 10Y Treasury**")
    )
    assert "+282 bps (2.82 pp above 10Y)" in row


# ---------------------------------------------------------------------------
# Defect 11: the in-progress dividend year ships unmarked
# ---------------------------------------------------------------------------

def test_partial_dividend_year_is_exported_with_a_marker(meta_bundle):
    d = meta_bundle["metrics"]
    assert d["annual_dividends_complete_years"] == {"2024": 2.0, "2025": 2.1}
    assert d["annual_dividends_partial"] == {"2026": 1.575}


def test_partial_year_is_disclosed_in_the_table():
    from research_analyst.models import DividendAnalysis
    div = DividendAnalysis(
        ticker="META", pays_dividend=True, current_yield=0.0028,
        annual_dividends={"2025": 2.1, "2026": 1.575},
    )
    v = VisualEngine.table_dividend_summary(div, "USD")
    assert "partial" in v.caption.lower()


# ---------------------------------------------------------------------------
# Minor defects found while characterising
# ---------------------------------------------------------------------------

def test_singular_year_is_not_rendered_as_yrs():
    from research_analyst.models import DividendAnalysis
    div = DividendAnalysis(
        ticker="META", pays_dividend=True, current_yield=0.0028,
        consecutive_increase_years=1,
    )
    v = VisualEngine.table_dividend_summary(div, "USD")
    assert "1 yrs" not in v.content
    assert "1 year" in v.content


# ---------------------------------------------------------------------------
# Guard: fixtures must not smuggle in non-existent field names again
# ---------------------------------------------------------------------------

def test_fixture_fields_all_exist():
    """Prevent the original sin: passing a phantom kwarg that is ignored."""
    fields = DividendAnalysis.model_fields
    for name in ("payout_ratio_eps", "payout_ratio_fcf", "peer_median_yield",
                 "annual_dividends", "current_yield", "us_10y_yield"):
        assert name in fields, f"DividendAnalysis has no field {name!r}"
    assert "payout_ratio" not in fields, (
        "DividendAnalysis must not grow a bare `payout_ratio`; the EPS and FCF "
        "bases are different numbers and must stay distinguishable"
    )
    ca = CapitalAllocation.model_fields
    for name in ("capex_pct_of_fcf", "buyback_pct_of_fcf", "dividend_pct_of_fcf"):
        assert name in ca
    for name in ("capex_pct", "buyback_pct", "dividend_pct"):
        assert name not in ca


def test_schema_version_tracks_the_documented_shape(meta_bundle):
    """The docs promise a specific schema_version; a silent shape change with
    an unchanged version string is how the phantom-key defects survived."""
    import re
    from pathlib import Path

    actual = meta_bundle["schema_version"]
    text = (
        Path(__file__).resolve().parents[1] / "docs" / "API-REFERENCE.md"
    ).read_text(encoding="utf-8")

    row = next(
        (ln for ln in text.splitlines() if ln.startswith("| `schema_version`")),
        None,
    )
    assert row is not None, "API-REFERENCE.md does not document schema_version"
    documented = re.findall(r"\d+\.\d+", row)
    assert actual in documented, (
        f"bundle emits schema_version {actual!r} but the API reference "
        f"documents {documented}. The key set changed in this release "
        "(payout_ratio removed, *_pct_of_fcf, peer_median_yield, peer_yields, "
        "partial-year split, scenario assumptions all added)."
    )


def test_documented_top_level_keys_match_the_bundle(meta_bundle):
    """Guard against docs drifting from the produced bundle."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "docs" / "API-REFERENCE.md")
    text = text.read_text(encoding="utf-8")
    for key in ("tables", "metrics", "scenarios", "peers", "schema_version"):
        assert f"| `{key}` |" in text, f"{key} is not documented"


def test_bundle_is_json_serialisable_after_every_fix(meta_bundle):
    import json
    json.dumps(meta_bundle)
    csv_text = bundle_to_csv(meta_bundle)
    assert "payout_ratio_eps" in csv_text


# --- local helpers ----------------------------------------------------------

def _statement(eps: float) -> FinancialStatement:
    return FinancialStatement(
        period="FY2025", period_end_date=date(2025, 12, 31), eps_diluted=eps,
    )
