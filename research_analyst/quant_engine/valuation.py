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

"""Cost of capital and intrinsic-value mathematics.

Pure functions over scalars and short arrays: CAPM cost of equity,
WACC, a two-stage free-cash-flow DCF with a Gordon-growth terminal
value, reverse DCF (implied growth via bisection), the one-period
Gordon-algebra implied perpetual growth, historical multiple
percentiles, and a two-dimensional sensitivity grid.

Nulls in, nulls out — every function returns None (rather than
throwing) when a required input is missing or a guard is violated, so
report renderers can print "data unavailable" instead of a fabricated
number. Research/education only: nothing here is a buy/sell signal.

Ported from quant/src/valuation.ts, with spec amendment A2
(docs/quant-engine-spec-amendments.md): the two implied-growth
inversions carry distinct labels — "implied explicit-stage growth"
for :func:`reverse_dcf`, "implied perpetual growth" for
:func:`implied_perpetual_growth` — never a bare "implied growth".
"""
# Module: research_analyst/quant_engine/valuation.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from .guards import defined
from .series import Series


def capm_cost_of_equity(
    risk_free: float | None,
    beta: float | None,
    equity_risk_premium: float | None,
) -> float | None:
    """Cost of equity from the Sharpe–Lintner–Mossin CAPM.

    Formula: re = rf + β × ERP
    Source: Sharpe (1964), Lintner (1965), Mossin (1966).

    Null semantics: None when any input is None or non-finite — equity
    cannot be priced on risk the caller cannot observe.
    """
    if (
        risk_free is None
        or beta is None
        or equity_risk_premium is None
        or not math.isfinite(risk_free)
        or not math.isfinite(beta)
        or not math.isfinite(equity_risk_premium)
    ):
        return None
    return risk_free + beta * equity_risk_premium


def wacc(
    cost_of_equity: float | None,
    cost_of_debt: float | None,
    tax_rate: float | None,
    market_equity: float | None,
    market_debt: float | None,
) -> float | None:
    """Weighted average cost of capital.

    Formula: WACC = re × (E / V) + rd × (1 − t) × (D / V),  V = E + D

    Null semantics: None when any input is None/non-finite, or when
    V = E + D ≤ 0 (there is no observable capital base to weight).
    """
    for v in (cost_of_equity, cost_of_debt, tax_rate, market_equity, market_debt):
        if v is None or not math.isfinite(v):
            return None
    assert (
        cost_of_equity is not None
        and cost_of_debt is not None
        and tax_rate is not None
        and market_equity is not None
        and market_debt is not None
    )
    v = market_equity + market_debt
    if v <= 0:
        return None
    return (
        (cost_of_equity * market_equity) / v
        + (cost_of_debt * (1 - tax_rate) * market_debt) / v
    )


@dataclass
class DcfResult:
    """Result of :func:`dcf`."""

    #: Present value of the whole projection: pvExplicit + pvTerminal.
    enterprise_value: float
    #: Σ FCF_t / (1+r)^t over the explicit period.
    pv_explicit: float
    #: TV_n / (1+r)^n, the discounted Gordon terminal value.
    pv_terminal: float
    #: The explicit-period free cash flows, undiscounted, oldest → newest.
    cash_flows: list[float | None]


def dcf(
    fcf0: float | None,
    growth_rates: list[float],
    discount_rate: float | None,
    terminal_growth: float | None,
) -> DcfResult | None:
    """Two-stage free-cash-flow DCF with a Gordon-growth terminal value.

    Explicit period (t = 1..n, n = len(growth_rates)):
      FCF_t = fcf0 × Π_{i=1..t} (1 + g_i)
    Terminal value at year n (Gordon & Shapiro, 1956):
      TV_n = FCF_n × (1 + g) / (r − g)
    Enterprise value:
      EV = Σ_{t=1..n} FCF_t / (1 + r)^t  +  TV_n / (1 + r)^n

    Null semantics: None when fcf0, discountRate or terminalGrowth is
    None/non-finite, when growthRates is empty, when any growth rate is
    non-finite, or when discountRate ≤ terminalGrowth — the Gordon series
    diverges there, so the terminal value would be infinite or negative.
    """
    if (
        fcf0 is None
        or discount_rate is None
        or terminal_growth is None
        or not math.isfinite(fcf0)
        or not math.isfinite(discount_rate)
        or not math.isfinite(terminal_growth)
        or len(growth_rates) == 0
        or discount_rate <= terminal_growth
    ):
        return None
    cash_flows: list[float] = []
    fcf = fcf0
    for g in growth_rates:
        if not math.isfinite(g):
            return None
        fcf = fcf * (1 + g)
        cash_flows.append(fcf)
    pv_explicit = 0.0
    discount_factor = 1.0  # (1 + r)^t after t iterations
    for cf in cash_flows:
        discount_factor *= 1 + discount_rate
        pv_explicit += cf / discount_factor
    # cash_flows is non-empty (growth_rates was non-empty).
    last_fcf = cash_flows[-1]
    terminal_value = (
        (last_fcf * (1 + terminal_growth)) / (discount_rate - terminal_growth)
    )
    pv_terminal = terminal_value / discount_factor  # discount_factor is (1+r)^n now
    return DcfResult(
        enterprise_value=pv_explicit + pv_terminal,
        pv_explicit=pv_explicit,
        pv_terminal=pv_terminal,
        cash_flows=list(cash_flows),
    )


@dataclass
class ReverseDcfResult:
    """Result of :func:`reverse_dcf`.

    Per spec amendment A2, the solved rate is labeled **implied
    explicit-stage growth** — the constant near-term growth the business
    must deliver for today's EV to be fair. Never "implied growth" bare.
    """

    #: The constant explicit-period growth rate that prices the DCF at the
    #: current enterprise value. Clamped to the searched interval
    #: [-0.5, 1.0] when the value lies outside the model's range.
    implied_explicit_stage_growth: float
    #: True when |dcf(implied) − currentEV| / currentEV < 1e-6.
    converged: bool


#: Search interval for the implied growth rate (see :func:`reverse_dcf`).
REVERSE_DCF_MIN_GROWTH = -0.5
REVERSE_DCF_MAX_GROWTH = 1.0
#: Bisection iterations — the bracket shrinks by 2^100, far past float precision.
REVERSE_DCF_ITERATIONS = 100
#: Relative tolerance on enterprise value for convergence.
REVERSE_DCF_TOLERANCE = 1e-6


def reverse_dcf(
    current_ev: float | None,
    fcf0: float | None,
    discount_rate: float | None,
    terminal_growth: float | None,
    years: int,
) -> ReverseDcfResult | None:
    """Reverse DCF: the constant explicit-period growth rate g implied by the
    market's current enterprise value — the **implied explicit-stage growth**.

    Inverts :func:`dcf` by bisection (intermediate value theorem): with
    growthRates = [g, g, …, g] (years entries), EV(g) is continuous in g,
    so the equation dcf(g) = currentEV is solved by halving the bracket
    [−0.5, 1.0] 100 times. Handles both increasing (fcf0 > 0) and
    decreasing (fcf0 < 0) EV(g) orderings.

    When currentEV lies outside the model's range on [−0.5, 1.0] there is
    no in-interval root; the function returns the nearest bound with
    converged=False rather than inventing a growth rate outside the
    searched interval.

    Null semantics: None when currentEV is None/non-finite or ≤ 0, when
    years is not a positive integer, or when any dcf guard fails
    (fcf0 / discountRate / terminalGrowth missing, or r ≤ terminalGrowth).
    """
    if (
        current_ev is None
        or not math.isfinite(current_ev)
        or current_ev <= 0
        or not isinstance(years, int)
        or isinstance(years, bool)
        or years < 1
    ):
        return None

    def ev_at(g: float) -> float | None:
        result = dcf(fcf0, [g] * years, discount_rate, terminal_growth)
        return None if result is None else result.enterprise_value

    # Probe the bracket ends first: this also enforces dcf's own guards.
    ev_lo = ev_at(REVERSE_DCF_MIN_GROWTH)
    ev_hi = ev_at(REVERSE_DCF_MAX_GROWTH)
    if ev_lo is None or ev_hi is None:
        return None
    res_lo = ev_lo - current_ev
    res_hi = ev_hi - current_ev
    # currentEV outside the model's range on the interval: no in-bracket root.
    if res_lo > 0 and res_hi > 0:
        return ReverseDcfResult(
            implied_explicit_stage_growth=REVERSE_DCF_MIN_GROWTH, converged=False
        )
    if res_lo < 0 and res_hi < 0:
        return ReverseDcfResult(
            implied_explicit_stage_growth=REVERSE_DCF_MAX_GROWTH, converged=False
        )
    lo = REVERSE_DCF_MIN_GROWTH
    hi = REVERSE_DCF_MAX_GROWTH
    res_at_lo = res_lo
    for _ in range(REVERSE_DCF_ITERATIONS):
        mid = (lo + hi) / 2
        ev_mid = ev_at(mid)
        if ev_mid is None:
            return None  # unreachable: dcf is valid on the whole bracket
        res_mid = ev_mid - current_ev
        if res_mid == 0:
            lo = mid
            hi = mid
            break
        # Keep the half-bracket whose ends straddle zero.
        if (res_at_lo <= 0 and res_mid <= 0) or (res_at_lo >= 0 and res_mid >= 0):
            lo = mid
            res_at_lo = res_mid
        else:
            hi = mid
    implied = (lo + hi) / 2
    ev_implied = ev_at(implied)
    if ev_implied is None:
        return None  # unreachable, same as above
    converged = abs(ev_implied - current_ev) / current_ev < REVERSE_DCF_TOLERANCE
    return ReverseDcfResult(
        implied_explicit_stage_growth=implied, converged=converged
    )


def implied_perpetual_growth(
    enterprise_value: float | None,
    free_cash_flow: float | None,
    discount_rate: float | None,
) -> float | None:
    """Implied perpetual growth from a reverse DCF, solved algebraically.

    Constant-growth Gordon model on free cash flow:
      EV = FCF × (1 + g) / (r − g),   with r > g.
    Solve for g:
      EV×r − FCF = g × (EV + FCF)
      g = (EV×r − FCF) / (EV + FCF).

    Reads as: "what *perpetual* growth rate is the current enterprise value
    already pricing in, given this discount rate?" — the **implied
    perpetual growth** (spec amendment A2). This is the one-period Gordon
    inversion, distinct from :func:`reverse_dcf`'s explicit-stage bisection.

    Formula source: quant/src/lenses/damodaran.ts ``impliedGrowth``
    (relocated here with its corrected label; the TS lens itself is not
    ported). Null when any input is missing, r ≤ 0, or EV + FCF ≤ 0. An
    implied g ≥ r is economically impossible under the Gordon model
    (denominator r − g ≤ 0) — it means the price cannot be justified by
    any constant growth rate.
    """
    if (
        enterprise_value is None
        or free_cash_flow is None
        or discount_rate is None
    ):
        return None
    if discount_rate <= 0:
        return None
    denom = enterprise_value + free_cash_flow
    if denom <= 0:
        return None
    return (enterprise_value * discount_rate - free_cash_flow) / denom


def multiple_percentile(
    current: float | None, history: Series
) -> float | None:
    """Historical percentile of a current multiple (e.g. P/E, EV/EBITDA).

    Formula: 100 × |{ h ∈ history : h ≤ current }| / |history|,
    over the non-null, finite values of history.

    Null semantics: None when current is None/non-finite, or when history
    has no observable values to rank against.
    """
    if current is None or not math.isfinite(current):
        return None
    past = defined(history)
    if not past:
        return None
    at_or_below = sum(1 for v in past if v <= current)
    return (100 * at_or_below) / len(past)


@dataclass
class SensitivityGrid:
    """Result of :func:`sensitivity_grid`."""

    #: varyA.values, in order — the row axis.
    row_labels: list[float]
    #: varyB.values, in order — the column axis.
    col_labels: list[float]
    #: values[i][j] = model with varyA = rowLabels[i], varyB = colLabels[j].
    values: list[list[float | None]]


def sensitivity_grid(
    base: dict[str, float | None],
    vary_a: tuple[str, list[float]],
    vary_b: tuple[str, list[float]],
    model: Callable[[dict[str, float | None]], float | None],
) -> SensitivityGrid:
    """Two-dimensional sensitivity grid: evaluates model() over the Cartesian
    product varyA.values (rows) × varyB.values (columns), holding every
    other input at its base value.

    Null semantics: a cell is None wherever the model returns None for
    that input combination; the grid itself is always returned.
    """
    name_a, values_a = vary_a
    name_b, values_b = vary_b
    row_labels = list(values_a)
    col_labels = list(values_b)
    values: list[list[float | None]] = []
    for a in values_a:
        row: list[float | None] = []
        for b in values_b:
            inputs = dict(base)
            inputs[name_a] = a
            inputs[name_b] = b
            row.append(model(inputs))
        values.append(row)
    return SensitivityGrid(
        row_labels=row_labels, col_labels=col_labels, values=values
    )