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

"""Earnings-quality and distress forensics.

- Sloan (1996) accruals: high accruals predict lower earnings persistence.
- Cash conversion: how much of reported profit arrived as cash.
- Altman (1968) Z-score: manufacturing bankruptcy-prediction model.
- Beneish (1999) M-score: eight-variable earnings-manipulation screen.
- Working-capital days: DSO / DIO / DPO cash-conversion-cycle inputs.

These are screens, not verdicts: the Altman cutoffs were fit on 1960s
US manufacturers, and the Beneish flag is probabilistic. Nulls in,
nulls out — missing inputs are reported, never silently dropped.

Ported from quant/src/forensics.ts.
"""
# Module: research_analyst/quant_engine/forensics.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from .guards import div
from .series import Series, StatementSeries

#: Altman Z-score distress zone.
AltmanZone = Literal["safe", "grey", "distress"]


def _at(values: Series, i: int) -> float | None:
    """Read index i of a series; out-of-range or non-finite becomes None."""
    if 0 <= i < len(values):
        v = values[i]
        return v if v is not None and math.isfinite(v) else None
    return None


def sloan_accruals(
    net_income: float | None,
    operating_cash_flow: float | None,
    total_assets: float | None,
) -> float | None:
    """Sloan (1996) accruals ratio: (netIncome − operatingCashFlow) / totalAssets.

    Sloan, R.G. (1996), "Do Stock Prices Fully Reflect Information in
    Accruals and Cash Flows about Future Earnings?", The Accounting Review.
    Finding: the accrual component of earnings is less persistent than the
    cash-flow component, so high positive accruals warn of lower-quality,
    less repeatable earnings.

    Returns None when any input is None or totalAssets <= 0.
    """
    if net_income is None or operating_cash_flow is None or total_assets is None:
        return None
    if total_assets <= 0:
        return None
    return (net_income - operating_cash_flow) / total_assets


def cash_conversion(
    operating_cash_flow: float | None, net_income: float | None
) -> float | None:
    """Cash conversion: operatingCashFlow / netIncome.

    The share of reported profit that materialized as operating cash.
    Sustained readings well below 1.0 mean profits are not turning into
    cash; readings above 1.0 are normal for capital-heavy businesses
    (depreciation is a non-cash charge).

    Returns None when either input is None or netIncome is 0. A negative
    netIncome still yields a (negative) ratio — None means "no data", not
    "bad".
    """
    if operating_cash_flow is None or net_income is None or net_income == 0:
        return None
    return operating_cash_flow / net_income


@dataclass
class AltmanComponents:
    """The five Altman (1968) discriminant variables."""

    #: (currentAssets − currentLiabilities) / totalAssets — working capital.
    x1: float
    #: retainedEarnings / totalAssets — cumulative profitability.
    x2: float
    #: ebit / totalAssets — operating productivity of assets.
    x3: float
    #: (price × sharesOutstanding) / totalLiabilities — market leverage.
    x4: float
    #: revenue / totalAssets — asset turnover.
    x5: float


@dataclass
class AltmanZResult:
    """Altman Z-score result.

    On success: z/zone/components set and ``missing`` empty. On failure:
    z/zone/components are None and ``missing`` names every unavailable
    input (series key, e.g. "ebit", or "periodIndex" when i is out of
    range, or "totalAssets" / "totalLiabilities" when non-positive).
    """

    z: float | None
    zone: AltmanZone | None
    components: AltmanComponents | None
    missing: list[str] = field(default_factory=list)


def altman_z(s: StatementSeries, i: int) -> AltmanZResult:
    """Altman (1968) Z-score for public manufacturers, at period index i.

    Altman, E.I. (1968), "Financial Ratios, Discriminant Analysis and the
    Prediction of Corporate Bankruptcy", Journal of Finance.

      Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5
      X1 = (CA − CL)/TA, X2 = RE/TA, X3 = EBIT/TA,
      X4 = marketCap/totalLiabilities, X5 = revenue/TA

    Zones: Z > 2.99 "safe"; 1.81 ≤ Z ≤ 2.99 "grey" (zone of ignorance);
    Z < 1.81 "distress". Cutoffs were fit on 1960s US manufacturers —
    do not apply the model to banks, insurers, or private firms
    (X4 needs a market price).
    """
    if not isinstance(i, int) or i < 0 or i >= len(s.periods):
        return AltmanZResult(z=None, zone=None, components=None, missing=["periodIndex"])
    missing: list[str] = []

    def need(key: str, v: float | None) -> float | None:
        if v is None:
            missing.append(key)
        return v

    ca = need("currentAssets", _at(s.current_assets, i))
    cl = need("currentLiabilities", _at(s.current_liabilities, i))
    ta = need("totalAssets", _at(s.total_assets, i))
    re = need("retainedEarnings", _at(s.retained_earnings, i))
    ebit = need("ebit", _at(s.ebit, i))
    price = need("price", _at(s.price, i))
    shares = need("sharesOutstanding", _at(s.shares_outstanding, i))
    tl = need("totalLiabilities", _at(s.total_liabilities, i))
    rev = need("revenue", _at(s.revenue, i))
    if ta is not None and ta <= 0:
        missing.append("totalAssets")
    if tl is not None and tl <= 0:
        missing.append("totalLiabilities")

    if (
        missing
        or ca is None
        or cl is None
        or ta is None
        or re is None
        or ebit is None
        or price is None
        or shares is None
        or tl is None
        or rev is None
    ):
        return AltmanZResult(z=None, zone=None, components=None, missing=missing)

    components = AltmanComponents(
        x1=(ca - cl) / ta,
        x2=re / ta,
        x3=ebit / ta,
        x4=(price * shares) / tl,
        x5=rev / ta,
    )
    z = (
        1.2 * components.x1
        + 1.4 * components.x2
        + 3.3 * components.x3
        + 0.6 * components.x4
        + 1.0 * components.x5
    )
    # Exact-boundary rule: Z == 2.99 or Z == 1.81 falls in "grey".
    zone: AltmanZone = "safe" if z > 2.99 else ("distress" if z < 1.81 else "grey")
    return AltmanZResult(z=z, zone=zone, components=components, missing=[])


@dataclass
class BeneishVariables:
    """The eight Beneish (1999) variables, period t vs t−1."""

    #: Days-sales-in-receivables index.
    dsri: float
    #: Gross-margin index.
    gmi: float
    #: Asset-quality index.
    aqi: float
    #: Sales-growth index.
    sgi: float
    #: Depreciation index.
    depi: float
    #: SG&A index.
    sgai: float
    #: Leverage index.
    lvgi: float
    #: Total accruals to total assets.
    tata: float


@dataclass
class BeneishMResult:
    """Beneish M-score result.

    On success: m/flag/variables set and ``missing`` empty. On failure:
    m/flag/variables are None and ``missing`` names every variable that
    could not be built ("DSRI" … "TATA"), or "priorPeriod" when i < 1.
    """

    m: float | None
    flag: bool | None
    variables: BeneishVariables | None
    missing: list[str] = field(default_factory=list)


def beneish_m(s: StatementSeries, i: int) -> BeneishMResult:
    """Beneish (1999) M-score at period index i, vs period i−1.

    Beneish, M.D. (1999), "The Detection of Earnings Manipulation",
    Financial Analysts Journal.

      DSRI = (recv_t/rev_t) / (recv_{t−1}/rev_{t−1})
      GMI  = [(rev−COGS)/rev]_{t−1} / [(rev−COGS)/rev]_t, COGS = revenue − grossProfit
      AQI  = [1 − (CA+PPE)/TA]_t / [1 − (CA+PPE)/TA]_{t−1}
      SGI  = rev_t / rev_{t−1}
      DEPI = [dep/(PPE+dep)]_{t−1} / [dep/(PPE+dep)]_t   (dep = depreciationAmortization,
             a positive magnitude per the StatementSeries contract)
      SGAI = (sga/rev)_t / (sga/rev)_{t−1}
      LVGI = [(CL+totalDebt)/TA]_t / [(CL+totalDebt)/TA]_{t−1}
      TATA = (netIncome − operatingCashFlow) / TA_t

      M = −4.84 + 0.92·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI
          + 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI

    flag = M > −1.78 (Beneish's manipulator cutoff). A flag is a screen
    for further review, not proof of manipulation.
    """
    if not isinstance(i, int) or i < 1 or i >= len(s.periods):
        return BeneishMResult(m=None, flag=None, variables=None, missing=["priorPeriod"])
    t, p = i, i - 1

    recv_t = _at(s.receivables, t)
    recv_p = _at(s.receivables, p)
    rev_t = _at(s.revenue, t)
    rev_p = _at(s.revenue, p)
    gp_t = _at(s.gross_profit, t)
    gp_p = _at(s.gross_profit, p)
    ca_t = _at(s.current_assets, t)
    ca_p = _at(s.current_assets, p)
    ppe_t = _at(s.ppe_net, t)
    ppe_p = _at(s.ppe_net, p)
    ta_t = _at(s.total_assets, t)
    ta_p = _at(s.total_assets, p)
    dep_t = _at(s.depreciation_amortization, t)
    dep_p = _at(s.depreciation_amortization, p)
    sga_t = _at(s.sga_expense, t)
    sga_p = _at(s.sga_expense, p)
    cl_t = _at(s.current_liabilities, t)
    cl_p = _at(s.current_liabilities, p)
    debt_t = _at(s.total_debt, t)
    debt_p = _at(s.total_debt, p)
    ni_t = _at(s.net_income, t)
    ocf_t = _at(s.operating_cash_flow, t)

    def add(a: float | None, b: float | None) -> float | None:
        return None if a is None or b is None else a + b

    def base(num: float | None, den: float | None) -> float | None:
        return None if num is None or den is None or den == 0 else num / den

    def sub1(v: float | None) -> float | None:
        return None if v is None else 1 - v

    dsri = div(div(recv_t, rev_t), div(recv_p, rev_p))
    gmi = div(div(gp_p, rev_p), div(gp_t, rev_t))
    aqi = div(
        sub1(div(add(ca_t, ppe_t), ta_t)),
        sub1(div(add(ca_p, ppe_p), ta_p)),
    )
    sgi = div(rev_t, rev_p)
    depi = div(
        base(dep_p, add(ppe_p, dep_p)),
        base(dep_t, add(ppe_t, dep_t)),
    )
    sgai = div(div(sga_t, rev_t), div(sga_p, rev_p))
    lvgi = div(
        base(add(cl_t, debt_t), ta_t),
        base(add(cl_p, debt_p), ta_p),
    )
    tata = (
        None
        if ni_t is None or ocf_t is None or ta_t is None or ta_t <= 0
        else (ni_t - ocf_t) / ta_t
    )

    entries: list[tuple[str, float | None]] = [
        ("DSRI", dsri),
        ("GMI", gmi),
        ("AQI", aqi),
        ("SGI", sgi),
        ("DEPI", depi),
        ("SGAI", sgai),
        ("LVGI", lvgi),
        ("TATA", tata),
    ]
    missing = [k for k, v in entries if v is None]

    if (
        missing
        or dsri is None
        or gmi is None
        or aqi is None
        or sgi is None
        or depi is None
        or sgai is None
        or lvgi is None
        or tata is None
    ):
        return BeneishMResult(m=None, flag=None, variables=None, missing=missing)

    variables = BeneishVariables(
        dsri=dsri, gmi=gmi, aqi=aqi, sgi=sgi,
        depi=depi, sgai=sgai, lvgi=lvgi, tata=tata,
    )
    m = (
        -4.84
        + 0.92 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi
    )
    return BeneishMResult(m=m, flag=m > -1.78, variables=variables, missing=[])


@dataclass
class WorkingCapitalDays:
    """DSO / DIO / DPO in days; each independently None when inputs missing."""

    #: receivables / revenue × 365.
    dso: float | None
    #: inventory / COGS × 365, COGS = revenue − grossProfit.
    dio: float | None
    #: accountsPayable / COGS × 365.
    dpo: float | None


def working_capital_days(s: StatementSeries, i: int) -> WorkingCapitalDays | None:
    """Working-capital days at period index i.

      DSO = receivables / revenue × 365
      DIO = inventory / (revenue − grossProfit) × 365
      DPO = accountsPayable / (revenue − grossProfit) × 365

    Rising DSO/DIO with flat DPO means cash is being trapped in
    receivables and inventory — a classic earnings-quality tell that
    pairs with the Sloan accruals screen above.

    Returns None only when i is out of range; otherwise each field is
    independently None when its own inputs are missing (or COGS is 0).
    """
    if not isinstance(i, int) or i < 0 or i >= len(s.periods):
        return None
    recv = _at(s.receivables, i)
    rev = _at(s.revenue, i)
    inv = _at(s.inventory, i)
    gp = _at(s.gross_profit, i)
    ap = _at(s.accounts_payable, i)
    cogs = None if rev is None or gp is None else rev - gp

    def ratio_days(num: float | None, den: float | None) -> float | None:
        return None if num is None or den is None or den == 0 else (num / den) * 365

    return WorkingCapitalDays(
        dso=ratio_days(recv, rev),
        dio=ratio_days(inv, cogs),
        dpo=ratio_days(ap, cogs),
    )
