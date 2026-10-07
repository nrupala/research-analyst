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

"""Probability-weighted expectation and break-even math.

Pure functions: scenario expected value with strict probability
validation, one-at-a-time sensitivity (tornado), Graham's margin of
safety, and a bisection root-finder for "what input hits this target?".

Nulls in, nulls out — functions return None (or a descriptive error
for expected_value) rather than throwing on missing or invalid data, so
report renderers can print "data unavailable" instead of a fabricated
number. Research/education only: nothing here is a buy/sell signal.

Ported from quant/src/expected.ts.
"""
# Module: research_analyst/quant_engine/expected.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ScenarioInput:
    """One scenario for :func:`expected_value`."""

    label: str
    value: float | None
    probability: float | None


@dataclass
class ExpectedValueResult:
    """Successful result of :func:`expected_value`."""

    #: Σ value_i × probability_i.
    expected: float
    #: Per-scenario value_i × probability_i, in input order.
    contributions: list[dict[str, float | str]]


#: Probability-sum tolerance: Σp must equal 1 ± 0.01. A looser band would
#: silently mis-weight the scenarios; a tighter one would reject honest
#: rounding (e.g. 0.33 + 0.33 + 0.34).
PROBABILITY_SUM_TOLERANCE = 0.01


def expected_value(
    scenarios: list[ScenarioInput],
) -> ExpectedValueResult | dict[str, str]:
    """Probability-weighted expected value over discrete scenarios.

    Formula: E = Σ value_i × probability_i

    Validation (first violation wins, returned as {"error": ...}):
      1. at least one scenario,
      2. every value is present and finite,
      3. every probability is present and finite,
      4. every probability ≥ 0,
      5. Σp = 1 ± 0.01.

    The error branch exists so callers can surface *why* the expectation
    is unavailable instead of silently dropping the scenarios.
    """
    if not scenarios:
        return {"error": "expected_value: at least one scenario is required"}
    clean: list[tuple[str, float, float]] = []
    for sc in scenarios:
        if sc.value is None or not math.isfinite(sc.value):
            return {
                "error": f'expected_value: scenario "{sc.label}" has a missing value'
            }
        if sc.probability is None or not math.isfinite(sc.probability):
            return {
                "error": f'expected_value: scenario "{sc.label}" has a missing probability'
            }
        if sc.probability < 0:
            return {
                "error": f'expected_value: scenario "{sc.label}" has negative probability '
                f"{sc.probability}"
            }
        clean.append((sc.label, sc.value, sc.probability))
    total_probability = sum(p for _, _, p in clean)
    if abs(total_probability - 1) > PROBABILITY_SUM_TOLERANCE:
        return {
            "error": "expected_value: probabilities sum to "
            f"{total_probability}, expected 1 ± {PROBABILITY_SUM_TOLERANCE}"
        }
    expected = 0.0
    contributions: list[dict[str, float | str]] = []
    for label, value, probability in clean:
        contribution = value * probability
        expected += contribution
        contributions.append({"label": label, "contribution": contribution})
    return ExpectedValueResult(expected=expected, contributions=contributions)


@dataclass
class TornadoRow:
    """One row of :func:`tornado`: a single input varied low → high."""

    #: The varied input's name.
    name: str
    #: model() with this input at its low end, others at base.
    low_output: float | None
    #: model() with this input at its high end, others at base.
    high_output: float | None
    #: |highOutput − lowOutput|; 0 when either end is None.
    swing: float


def tornado(
    base: dict[str, float | None],
    model: Callable[[dict[str, float | None]], float | None],
    ranges: list[tuple[str, float, float]],
) -> list[TornadoRow]:
    """One-at-a-time sensitivity ("tornado"): for each range, evaluate the
    model with that input at low and at high while every other input stays
    at its base value.

    Swing = |highOutput − lowOutput| (0 when either end is None), rows
    sorted by descending swing so the largest driver of the output comes
    first. Interaction effects are not captured — this is deliberately a
    first-order screening, not a full factorial design.
    """
    rows: list[TornadoRow] = []
    for name, low, high in ranges:
        low_inputs = dict(base)
        low_inputs[name] = low
        high_inputs = dict(base)
        high_inputs[name] = high
        low_output = model(low_inputs)
        high_output = model(high_inputs)
        swing = (
            abs(high_output - low_output)
            if low_output is not None and high_output is not None
            else 0.0
        )
        rows.append(
            TornadoRow(
                name=name,
                low_output=low_output,
                high_output=high_output,
                swing=swing,
            )
        )
    rows.sort(key=lambda r: r.swing, reverse=True)
    return rows


def margin_of_safety(
    intrinsic_value: float | None, price: float | None
) -> float | None:
    """Graham's margin of safety.

    Formula: MoS = (intrinsicValue − price) / intrinsicValue
    Source: Graham (1949), The Intelligent Investor.

    Positive means the price sits below intrinsic value; negative means
    above. Null semantics: None when intrinsicValue is None/non-finite or
    ≤ 0 (a non-positive anchor cannot define a margin), or when price is
    None/non-finite.
    """
    if (
        intrinsic_value is None
        or not math.isfinite(intrinsic_value)
        or intrinsic_value <= 0
        or price is None
        or not math.isfinite(price)
    ):
        return None
    return (intrinsic_value - price) / intrinsic_value


@dataclass
class SolveForInputResult:
    """Result of :func:`solve_for_input`."""

    #: The input x with model(x) ≈ target.
    input: float
    #: True when |model(input) − target| ≤ 1e-9 × max(1, |target|) after
    #: bisection. False means the model is discontinuous or flat on the
    #: bracket and bisection could not pin the root.
    converged: bool


#: Bisection iterations — the bracket shrinks by 2^100, far past float precision.
SOLVE_ITERATIONS = 100


def solve_for_input(
    model: Callable[[float], float | None],
    target: float,
    lo: float,
    hi: float,
) -> SolveForInputResult | None:
    """Bisection root-finder: the input x in [lo, hi] with model(x) = target.

    Method: bisection (intermediate value theorem) — requires the target
    to be bracketed, i.e. between model(lo) and model(hi) inclusive.
    Works for both increasing and decreasing models; 100 iterations halve
    the bracket far past float precision.

    Null semantics: None when model(lo) or model(hi) is None/non-finite,
    when target is non-finite, when the target is not bracketed, or when
    the model returns None at any probe point mid-search (a hole in the
    model cannot be bisected through).
    """
    f_lo = model(lo)
    f_hi = model(hi)
    if (
        f_lo is None
        or f_hi is None
        or not math.isfinite(f_lo)
        or not math.isfinite(f_hi)
        or not math.isfinite(target)
    ):
        return None
    bracketed = (f_lo <= target <= f_hi) or (f_hi <= target <= f_lo)
    if not bracketed:
        return None
    a, b = lo, hi
    f_a = f_lo
    for _ in range(SOLVE_ITERATIONS):
        mid = (a + b) / 2
        f_mid = model(mid)
        if f_mid is None or not math.isfinite(f_mid):
            return None
        if f_mid == target:
            a = mid
            b = mid
            f_a = f_mid
            break
        # Keep the half-bracket whose ends straddle the target.
        if (f_a <= target and f_mid <= target) or (f_a >= target and f_mid >= target):
            a = mid
            f_a = f_mid
        else:
            b = mid
    result = (a + b) / 2
    f_result = model(result)
    if f_result is None or not math.isfinite(f_result):
        return None
    converged = abs(f_result - target) <= 1e-9 * max(1, abs(target))
    return SolveForInputResult(input=result, converged=converged)
