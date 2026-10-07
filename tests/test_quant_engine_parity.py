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

"""Machine-verified parity between the TypeScript quant engine (quant/src)
and its Python port (research_analyst/quant_engine).

Fixtures are generated from the actual TypeScript by
quant/src/parity-dump.test.ts (three fixed inputs: a synthetic series with
nulls plus two realistic multi-year series) and stored at
tests/fixtures/quant/fixtures.json. This suite replays every fixture case
through the Python port and asserts equality within 1e-9 relative
tolerance. This file is the acceptance proof: green means the port is
faithful.

Deliberate, spec-mandated deviations (docs/quant-engine-spec-amendments.md):
- A1: allocation.incremental_roic uses the corrected operating tax rate
  t = taxExpense / (ebit − interestExpense); it is NOT parity-tested against
  the TS (the TS formula is the known-wrong one). It is tested separately
  against hand-computed values below.
- A2: valuation.reverse_dcf's result field is named
  ``implied_explicit_stage_growth`` (the TS field is ``impliedGrowth``);
  the parity comparison remaps the key. The one-period Gordon-algebra
  inversion is ``implied_perpetual_growth`` and IS parity-tested against
  the TS lenses/damodaran.impliedGrowth fixture.
- expected_value's error messages are prefixed with the Python function
  name ("expected_value: ") instead of the TS name ("expectedValue: ");
  the parity comparison normalizes the prefix and checks the rest.
"""
# Module: tests/test_quant_engine_parity.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

import dataclasses
import json
import math
import re
from pathlib import Path

import pytest

from research_analyst.quant_engine import (
    SERIES_KEYS,
    FiscalPeriod,
    ScenarioInput,
    StatementSeries,
    altman_z,
    assert_valid_series,
    beneish_m,
    buyback_effectiveness,
    cagr,
    capm_cost_of_equity,
    cash_conversion,
    dcf,
    debt_profile,
    defined,
    div,
    div_series,
    dividend_profile,
    dupont_point,
    dupont_series,
    expected_value,
    first_value,
    flattery,
    implied_perpetual_growth,
    incremental_roic,
    last_value,
    log_linear_trend,
    margin_of_safety,
    margin_series,
    mean,
    multiple_percentile,
    operating_tax_rate,
    per_share_series,
    reverse_dcf,
    roe_attribution,
    sensitivity_grid,
    series_cagr,
    sloan_accruals,
    solve_for_input,
    tornado,
    wacc,
    working_capital_days,
    yoy_growth,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "quant" / "fixtures.json"
REL_TOL = 1e-9
ABS_TOL = 1e-12


# --------------------------------------------------------------------------
# Fixture loading and comparison machinery
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fixtures():
    with open(FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def _snake_to_camel(name: str) -> str:
    return re.sub(r"_([a-z])", lambda m: m.group(1).upper(), name)


#: Python field name → TS JSON key where they intentionally differ.
KEY_OVERRIDES = {"implied_explicit_stage_growth": "impliedGrowth"}


def normalize(obj):
    """Convert a Python engine result to the TS fixture's JSON shape."""
    if dataclasses.is_dataclass(obj):
        obj = dataclasses.asdict(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = KEY_OVERRIDES.get(k, _snake_to_camel(k))
            out[key] = normalize(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [normalize(v) for v in obj]
    return obj


def assert_close(actual, expected, path="root"):
    """Recursive equality: None == None, floats within 1e-9 relative."""
    if expected is None:
        assert actual is None, f"{path}: expected None, got {actual!r}"
        return
    if isinstance(expected, bool):
        assert actual is expected, f"{path}: expected {expected!r}, got {actual!r}"
        return
    if isinstance(expected, (int, float)):
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool), (
            f"{path}: expected number, got {actual!r}"
        )
        assert math.isclose(actual, expected, rel_tol=REL_TOL, abs_tol=ABS_TOL), (
            f"{path}: {actual!r} != {expected!r}"
        )
        return
    if isinstance(expected, str):
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected list, got {actual!r}"
        assert len(actual) == len(expected), (
            f"{path}: length {len(actual)} != {len(expected)}"
        )
        for i, (a, e) in enumerate(zip(actual, expected)):
            assert_close(a, e, f"{path}[{i}]")
        return
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected dict, got {actual!r}"
        assert set(actual.keys()) == set(expected.keys()), (
            f"{path}: keys {sorted(actual.keys())} != {sorted(expected.keys())}"
        )
        for k in expected:
            assert_close(actual[k], expected[k], f"{path}.{k}")
        return
    raise AssertionError(f"{path}: unexpected fixture value {expected!r}")


# --------------------------------------------------------------------------
# Series builders — mirror quant/src/parity-dump.test.ts exactly
# --------------------------------------------------------------------------

SERIES_DATA = {
    "synthetic": {
        "ticker": "SYN",
        "labels": ["FY2021", "FY2022", "FY2023", "FY2024"],
        "vals": {
            "revenue": [1000, 1100, None, 1300],
            "gross_profit": [400, 450, 470, 520],
            "operating_income": [200, 220, 230, 260],
            "ebit": [210, 230, 240, 270],
            "net_income": [150, 170, 180, 200],
            "eps_diluted": [1.5, 1.7, 1.8, 2.0],
            "sga_expense": [150, 160, 170, 180],
            "depreciation_amortization": [50, 55, 60, 65],
            "operating_cash_flow": [250, 260, 200, 300],
            "capital_expenditure": [80, 90, 100, 110],
            "free_cash_flow": [170, 170, 100, 190],
            "dividends_paid": [50, 55, 60, 65],
            "share_buybacks": [30, 40, 0, 50],
            "total_assets": [5000, 5400, 5800, 6200],
            "total_equity": [3000, 3200, 3400, 3600],
            "total_liabilities": [2000, 2200, 2400, 2600],
            "retained_earnings": [1500, 1600, 1700, 1850],
            "ppe_net": [2000, 2100, 2200, 2300],
            "accounts_payable": [300, 320, 340, 360],
            "total_debt": [1200, 1250, 1300, 1350],
            "cash": [500, 550, 600, 650],
            "current_assets": [1500, 1600, 1700, 1800],
            "current_liabilities": [800, 850, 900, 950],
            "inventory": [400, 420, 440, 460],
            "receivables": [500, 550, 600, 650],
            "interest_expense": [60, 62, 64, 66],
            "tax_expense": [40, 45, 50, 55],
            "shares_outstanding": [100, 98, 96, 94],
            "price": [150, 160, 155, 180],
        },
    },
    "realA": {
        "ticker": "TECHA",
        "labels": ["FY2019", "FY2020", "FY2021", "FY2022", "FY2023", "FY2024"],
        "vals": {
            "revenue": [70000, 86000, 118000, 116000, 135000, 165000],
            "gross_profit": [56000, 69000, 94000, 92000, 108000, 134000],
            "operating_income": [24000, 32000, 47000, 40000, 47000, 69000],
            "ebit": [25000, 33000, 48000, 41000, 48000, 70000],
            "net_income": [18000, 29000, 39000, 23000, 34000, 55000],
            "eps_diluted": [6.4, 10.2, 13.8, 8.9, 13.2, 21.5],
            "sga_expense": [18000, 20000, 25000, 28000, 32000, 36000],
            "depreciation_amortization": [15000, 16000, 18000, 20000, 22000, 24000],
            "operating_cash_flow": [36000, 58000, 71000, 60000, 71000, 92000],
            "capital_expenditure": [15000, 16000, 19000, 31000, 28000, 35000],
            "free_cash_flow": [21000, 42000, 52000, 29000, 43000, 57000],
            "dividends_paid": [0, 0, 0, 0, 0, 0],
            "share_buybacks": [20000, 25000, 44000, 28000, 20000, 30000],
            "total_assets": [300000, 320000, 360000, 380000, 410000, 450000],
            "total_equity": [100000, 128000, 142000, 166000, 154000, 165000],
            "total_liabilities": [200000, 192000, 218000, 214000, 256000, 285000],
            "retained_earnings": [80000, 90000, 85000, 90000, 70000, 75000],
            "ppe_net": [90000, 95000, 100000, 120000, 125000, 140000],
            "accounts_payable": [15000, 16000, 18000, 19000, 20000, 22000],
            "total_debt": [65000, 60000, 58000, 45000, 50000, 55000],
            "cash": [45000, 62000, 48000, 42000, 41000, 65000],
            "current_assets": [175000, 180000, 190000, 180000, 185000, 200000],
            "current_liabilities": [90000, 95000, 100000, 105000, 110000, 120000],
            "inventory": [100, 120, 110, 130, 125, 140],
            "receivables": [25000, 28000, 32000, 30000, 33000, 38000],
            "interest_expense": [200, 180, 150, 120, 150, 200],
            "tax_expense": [5000, 4000, 8000, 12000, 9000, 11000],
            "shares_outstanding": [2830, 2840, 2820, 2580, 2570, 2560],
            "price": [205, 273, 336, 120, 154, 200],
        },
    },
    "realB": {
        "ticker": "DIVB",
        "labels": ["FY2019", "FY2020", "FY2021", "FY2022", "FY2023", "FY2024"],
        "vals": {
            "revenue": [50000, 52000, 48000, 55000, 58000, 60000],
            "gross_profit": [20000, 21000, 18000, 22000, 23000, 24000],
            "operating_income": [8000, 8500, 6000, 9000, 9500, 10000],
            "ebit": [8200, 8700, 6200, 9200, 9700, 10200],
            "net_income": [5000, 5200, None, 5600, 5900, 6200],
            "eps_diluted": [2.5, 2.6, None, 2.9, 3.0, 3.1],
            "sga_expense": [9000, 9200, 9500, 9800, 10000, 10200],
            "depreciation_amortization": [3000, 3100, 3200, 3300, 3400, 3500],
            "operating_cash_flow": [9000, 9500, 7000, 10000, 10500, 11000],
            "capital_expenditure": [4000, 4200, 4500, 4800, 5000, 5200],
            "free_cash_flow": [5000, 5300, 2500, 5200, 5500, 5800],
            "dividends_paid": [3000, 3100, 3200, 3300, 3400, 3500],
            "share_buybacks": [500, 600, 0, 700, 800, 900],
            "total_assets": [80000, 82000, 85000, 88000, 90000, 92000],
            "total_equity": [35000, 36000, 34000, 37000, 38000, 39000],
            "total_liabilities": [45000, 46000, 51000, 51000, 52000, 53000],
            "retained_earnings": [20000, 21000, 19000, 20000, 21000, 22000],
            "ppe_net": [40000, 41000, 43000, 44000, 45000, 46000],
            "accounts_payable": [8000, 8200, 8500, 8800, 9000, 9200],
            "total_debt": [25000, 26000, 30000, 29000, 28500, 28000],
            "cash": [6000, 6200, 5000, 6500, 7000, 7500],
            "current_assets": [25000, 26000, 24000, 27000, 28000, 29000],
            "current_liabilities": [18000, 18500, 20000, 19500, 19800, 20000],
            "inventory": [10000, 10200, 11000, 10800, 10900, 11000],
            "receivables": [12000, 12500, 13000, 12800, 13000, 13200],
            "interest_expense": [1500, 1550, 1700, 1650, 1600, 1550],
            "tax_expense": [1700, 1800, 1500, 1900, 2000, 2100],
            "shares_outstanding": [2000, 1990, 1985, 1930, 1920, 1910],
            "price": [45, 48, 38, 52, 55, 58],
        },
    },
}


def build_series(name: str, ebit_override=None) -> StatementSeries:
    data = SERIES_DATA[name]
    kwargs = {}
    for key in SERIES_KEYS:
        vals = list(data["vals"][key])
        if ebit_override is not None and key == "ebit":
            vals = list(ebit_override)
        kwargs[key] = vals
    s = StatementSeries(
        ticker=data["ticker"],
        currency="USD",
        periods=[
            FiscalPeriod(period=label, period_end_date=f"{2019 + k}-12-31")
            for k, label in enumerate(data["labels"])
        ],
        **kwargs,
    )
    assert_valid_series(s)
    return s


@pytest.fixture(scope="module")
def series():
    return {
        "synthetic": build_series("synthetic"),
        "realA": build_series("realA"),
        "realB": build_series("realB"),
        "realBNoEbit": build_series("realB", ebit_override=[8200, 8700, 6200, 9200, 9700, None]),
    }


def lin_model(inp):
    a, b = inp["a"], inp["b"]
    return None if a is None or b is None else a * 10 + b


# --------------------------------------------------------------------------
# Case replay: each fixture id → the same Python call
# --------------------------------------------------------------------------

def replay(case_id, s):
    if case_id == "guards_defined":
        return defined([1, None, 2, 3])
    if case_id == "guards_defined_empty":
        return defined([None, None])
    if case_id == "guards_lastValue":
        return last_value([None, 1, None, 2])
    if case_id == "guards_lastValue_empty":
        return last_value([None])
    if case_id == "guards_firstValue":
        return first_value([None, 1, None])
    if case_id == "guards_divSeries":
        return div_series([1, 2, 3], [2, 0, None])
    if case_id == "guards_divSeries_ragged":
        return div_series([1, 2], [1, 2, 4])
    if case_id == "guards_div":
        return [div(1, 2), div(1, 0), div(None, 2)]
    if case_id == "guards_mean":
        return [mean([1, 2, None, 3]), mean([])]
    if case_id == "trends_cagr":
        return cagr(100, 200, 4)
    if case_id == "trends_cagr_nulls":
        return [
            cagr(None, 200, 4),
            cagr(0, 200, 4),
            cagr(-100, 200, 4),
            cagr(100, -50, 4),
            cagr(100, 200, 0),
        ]
    if case_id == "trends_seriesCagr":
        return [
            series_cagr(s["synthetic"].revenue),
            series_cagr(s["realA"].revenue),
            series_cagr([None, None]),
            series_cagr(s["realB"].eps_diluted),
        ]
    if case_id == "trends_yoyGrowth":
        return [
            yoy_growth(s["synthetic"].revenue),
            yoy_growth([100, None, 150]),
            yoy_growth([100, 0, 150]),
        ]
    if case_id == "trends_logLinearTrend":
        return [
            log_linear_trend(s["realA"].revenue),
            log_linear_trend([5, 5, 5, 5]),
            log_linear_trend([1, 2]),
            log_linear_trend(s["synthetic"].revenue),
        ]
    if case_id == "trends_perShareSeries":
        return [
            per_share_series(s["realA"].net_income, s["realA"].shares_outstanding),
            per_share_series([10, 20], [2, 0]),
            per_share_series([10], [2, 4, 8]),
        ]
    if case_id == "trends_marginSeries":
        return [
            margin_series(s["realA"].net_income, s["realA"].revenue),
            margin_series([10, 20], [100, 0]),
        ]
    if case_id == "trends_flattery":
        return [
            flattery(0.05, 0.09),
            flattery(None, 0.1),
            flattery(0.05, 0.052),
            flattery(0.09, 0.05),
        ]
    if case_id == "dupont_point":
        return dupont_point(100, 1000, 5000, 2000)
    if case_id == "dupont_point_nulls":
        return [
            dupont_point(None, 1000, 5000, 2000),
            dupont_point(100, 0, 5000, 2000),
            dupont_point(100, 1000, -5, 2000),
        ]
    if case_id == "dupont_series_synthetic":
        return dupont_series(s["synthetic"])
    if case_id == "dupont_series_realA":
        return dupont_series(s["realA"])
    if case_id == "dupont_roeAttribution":
        rows = dupont_series(s["realA"])
        return roe_attribution(rows[0], rows[5])
    if case_id == "dupont_roeAttribution_null":
        rows_a = dupont_series(s["realA"])
        rows_syn = dupont_series(s["synthetic"])
        return roe_attribution(rows_a[0], rows_syn[2])
    if case_id == "dupont_roeAttribution_unchanged":
        rows = dupont_series(s["realA"])
        return roe_attribution(rows[1], rows[1])
    if case_id == "forensics_sloan":
        return [
            sloan_accruals(100, 80, 1000),
            sloan_accruals(100, 80, 0),
            sloan_accruals(None, 80, 1000),
        ]
    if case_id == "forensics_cashConversion":
        return [cash_conversion(80, 100), cash_conversion(80, 0), cash_conversion(80, -100)]
    if case_id == "forensics_altmanZ":
        return [
            altman_z(s["realA"], 5),
            altman_z(s["synthetic"], 3),
            altman_z(s["realA"], 99),
            altman_z(s["realBNoEbit"], 5),
        ]
    if case_id == "forensics_beneishM":
        return [
            beneish_m(s["realA"], 5),
            beneish_m(s["realA"], 0),
            beneish_m(s["realB"], 5),
            beneish_m(s["realB"], 2),
        ]
    if case_id == "forensics_workingCapitalDays":
        return [
            working_capital_days(s["realA"], 5),
            working_capital_days(s["realA"], 99),
            working_capital_days(s["synthetic"], 0),
        ]
    if case_id == "valuation_capm":
        return [capm_cost_of_equity(0.04, 1.2, 0.05), capm_cost_of_equity(None, 1.2, 0.05)]
    if case_id == "valuation_wacc":
        return [
            wacc(0.1, 0.05, 0.25, 800, 200),
            wacc(0.1, 0.05, 0.25, 0, 0),
            wacc(0.1, 0.05, 0.25, 800, -800),
        ]
    if case_id == "valuation_dcf":
        return [
            dcf(100, [0.1, 0.08, 0.06], 0.1, 0.03),
            dcf(100, [], 0.1, 0.03),
            dcf(100, [0.1], 0.03, 0.03),
            dcf(-50, [0.05, 0.05], 0.1, 0.02),
        ]
    if case_id == "valuation_reverseDcf":
        return [
            reverse_dcf(1500, 100, 0.1, 0.03, 5),
            reverse_dcf(-5, 100, 0.1, 0.03, 5),
            reverse_dcf(1e12, 100, 0.1, 0.03, 5),
            reverse_dcf(1, 100, 0.1, 0.03, 5),
        ]
    if case_id == "valuation_impliedPerpetualGrowth":
        return [
            implied_perpetual_growth(1000, 100, 0.1),
            implied_perpetual_growth(1000, 100, 0),
            implied_perpetual_growth(None, 100, 0.1),
        ]
    if case_id == "valuation_multiplePercentile":
        return [
            multiple_percentile(15, [10, 12, 14, 16, 18]),
            multiple_percentile(None, [1]),
            multiple_percentile(15, []),
            multiple_percentile(15, [10, None, 20]),
        ]
    if case_id == "valuation_sensitivityGrid":
        return sensitivity_grid(
            {"a": 2, "b": 1},
            ("a", [1, 2, 3]),
            ("b", [0, 0.5]),
            lin_model,
        )
    if case_id == "allocation_buybackEffectiveness":
        return [buyback_effectiveness(s["realA"]), buyback_effectiveness(s["synthetic"])]
    if case_id == "allocation_dividendProfile":
        return [dividend_profile(s["realA"]), dividend_profile(s["realB"])]
    if case_id == "allocation_debtProfile":
        return [debt_profile(s["realA"]), debt_profile(s["realB"])]
    if case_id == "expected_expectedValue":
        return [
            expected_value([
                ScenarioInput(label="a", value=100, probability=0.5),
                ScenarioInput(label="b", value=200, probability=0.5),
            ]),
            expected_value([
                ScenarioInput(label="a", value=100, probability=0.33),
                ScenarioInput(label="b", value=200, probability=0.33),
                ScenarioInput(label="c", value=300, probability=0.34),
            ]),
        ]
    if case_id == "expected_expectedValue_errors":
        # Deliberate deviation: TS error messages are prefixed with the TS
        # function name ("expectedValue: "); the Python port prefixes with
        # the snake_case name ("expected_value: "). Normalize the prefix so
        # the comparison covers the diagnostic content, not the name style.
        return [
            {"error": r["error"].replace("expected_value: ", "expectedValue: ")}
            if isinstance(r, dict) and "error" in r
            else r
            for r in [
                expected_value([]),
                expected_value([
                    ScenarioInput(label="a", value=100, probability=0.5),
                    ScenarioInput(label="b", value=200, probability=0.4),
                ]),
                expected_value([ScenarioInput(label="a", value=None, probability=0.5)]),
                expected_value([ScenarioInput(label="a", value=100, probability=-0.5)]),
            ]
        ]
    if case_id == "expected_tornado":
        return tornado(
            {"a": 2, "b": 1}, lin_model, [("a", 0, 4), ("b", 0, 2)]
        )
    if case_id == "expected_marginOfSafety":
        return [
            margin_of_safety(100, 80),
            margin_of_safety(0, 80),
            margin_of_safety(100, 120),
            margin_of_safety(None, 80),
        ]
    if case_id == "expected_solveForInput":
        return [
            solve_for_input(lambda x: 2 * x + 1, 11, 0, 10),
            solve_for_input(lambda x: 10 - x, 3, 0, 10),
            solve_for_input(lambda x: 2 * x + 1, 100, 0, 10),
            solve_for_input(lambda x: None if x > 5 else x, 3, 0, 10),
        ]
    raise KeyError(f"no replay for {case_id}")


# One test per fixture case so failures pinpoint the exact function.
CASE_IDS = [
    "guards_defined", "guards_defined_empty", "guards_lastValue",
    "guards_lastValue_empty", "guards_firstValue", "guards_divSeries",
    "guards_divSeries_ragged", "guards_div", "guards_mean",
    "trends_cagr", "trends_cagr_nulls", "trends_seriesCagr",
    "trends_yoyGrowth", "trends_logLinearTrend", "trends_perShareSeries",
    "trends_marginSeries", "trends_flattery",
    "dupont_point", "dupont_point_nulls", "dupont_series_synthetic",
    "dupont_series_realA", "dupont_roeAttribution",
    "dupont_roeAttribution_null", "dupont_roeAttribution_unchanged",
    "forensics_sloan", "forensics_cashConversion", "forensics_altmanZ",
    "forensics_beneishM", "forensics_workingCapitalDays",
    "valuation_capm", "valuation_wacc", "valuation_dcf",
    "valuation_reverseDcf", "valuation_impliedPerpetualGrowth",
    "valuation_multiplePercentile", "valuation_sensitivityGrid",
    "allocation_buybackEffectiveness", "allocation_dividendProfile",
    "allocation_debtProfile",
    "expected_expectedValue", "expected_expectedValue_errors",
    "expected_tornado", "expected_marginOfSafety",
    "expected_solveForInput",
]


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_parity(case_id, fixtures, series):
    assert set(CASE_IDS) == set(fixtures.keys()), "fixture/case drift"
    actual = normalize(replay(case_id, series))
    assert_close(actual, fixtures[case_id], path=case_id)


# --------------------------------------------------------------------------
# Explicit null-semantics cases from the TS JSDoc (None in → None out)
# --------------------------------------------------------------------------

class TestNullSemantics:
    def test_cagr_non_positive_base(self):
        assert cagr(0, 200, 4) is None
        assert cagr(-100, 200, 4) is None

    def test_cagr_negative_last_is_null(self):
        # fractional power of a negative ratio is undefined on the reals
        assert cagr(100, -50, 4) is None

    def test_cagr_non_positive_periods(self):
        assert cagr(100, 200, 0) is None
        assert cagr(100, 200, -3) is None

    def test_yoy_growth_first_element_always_null(self):
        assert yoy_growth([100, 150])[0] is None

    def test_div_zero_divisor(self):
        assert div(1, 0) is None
        assert div_series([1], [0]) == [None]

    def test_mean_empty(self):
        assert mean([]) is None
        assert mean([None, None]) is None

    def test_altman_z_lists_missing_inputs(self, series):
        r = altman_z(series["realBNoEbit"], 5)
        assert r.z is None and r.zone is None
        assert "ebit" in r.missing
        r2 = altman_z(series["realA"], 99)
        assert r2.missing == ["periodIndex"]

    def test_beneish_m_flag_is_probabilistic_screen(self, fixtures):
        # flag boundary: M > -1.78, exactly as the JSDoc states
        for case in fixtures["forensics_beneishM"]:
            if case["m"] is not None:
                assert case["flag"] == (case["m"] > -1.78)
            else:
                assert case["flag"] is None
                assert case["missing"]

    def test_beneish_m_needs_prior_period(self, series):
        r = beneish_m(series["realA"], 0)
        assert r.m is None and r.missing == ["priorPeriod"]

    def test_working_capital_days_out_of_range(self, series):
        assert working_capital_days(series["realA"], 99) is None

    def test_dcf_divergent_terminal_is_null(self):
        assert dcf(100, [0.1], 0.03, 0.03) is None  # r <= g
        assert dcf(100, [0.1], 0.05, 0.08) is None  # r < g

    def test_reverse_dcf_non_positive_ev_is_null(self):
        assert reverse_dcf(0, 100, 0.1, 0.03, 5) is None
        assert reverse_dcf(-5, 100, 0.1, 0.03, 5) is None

    def test_margin_of_safety_non_positive_anchor(self):
        assert margin_of_safety(0, 80) is None
        assert margin_of_safety(-10, 80) is None
        assert margin_of_safety(100, 120) < 0  # overpriced, not missing

    def test_solve_for_input_unbracketed_is_null(self):
        assert solve_for_input(lambda x: 2 * x + 1, 100, 0, 10) is None

    def test_expected_value_error_messages(self, fixtures):
        errors = fixtures["expected_expectedValue_errors"]
        assert "at least one scenario" in errors[0]["error"]
        assert "probabilities sum to" in errors[1]["error"]
        assert "missing value" in errors[2]["error"]
        assert "negative probability" in errors[3]["error"]


# --------------------------------------------------------------------------
# Spec amendment A1: operating tax rate / NOPAT in incremental_roic
# --------------------------------------------------------------------------

def _a1_series(**overrides):
    """Two-period series for incremental_roic tests; unspecified series are None."""
    n = 2
    kwargs = {key: [None] * n for key in SERIES_KEYS}
    kwargs.update(overrides)
    s = StatementSeries(
        ticker="A1",
        currency="USD",
        periods=[FiscalPeriod(period="FY2023"), FiscalPeriod(period="FY2024")],
        **kwargs,
    )
    assert_valid_series(s)
    return s


class TestOperatingTaxRate:
    def test_happy_path(self):
        # pretax = 1000 − 100 = 900; t = 180/900 = 0.2
        assert operating_tax_rate(1000, 100, 180) == pytest.approx(0.2)

    def test_rate_above_one_is_null_not_clamped(self):
        assert operating_tax_rate(1000, 100, 1000) is None  # 1.11

    def test_negative_rate_is_null(self):
        assert operating_tax_rate(1000, 100, -50) is None

    def test_non_positive_ebit_is_null(self):
        assert operating_tax_rate(0, 100, 180) is None
        assert operating_tax_rate(-100, 100, 180) is None

    def test_non_positive_pretax_is_null(self):
        assert operating_tax_rate(1000, 1000, 180) is None  # pretax = 0
        assert operating_tax_rate(1000, 1200, 180) is None  # pretax < 0

    def test_missing_inputs_are_null(self):
        assert operating_tax_rate(None, 100, 180) is None
        assert operating_tax_rate(1000, None, 180) is None
        assert operating_tax_rate(1000, 100, None) is None


class TestIncrementalRoicA1:
    def _base(self):
        return _a1_series(
            ebit=[1000, 1200],
            interest_expense=[100, 120],
            tax_expense=[180, 216],
            total_equity=[5000, 5500],
            total_debt=[2000, 2100],
            cash=[500, 600],
        )

    def test_hand_computed(self):
        # t0: NOPAT = 1000×0.8 = 800, IC = 5000+2000−500 = 6500
        # t1: NOPAT = 1200×0.8 = 960, IC = 5500+2100−600 = 7000
        # interval: (960−800)/(7000−6500) = 0.32
        r = incremental_roic(self._base())
        assert len(r.by_period) == 1
        assert r.by_period[0].period == "FY2024"
        assert r.by_period[0].value == pytest.approx(0.32)
        assert r.average == pytest.approx(0.32)

    def test_null_tax_rate_nulls_interval(self):
        # tax 2000/1080 > 1 → t null at t1 → interval null, average null
        s = self._base()
        s.tax_expense = [180, 2000]
        r = incremental_roic(s)
        assert r.by_period[0].value is None
        assert r.average is None

    def test_shrinking_capital_base_is_null(self):
        # ΔIC ≤ 0 is economically meaningless — must not reward divestment
        s = self._base()
        s.total_equity = [5000, 4000]
        s.total_debt = [2000, 1500]
        r = incremental_roic(s)
        assert r.by_period[0].value is None
        assert r.average is None

    def test_uses_operating_tax_not_ebit_minus_ni(self):
        # Old (wrong) formula t=(ebit−ni)/ebit would need net_income;
        # net_income is None here — the corrected formula must not care.
        s = self._base()
        assert s.net_income == [None, None]
        r = incremental_roic(s)
        assert r.by_period[0].value == pytest.approx(0.32)


# --------------------------------------------------------------------------
# Spec amendment A2: implied-growth labels
# --------------------------------------------------------------------------

class TestImpliedGrowthLabels:
    def test_reverse_dcf_field_is_labeled_explicit_stage(self):
        r = reverse_dcf(1500, 100, 0.1, 0.03, 5)
        assert r is not None
        assert hasattr(r, "implied_explicit_stage_growth")
        assert not hasattr(r, "implied_growth")
        assert "explicit" in type(r).__doc__

    def test_implied_perpetual_growth_matches_gordon_algebra(self, fixtures):
        # TS lenses/damodaran.impliedGrowth fixture: g = (EV·r − FCF)/(EV + FCF)
        expected = fixtures["valuation_impliedPerpetualGrowth"]
        actual = [
            implied_perpetual_growth(1000, 100, 0.1),
            implied_perpetual_growth(1000, 100, 0),
            implied_perpetual_growth(None, 100, 0.1),
        ]
        assert_close(actual, expected, path="implied_perpetual_growth")

    def test_implied_perpetual_growth_hand_computed(self):
        assert implied_perpetual_growth(1000, 100, 0.1) == pytest.approx(0.0)
        assert implied_perpetual_growth(1200, 100, 0.1) == pytest.approx(20 / 1300)
        assert implied_perpetual_growth(1000, 100, 0) is None
        assert implied_perpetual_growth(1000, -1000, 0.1) is None  # EV + FCF ≤ 0

    def test_two_inversions_answer_different_questions(self):
        # reverse_dcf: constant explicit-stage growth over N years + Gordon terminal
        rd = reverse_dcf(1500, 100, 0.1, 0.03, 5)
        # implied_perpetual_growth: one-period Gordon algebra
        ip = implied_perpetual_growth(1500, 100, 0.1)
        assert rd is not None and ip is not None
        assert rd.implied_explicit_stage_growth != ip


# --------------------------------------------------------------------------
# Series contract validation
# --------------------------------------------------------------------------

class TestSeriesValidation:
    def test_valid_series_passes(self, series):
        assert_valid_series(series["synthetic"])
        assert_valid_series(series["realA"])

    def test_length_mismatch_raises(self, series):
        s = series["synthetic"]
        s.revenue = [1, 2]  # programmer error, not a data gap
        with pytest.raises(ValueError, match="revenue"):
            assert_valid_series(s)

    def test_series_keys_cover_29_line_items(self):
        assert len(SERIES_KEYS) == 29
