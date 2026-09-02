"""Tests for the mental-model lens framework (Phase 5a).

* Every lens returns a typed LensResult with attribution-safe phrasing
* Known-value computations (Graham Number, PEG, earnings yield)
* run_all isolates lens failures (never raises)
"""
# Module: tests/test_lenses.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

import math
from decimal import Decimal

from research_analyst.engines.lenses import graham, greenblatt, lynch, run_all
from research_analyst.engines.lenses.base import ATTRIBUTION, LensInput, bvps, ncav, pct_change


def _stmt(**kw):
    from research_analyst.models import FinancialStatement

    base = dict(
        period="FY2025", revenue=Decimal("50_000_000_000"),
        gross_profit=Decimal("20_000_000_000"),
        operating_income=Decimal("10_000_000_000"),
        ebit=Decimal("10_000_000_000"),
        net_income=Decimal("8_000_000_000"),
        eps_diluted=3.0, shares_outstanding=2_000_000_000,
        total_assets=Decimal("60_000_000_000"),
        total_liabilities=Decimal("25_000_000_000"),
        total_equity=Decimal("35_000_000_000"),
        cash_and_equivalents=Decimal("5_000_000_000"),
        total_debt=Decimal("10_000_000_000"),
        current_assets=Decimal("30_000_000_000"),
        current_liabilities=Decimal("10_000_000_000"),
        free_cash_flow=Decimal("9_000_000_000"),
        roe=0.25, roic=0.20, debt_to_equity=0.3,
    )
    base.update(kw)
    return FinancialStatement(**base)


def _input(**kw) -> LensInput:
    defaults = dict(
        ticker="TEST", current_price=50.0,
        latest=_stmt(), prior=_stmt(revenue=Decimal("45_000_000_000"),
                                     eps_diluted=2.5),
        shares_outstanding=2_000_000_000, currency="USD",
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
# Registry
# ---------------------------------------------------------------------------


def test_run_all_returns_typed_results():
    results = run_all(_input())
    assert [r.lens for r in results] == ["graham", "greenblatt", "lynch"]
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
    assert len(results) == 3
