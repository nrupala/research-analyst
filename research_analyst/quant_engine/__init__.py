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

"""Research Analyst quantitative engine — Python port of quant/.

Pure functions over multi-year financial statement series. No I/O, no
network, no advice: numbers in, numbers out. See
``research_analyst.quant_engine.series`` for the data contract and sign
conventions.

Ported from quant/src/index.ts, with the locked spec amendments in
docs/quant-engine-spec-amendments.md:
- A1: operating tax rate t = taxExpense / (ebit − interestExpense) in
  incremental ROIC (the old (ebit−ni)/ebit formula is removed).
- A2: "implied explicit-stage growth" (reverse_dcf) vs "implied
  perpetual growth" (implied_perpetual_growth) — never bare
  "implied growth".
"""
# Module: research_analyst/quant_engine/__init__.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

from . import allocation, dupont, expected, forensics, guards, series, trends, valuation
from .allocation import (
    BuybackEffectiveness,
    DebtProfile,
    DividendProfile,
    IncrementalRoic,
    IncrementalRoicPeriod,
    buyback_effectiveness,
    debt_profile,
    dividend_profile,
    incremental_roic,
    operating_tax_rate,
)
from .dupont import (
    DupontComponents,
    DupontPoint,
    DupontRow,
    RoeAttribution,
    dupont_point,
    dupont_series,
    roe_attribution,
)
from .expected import (
    PROBABILITY_SUM_TOLERANCE,
    SOLVE_ITERATIONS,
    ExpectedValueResult,
    ScenarioInput,
    SolveForInputResult,
    TornadoRow,
    expected_value,
    margin_of_safety,
    solve_for_input,
    tornado,
)
from .forensics import (
    AltmanComponents,
    AltmanZone,
    AltmanZResult,
    BeneishMResult,
    BeneishVariables,
    WorkingCapitalDays,
    altman_z,
    beneish_m,
    cash_conversion,
    sloan_accruals,
    working_capital_days,
)
from .guards import defined, div, div_series, first_value, last_value, mean
from .series import (
    SERIES_KEYS,
    FiscalPeriod,
    Series,
    StatementSeries,
    assert_valid_series,
)
from .trends import (
    FlatteryResult,
    LogLinearTrend,
    TrendDirection,
    cagr,
    flattery,
    log_linear_trend,
    margin_series,
    per_share_series,
    series_cagr,
    yoy_growth,
)
from .valuation import (
    REVERSE_DCF_ITERATIONS,
    REVERSE_DCF_MAX_GROWTH,
    REVERSE_DCF_MIN_GROWTH,
    REVERSE_DCF_TOLERANCE,
    DcfResult,
    ReverseDcfResult,
    SensitivityGrid,
    capm_cost_of_equity,
    dcf,
    implied_perpetual_growth,
    multiple_percentile,
    reverse_dcf,
    sensitivity_grid,
    wacc,
)

__all__ = [
    "allocation",
    "dupont",
    "expected",
    "forensics",
    "guards",
    "series",
    "trends",
    "valuation",
    "SERIES_KEYS",
    "FiscalPeriod",
    "Series",
    "StatementSeries",
    "assert_valid_series",
    "defined",
    "div",
    "div_series",
    "first_value",
    "last_value",
    "mean",
    "TrendDirection",
    "LogLinearTrend",
    "FlatteryResult",
    "cagr",
    "series_cagr",
    "yoy_growth",
    "log_linear_trend",
    "per_share_series",
    "margin_series",
    "flattery",
    "DupontComponents",
    "DupontPoint",
    "DupontRow",
    "RoeAttribution",
    "dupont_point",
    "dupont_series",
    "roe_attribution",
    "AltmanZone",
    "AltmanComponents",
    "AltmanZResult",
    "BeneishVariables",
    "BeneishMResult",
    "WorkingCapitalDays",
    "sloan_accruals",
    "cash_conversion",
    "altman_z",
    "beneish_m",
    "working_capital_days",
    "DcfResult",
    "ReverseDcfResult",
    "SensitivityGrid",
    "capm_cost_of_equity",
    "wacc",
    "dcf",
    "reverse_dcf",
    "implied_perpetual_growth",
    "multiple_percentile",
    "sensitivity_grid",
    "REVERSE_DCF_MIN_GROWTH",
    "REVERSE_DCF_MAX_GROWTH",
    "REVERSE_DCF_ITERATIONS",
    "REVERSE_DCF_TOLERANCE",
    "BuybackEffectiveness",
    "DividendProfile",
    "DebtProfile",
    "IncrementalRoicPeriod",
    "IncrementalRoic",
    "buyback_effectiveness",
    "dividend_profile",
    "debt_profile",
    "incremental_roic",
    "operating_tax_rate",
    "ScenarioInput",
    "ExpectedValueResult",
    "TornadoRow",
    "SolveForInputResult",
    "expected_value",
    "tornado",
    "margin_of_safety",
    "solve_for_input",
    "PROBABILITY_SUM_TOLERANCE",
    "SOLVE_ITERATIONS",
]