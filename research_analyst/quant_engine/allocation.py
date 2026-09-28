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

"""Buffett-style capital allocation tests.

Four pure analyses of how management deploys cash: buybacks, dividends,
debt, and incremental reinvestment. All functions are null-safe
(nulls in, nulls out) and never throw on data gaps.

Sign convention (from series.py): share buybacks, dividends paid, and
capital expenditure are POSITIVE MAGNITUDES.

Ported from quant/src/allocation.ts, with spec amendment A1
(docs/quant-engine-spec-amendments.md): the operating tax rate is
t = taxExpense / (ebit − interestExpense), null unless ebit > 0,
pretax > 0 and 0 ≤ t ≤ 1. The old (ebit − netIncome)/ebit formula is
removed, not kept as a fallback.
"""
# Module: research_analyst/quant_engine/allocation.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

from dataclasses import dataclass

from .guards import defined, div, first_value, last_value
from .series import Series, StatementSeries
from .trends import series_cagr


@dataclass
class BuybackEffectiveness:
    """Output of :func:`buyback_effectiveness`."""

    #: CAGR of sharesOutstanding, first → last non-null observation.
    shares_cagr: float | None
    #: Sum of shareBuybacks over the window (positive magnitude). None when no data.
    total_spent: float | None
    #: First − last sharesOutstanding. Positive means shares were retired.
    shares_retired: float | None
    #: totalSpent / sharesRetired — the average price paid per retired share.
    implied_avg_price: float | None
    #: Latest period-end price.
    current_price: float | None
    #: (impliedAvgPrice − currentPrice) / currentPrice. Positive = overpaid vs today.
    premium_vs_market: float | None


def buyback_effectiveness(s: StatementSeries) -> BuybackEffectiveness:
    """Tests whether buybacks created value (Buffett's rule: repurchase only
    below intrinsic value).

    impliedAvgPrice = totalSpent / sharesRetired answers "what did management
    actually pay per share retired?" premiumVsMarket then compares that
    against today's price. A persistent premium means the company bought
    high — the classic buyback value-destruction pattern.

    Null semantics: impliedAvgPrice is None when sharesRetired <= 0 (no net
    retirement — e.g. issuance offset repurchases) or buyback data is missing;
    premiumVsMarket is None when either price is missing or currentPrice is 0.
    """
    shares_cagr = series_cagr(s.shares_outstanding)
    spent = defined(s.share_buybacks)
    total_spent = sum(spent) if spent else None
    first = first_value(s.shares_outstanding)
    last = last_value(s.shares_outstanding)
    shares_retired = None if first is None or last is None else first - last
    implied_avg_price = (
        None
        if total_spent is None or shares_retired is None or shares_retired <= 0
        else total_spent / shares_retired
    )
    current_price = last_value(s.price)
    premium_vs_market = (
        None
        if implied_avg_price is None or current_price is None or current_price == 0
        else (implied_avg_price - current_price) / current_price
    )
    return BuybackEffectiveness(
        shares_cagr=shares_cagr,
        total_spent=total_spent,
        shares_retired=shares_retired,
        implied_avg_price=implied_avg_price,
        current_price=current_price,
        premium_vs_market=premium_vs_market,
    )


@dataclass
class DividendProfile:
    """Output of :func:`dividend_profile`."""

    #: Latest dividendsPaid / latest netIncome. None when either is missing or earnings are 0.
    payout_on_earnings: float | None
    #: Latest dividendsPaid / latest freeCashFlow. None when either is missing or FCF is 0.
    payout_on_fcf: float | None
    #: Trailing consecutive YoY increases in dividends per share, from latest.
    years_grown: int
    #: Count of YoY declines in dividends per share over the whole window.
    cuts: int


def dividend_profile(s: StatementSeries) -> DividendProfile:
    """Dividend sustainability profile.

    payoutOnEarnings and payoutOnFcf use the latest non-null observation of
    each series (they need not come from the same period — documented
    limitation). yearsGrown/cuts are computed on dividends per share so
    buyback-driven per-share growth is not mistaken for dividend growth.
    A flat year breaks the streak; nulls are skipped pairwise.
    """
    payout_on_earnings = div(last_value(s.dividends_paid), last_value(s.net_income))
    payout_on_fcf = div(last_value(s.dividends_paid), last_value(s.free_cash_flow))

    # Per-share dividend series over aligned non-null (dividends, shares) pairs.
    dps: list[float] = []
    n = min(len(s.dividends_paid), len(s.shares_outstanding))
    for i in range(n):
        d = s.dividends_paid[i]
        sh = s.shares_outstanding[i]
        if d is not None and sh is not None and sh > 0:
            dps.append(d / sh)

    years_grown = 0
    for i in range(len(dps) - 1, 0, -1):
        if dps[i] > dps[i - 1]:
            years_grown += 1
        else:
            break
    cuts = sum(1 for i in range(1, len(dps)) if dps[i] < dps[i - 1])
    return DividendProfile(
        payout_on_earnings=payout_on_earnings,
        payout_on_fcf=payout_on_fcf,
        years_grown=years_grown,
        cuts=cuts,
    )


@dataclass
class DebtProfile:
    """Output of :func:`debt_profile`."""

    #: Latest totalDebt − latest cash. Negative = net cash position.
    net_debt_latest: float | None
    #: netDebtLatest / latest ebit. None when ebit is missing or 0.
    net_debt_to_ebit: float | None
    #: Latest ebit / latest interestExpense. None when either is missing or interest is 0.
    interest_coverage: float | None
    #: CAGR of totalDebt, first → last non-null observation.
    debt_cagr: float | None


def debt_profile(s: StatementSeries) -> DebtProfile:
    """Balance-sheet leverage profile.

    netDebtToEbit answers "how many years of operating profit to repay net
    debt"; interestCoverage answers "can operating profit service the
    interest bill". debtCagr shows whether leverage is structurally growing.
    """
    debt = last_value(s.total_debt)
    cash = last_value(s.cash)
    ebit = last_value(s.ebit)
    interest = last_value(s.interest_expense)
    net_debt_latest = None if debt is None or cash is None else debt - cash
    return DebtProfile(
        net_debt_latest=net_debt_latest,
        net_debt_to_ebit=div(net_debt_latest, ebit),
        interest_coverage=div(ebit, interest),
        debt_cagr=series_cagr(s.total_debt),
    )


def operating_tax_rate(
    ebit: float | None,
    interest_expense: float | None,
    tax_expense: float | None,
) -> float | None:
    """Operating tax rate for one period (spec amendment A1).

    t = taxExpense / (ebit − interestExpense), where interest is a positive
    magnitude per the StatementSeries contract, so ``ebit − interestExpense``
    is pretax operating income.

    Returns None unless ``ebit > 0``, ``pretax > 0`` and ``0 ≤ t ≤ 1`` — a
    rate outside [0, 1] is a data artifact, not a rate. Missing stays
    missing, never clamped into a fabricated number.
    """
    if ebit is None or interest_expense is None or tax_expense is None:
        return None
    if ebit <= 0:
        return None
    pretax = ebit - interest_expense
    if pretax <= 0:
        return None
    t = tax_expense / pretax
    if t < 0 or t > 1:
        return None
    return t


@dataclass
class IncrementalRoicPeriod:
    """One interval of :func:`incremental_roic`."""

    #: Period label of the interval's end (e.g. "FY2024").
    period: str
    #: ΔNOPAT / ΔInvestedCapital for the interval, or None (see below).
    value: float | None


@dataclass
class IncrementalRoic:
    """Output of :func:`incremental_roic`."""

    by_period: list[IncrementalRoicPeriod]
    #: Mean of the non-null interval values; None when every interval is None.
    average: float | None


def incremental_roic(s: StatementSeries) -> IncrementalRoic:
    """Incremental return on invested capital per period interval.

    For each interval t−1 → t:
      pretaxOperating_t = ebit_t − interestExpense_t,
      t_t = taxExpense_t / pretaxOperating_t   (see :func:`operating_tax_rate`),
      NOPAT_t = ebit_t × (1 − t_t),
      InvestedCapital_t = totalEquity_t + totalDebt_t − cash_t,
      incremental ROIC = (NOPAT_t − NOPAT_{t−1}) / (IC_t − IC_{t−1}).

    The interval value is None when any input is missing, when either
    endpoint's tax rate is None, OR when ΔInvestedCapital <= 0 (a shrinking
    capital base makes the ratio economically meaningless — it would reward
    divestment as "return"). average is the mean of the non-null values.
    """
    n = len(s.periods)
    by_period: list[IncrementalRoicPeriod] = []
    values: list[float] = []
    prev_nopat: float | None = None
    prev_ic: float | None = None

    def at(values: Series, i: int) -> float | None:
        return values[i] if 0 <= i < len(values) else None

    for i in range(n):
        ebit = at(s.ebit, i)
        interest = at(s.interest_expense, i)
        tax = at(s.tax_expense, i)
        eq = at(s.total_equity, i)
        debt = at(s.total_debt, i)
        cash = at(s.cash, i)

        t = operating_tax_rate(ebit, interest, tax)
        nopat = None if ebit is None or t is None else ebit * (1 - t)
        ic = None if eq is None or debt is None or cash is None else eq + debt - cash

        if i > 0:
            value: float | None = None
            if (
                nopat is not None
                and prev_nopat is not None
                and ic is not None
                and prev_ic is not None
            ):
                d_ic = ic - prev_ic
                value = (nopat - prev_nopat) / d_ic if d_ic > 0 else None
            period = s.periods[i]
            by_period.append(
                IncrementalRoicPeriod(
                    period=period.period if period is not None else f"period-{i}",
                    value=value,
                )
            )
            if value is not None:
                values.append(value)
        prev_nopat = nopat
        prev_ic = ic

    average = sum(values) / len(values) if values else None
    return IncrementalRoic(by_period=by_period, average=average)