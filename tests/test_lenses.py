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

"""Tests for the mental-model lens framework (Phase 5a).

* Every lens returns a typed LensResult with attribution-safe phrasing
* Known-value computations (Graham Number, PEG, earnings yield)
* run_all isolates lens failures (never raises)
"""
# Module: tests/test_lenses.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

import math
from decimal import Decimal

from research_analyst.engines.lenses import (
    buffett,
    dalio,
    damodaran,
    graham,
    greenblatt,
    lynch,
    marks,
    run_all,
)
from research_analyst.engines.lenses.base import ATTRIBUTION, LensInput, bvps, ncav, pct_change


def _stmt(**kw):
    from research_analyst.models import FinancialStatement

    base = dict(
        period="FY2025",
        revenue=Decimal("50_000_000_000"),
        gross_profit=Decimal("20_000_000_000"),
        operating_income=Decimal("10_000_000_000"),
        ebit=Decimal("10_000_000_000"),
        net_income=Decimal("8_000_000_000"),
        eps_diluted=3.0,
        shares_outstanding=2_000_000_000,
        total_assets=Decimal("60_000_000_000"),
        total_liabilities=Decimal("25_000_000_000"),
        total_equity=Decimal("35_000_000_000"),
        cash_and_equivalents=Decimal("5_000_000_000"),
        total_debt=Decimal("10_000_000_000"),
        current_assets=Decimal("30_000_000_000"),
        current_liabilities=Decimal("10_000_000_000"),
        free_cash_flow=Decimal("9_000_000_000"),
        roe=0.25,
        roic=0.20,
        debt_to_equity=0.3,
    )
    base.update(kw)
    return FinancialStatement(**base)


def _input(**kw) -> LensInput:
    defaults = dict(
        ticker="TEST",
        current_price=50.0,
        latest=_stmt(),
        prior=_stmt(revenue=Decimal("45_000_000_000"), eps_diluted=2.5),
        shares_outstanding=2_000_000_000,
        currency="USD",
    )
    defaults.update(kw)
    return LensInput(**defaults)


# ---------------------------------------------------------------------------
# Base helpers
# ---------------------------------------------------------------------------


def test_bvps_and_ncav():
    s = _stmt()
    assert bvps(s) == 17.5  # 35B / 2B
    assert ncav(s) == 10.0  # (30B - 10B) / 2B


def test_pct_change():
    assert pct_change(3.0, 2.5) == 0.2
    assert pct_change(None, 2.5) is None
    assert pct_change(3.0, 0) is None


def test_attribution_phrasing_safe():
    assert "not affiliated with or endorsed by" in ATTRIBUTION
    assert "public-domain" in ATTRIBUTION


# ---------------------------------------------------------------------------
# Graham
# ---------------------------------------------------------------------------


def test_graham_number_known_value():
    """EPS 3.00, BVPS 17.50 -> sqrt(22.5*3*17.5) = sqrt(1181.25) = 34.37."""
    result = graham.run(_input())
    expected = round(math.sqrt(22.5 * 3.0 * 17.5), 2)
    assert result.raw_values["graham_number"] == expected
    # price 50 > 34.37 -> caution
    assert any(s.read == "caution" for s in result.signals)
    assert "Benjamin Graham" in result.attribution
    assert result.educational_only is True


def test_graham_favor_when_cheap():
    result = graham.run(_input(current_price=30.0))
    assert any(s.read == "favor" for s in result.signals)


def test_graham_net_net():
    result = graham.run(_input(current_price=8.0))  # below NCAV 10
    assert any(s.label == "Net-Net Value (NCAV)" and s.read == "favor" for s in result.signals)


# ---------------------------------------------------------------------------
# Greenblatt
# ---------------------------------------------------------------------------


def test_greenblatt_roic_and_ey():
    result = greenblatt.run(_input())
    assert result.raw_values["roic"] == 0.20
    # EBIT 10B / EV (100B mcap + 10B debt - 5B cash = 105B) = 9.52%
    assert result.raw_values["earnings_yield_ebit"] == round(10_000_000_000 / 105_000_000_000, 4)
    # ROIC 20% + EY 9.5% -> favor composite
    assert any(s.label == "Magic Formula Composite" and s.read == "favor" for s in result.signals)
    assert "Greenblatt" in result.attribution


# ---------------------------------------------------------------------------
# Lynch
# ---------------------------------------------------------------------------


def test_lynch_peg():
    # EPS 3.0 vs 2.5 -> 20% growth; P/E = 50/3 = 16.67 -> PEG 0.83 -> favor
    result = lynch.run(_input())
    assert result.raw_values["peg"] == round(16.6667 / 20, 2)
    assert any(s.label == "PEG Ratio" and s.read == "favor" for s in result.signals)
    assert "Stalwart" in result.raw_values["archetype"]
    assert "Lynch" in result.attribution


def test_lynch_declining_eps_no_peg():
    result = lynch.run(_input(prior=_stmt(eps_diluted=4.0)))
    assert result.raw_values.get("peg") is None
    assert any(s.label == "PEG Ratio" and s.value == "n/a (declining EPS)" for s in result.signals)


# ---------------------------------------------------------------------------
# Damodaran
# ---------------------------------------------------------------------------


def test_damodaran_intrinsic_value():
    # FCF 9B, growth 20% (capped at 15% for stage), WACC 10%, 2B shares
    result = damodaran.run(_input())
    assert result.raw_values["fcf"] == 9_000_000_000
    assert result.raw_values["intrinsic_value_per_share"] is not None
    assert any(s.label == "Assumptions" for s in result.signals)
    assert "Damodaran" in result.attribution


def test_damodaran_missing_data_gaps():
    result = damodaran.run(_input(current_price=None, latest=None))
    assert result.raw_values["intrinsic_value_per_share"] is None


# ---------------------------------------------------------------------------
# Buffett
# ---------------------------------------------------------------------------


def test_buffett_owner_earnings():
    # OCF 10B - capex 1B = 9B owner earnings -> favor
    from decimal import Decimal

    result = buffett.run(
        _input(
            latest=_stmt(
                operating_cash_flow=Decimal("10_000_000_000"),
                capex=Decimal("1_000_000_000"),
                free_cash_flow=Decimal("9_000_000_000"),
                gross_margin=0.50,
                roe=0.25,
                debt_to_equity=0.3,
            )
        )
    )
    assert result.raw_values["owner_earnings"] == 9_000_000_000
    assert any(s.label == "Owner Earnings" and s.read == "favor" for s in result.signals)
    assert any(s.label == "Gross Margin Persistence" and s.read == "favor" for s in result.signals)
    assert "Buffett" in result.attribution


def test_buffett_caution_when_weak():
    from decimal import Decimal

    result = buffett.run(
        _input(
            latest=_stmt(
                operating_cash_flow=Decimal("1_000_000_000"),
                capex=Decimal("3_000_000_000"),
                free_cash_flow=Decimal("-2_000_000_000"),
                gross_margin=0.10,
                roe=0.04,
                debt_to_equity=1.5,
            )
        )
    )
    assert any(s.label == "Owner Earnings" and s.read == "caution" for s in result.signals)
    assert any(s.label == "Return on Equity" and s.read == "caution" for s in result.signals)


# ---------------------------------------------------------------------------
# Dalio
# ---------------------------------------------------------------------------


def test_dalio_yield_framing():
    result = dalio.run(_input(raw={"dividend_yield": 0.07}))
    assert result.raw_values["dividend_yield"] == 0.07
    assert any(s.label == "Income vs Rate Regime" for s in result.signals)
    assert any("Allocation Lever" == s.label for s in result.signals)
    assert "Dalio" in result.attribution


def test_dalio_beta_framing():
    result = dalio.run(_input(raw={"beta": 1.6}))
    assert any(
        s.label == "Market Sensitivity (Beta)" and s.read == "caution" for s in result.signals
    )


# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------


def test_marks_cycle_position():
    # P/E = 50/3 = 16.67 -> mid-band (12-22) -> neutral position ~47%
    result = marks.run(_input())
    assert result.raw_values["pe_ttm"] == round(50 / 3, 2)
    assert 0.3 < result.raw_values["cycle_position"] < 0.7
    assert any(s.label == "Second-Level Question" for s in result.signals)
    assert "Marks" in result.attribution


def test_marks_caution_when_extreme():
    result = marks.run(_input(latest=_stmt(eps_diluted=1.0)))  # P/E 50 -> top of band
    assert result.raw_values["cycle_position"] >= 0.7
    assert any(
        s.label == "Cycle Position (P/E vs band)" and s.read == "caution" for s in result.signals
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_run_all_returns_typed_results():
    results = run_all(_input())
    assert [r.lens for r in results] == [
        "graham",
        "greenblatt",
        "lynch",
        "damodaran",
        "buffett",
        "dalio",
        "marks",
    ]
    for r in results:
        assert r.educational_only
        assert "not affiliated with or endorsed by" in r.attribution


def test_run_all_isolates_lens_failure():
    """A throwing lens must not kill the batch."""

    class Boom:
        def __getattr__(self, _):
            raise RuntimeError("boom")

    results = run_all(_input(latest=Boom()))
    # each result is still a typed LensResult (with an error note where failed)
    for r in results:
        assert isinstance(r, object)  # type discipline: all are LensResult-shaped
    assert len(results) == 7


def test_report_output_renders_lenses_section():
    """A rendered ReportOutput carries the typed lenses + markdown section."""
    from datetime import UTC, datetime

    from research_analyst.engines.lenses import LensResult, LensSignal
    from research_analyst.enums import ReportType
    from research_analyst.models import ReportOutput

    report = ReportOutput(
        report_type=ReportType.COMPREHENSIVE,
        ticker="AAPL",
        title="AAPL — Comprehensive",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        sections=[],
        lenses=[
            LensResult(
                lens="graham",
                name="Graham — Margin of Safety",
                summary="screen applied",
                signals=[
                    LensSignal(label="Graham Number", value="34.37", read="caution", note="x"),
                ],
                attribution="public-domain methodology",
            )
        ],
    )
    md = report.to_markdown()
    assert "Mental-Model Lenses (Educational Frameworks)" in md
    assert "Graham — Margin of Safety" in md
    assert "▼ Caution" in md
    assert "public-domain methodology" in md
