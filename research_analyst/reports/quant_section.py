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

"""Quantitative Engine report section.

Renders the ported quant engine (``research_analyst.quant_engine``) as a
report section appended AFTER the 7 template steps — never numbered as a
step. Research and education only: every number ships with its formula,
the periods it was computed over, and the inputs that were missing. Altman
Z and Beneish M are framed as screens, not verdicts. No buy/sell/hold
language anywhere.

``compute_quant_results`` is the single computation path shared by the
report section and the ``/api/research/quant`` endpoint.
"""
# Module: research_analyst/reports/quant_section.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

import logging
import math
from typing import Any

from ..models import Assumption, ReportSection
from ..quant_engine import allocation, dupont, forensics, guards, trends, valuation
from ..quant_engine.adapter import missing_series_inputs
from ..quant_engine.series import StatementSeries

logger = logging.getLogger(__name__)

__all__ = ["render_quant_section", "compute_quant_results", "QUANT_SECTION_TITLE"]

#: Section title. Rendered without a step number (see ReportOutput.to_markdown).
QUANT_SECTION_TITLE = "Quantitative Engine"

#: step_number 0 marks "not one of the 7 template steps".
_QUANT_STEP_NUMBER = 0

_EDUCATION_NOTE = (
    "Research and education only — these are computed quantities from reported "
    "financial statements, not investment advice."
)

#: Terminal growth assumption for the reverse-DCF explicit-stage inversion.
_TERMINAL_GROWTH = 0.025
#: Explicit-stage window for the reverse-DCF inversion.
_EXPLICIT_YEARS = 5


def _fmt(value: float | None, *, pct: bool = False, digits: int = 2) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    v = value * 100 if pct else value
    return f"{v:.{digits}f}{'%' if pct else ''}"


def _period_range(series: StatementSeries) -> str:
    if not series.periods:
        return "no periods"
    first = series.periods[0].period
    last = series.periods[-1].period
    return f"{first}–{last}" if first != last else first


def compute_quant_results(
    series: StatementSeries, market: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Run every quant-engine phase over the series; return a plain dict.

    Never raises on data gaps — missing inputs are collected in
    ``missing_inputs`` instead. Numbers are floats or None (JSON-safe).
    """
    market = market or {}
    missing: list[str] = []
    assumptions: list[str] = []

    for key in missing_series_inputs(series):
        missing.append(f"{key} (no data from providers)")

    n = len(series.periods)
    last_idx = n - 1
    period_range = _period_range(series)

    # ---- Trends ----
    rev_cagr = trends.series_cagr(series.revenue)
    eps_cagr = trends.series_cagr(series.eps_diluted)
    fcf_cagr = trends.series_cagr(series.free_cash_flow)
    gross_m = guards.last_value(trends.margin_series(series.gross_profit, series.revenue))
    net_m = guards.last_value(trends.margin_series(series.net_income, series.revenue))
    yoy_rev_latest = guards.last_value(trends.yoy_growth(series.revenue))

    # ---- DuPont ----
    dupont_rows = dupont.dupont_series(series)
    latest_dupont = dupont_rows[-1] if dupont_rows else None
    dupont_latest: dict[str, Any] = {
        "period": None, "roe": None, "net_margin": None,
        "asset_turnover": None, "leverage": None,
    }
    dupont_all: list[dict[str, Any]] = []
    attribution: dict[str, Any] = {
        "roe_change_pp": None, "margin_contribution_pp": None,
        "turnover_contribution_pp": None, "leverage_contribution_pp": None,
    }
    if latest_dupont is not None and latest_dupont.roe is not None:
        dupont_latest = {
            "period": latest_dupont.period, "roe": latest_dupont.roe,
            "net_margin": latest_dupont.net_margin,
            "asset_turnover": latest_dupont.asset_turnover,
            "leverage": latest_dupont.leverage,
        }
        for row in dupont_rows:
            dupont_all.append({
                "period": row.period,
                "roe": row.roe,
                "net_margin": row.net_margin,
                "asset_turnover": row.asset_turnover,
                "leverage": row.leverage,
            })
        first_row = dupont_rows[0]
        if len(dupont_rows) > 1 and first_row.roe is not None:
            attr = dupont.roe_attribution(first_row, latest_dupont)
            if attr is not None:
                attribution = {
                    "roe_change_pp": attr.margin_pts + attr.turnover_pts + attr.leverage_pts,
                    "margin_contribution_pp": attr.margin_pts,
                    "turnover_contribution_pp": attr.turnover_pts,
                    "leverage_contribution_pp": attr.leverage_pts,
                }
    else:
        missing.append("dupont_inputs (net_income/revenue/total_assets/total_equity)")

    # ---- Forensics ----
    az = forensics.altman_z(series, last_idx)
    bm = forensics.beneish_m(series, last_idx)
    ni_last = guards.last_value(series.net_income)
    ocf_last = guards.last_value(series.operating_cash_flow)
    ta_last = guards.last_value(series.total_assets)
    sloan = forensics.sloan_accruals(ni_last, ocf_last, ta_last)
    cconv = forensics.cash_conversion(ocf_last, ni_last)
    if az.missing:
        missing.extend(f"altman_z: {m}" for m in az.missing)
    if bm.missing:
        missing.extend(f"beneish_m: {m}" for m in bm.missing)

    # ---- Valuation ----
    price = market.get("price")
    ev = market.get("enterprise_value")
    fcf_last = guards.last_value(series.free_cash_flow)
    discount_rate = market.get("discount_rate")

    eps_last = guards.last_value(series.eps_diluted)
    te_last = guards.last_value(series.total_equity)
    sh_last = guards.last_value(series.shares_outstanding)
    bvps = te_last / sh_last if te_last and sh_last and sh_last > 0 else None
    graham = (
        math.sqrt(22.5 * eps_last * bvps)
        if eps_last and eps_last > 0 and bvps and bvps > 0
        else None
    )
    lynch_fv = None
    if eps_last and eps_last > 0 and eps_cagr and eps_cagr > 0:
        lynch_fv = eps_last * (eps_cagr * 100)
    if graham is None:
        missing.append("graham_number (needs eps_diluted > 0 and book value per share > 0)")
    if lynch_fv is None:
        missing.append("lynch_fair_value (needs eps_diluted > 0 and positive EPS CAGR)")

    explicit_g: float | None = None
    perpetual_g: float | None = None
    if discount_rate is not None:
        assumptions.append(
            f"Discount rate r = {_fmt(discount_rate, pct=True)} (analyst assumption, "
            "not observed market data) used for the implied-growth inversions."
        )
        rdcf = valuation.reverse_dcf(ev, fcf_last, discount_rate, _TERMINAL_GROWTH, _EXPLICIT_YEARS)
        explicit_g = rdcf.implied_explicit_stage_growth if rdcf is not None else None
        perpetual_g = valuation.implied_perpetual_growth(ev, fcf_last, discount_rate)
        if explicit_g is None:
            missing.append(
                "implied_explicit_stage_growth (needs enterprise_value, free_cash_flow, discount_rate)"
            )
        if perpetual_g is None:
            missing.append(
                "implied_perpetual_growth (needs enterprise_value, free_cash_flow, discount_rate)"
            )
    else:
        missing.append("discount_rate (analyst assumption) — implied-growth rows need it")

    # ---- Allocation ----
    iroic = allocation.incremental_roic(series)
    tax_rates = [
        allocation.operating_tax_rate(
            series.ebit[i] if i < len(series.ebit) else None,
            series.interest_expense[i] if i < len(series.interest_expense) else None,
            series.tax_expense[i] if i < len(series.tax_expense) else None,
        )
        for i in range(n)
    ]
    tax_latest = next((t for t in reversed(tax_rates) if t is not None), None)
    if iroic.average is None:
        missing.append(
            "incremental_roic (needs ebit, interest_expense, tax_expense and "
            "invested-capital inputs across the interval)"
        )
    divp = allocation.dividend_profile(series)
    debtp = allocation.debt_profile(series)
    bb = allocation.buyback_effectiveness(series)

    # Dedupe missing while preserving order.
    seen: set[str] = set()
    missing_inputs: list[str] = []
    for m in missing:
        if m not in seen:
            seen.add(m)
            missing_inputs.append(m)

    return {
        "period_range": period_range,
        "n_periods": n,
        "trends": {
            "revenue_cagr": rev_cagr,
            "eps_cagr": eps_cagr,
            "fcf_cagr": fcf_cagr,
            "yoy_revenue_growth_latest": yoy_rev_latest,
            "gross_margin_latest": gross_m,
            "net_margin_latest": net_m,
        },
        "dupont": {
            "rows": dupont_all,
            "latest": dupont_latest,
            "attribution": attribution,
        },
        "forensics": {
            "altman_z": az.z,
            "altman_zone": az.zone,
            "altman_missing": list(az.missing),
            "beneish_m": bm.m,
            "beneish_flag": bm.flag,
            "beneish_missing": list(bm.missing),
            "sloan_accruals": sloan,
            "cash_conversion": cconv,
        },
        "valuation": {
            "graham_number": graham,
            "lynch_fair_value": lynch_fv,
            "implied_explicit_stage_growth": explicit_g,
            "implied_perpetual_growth": perpetual_g,
            "discount_rate_used": discount_rate,
        },
        "allocation": {
            "incremental_roic_average": iroic.average,
            "operating_tax_rate_latest": tax_latest,
            "dividend_payout_on_earnings": divp.payout_on_earnings,
            "dividend_payout_on_fcf": divp.payout_on_fcf,
            "dividend_years_grown": divp.years_grown,
            "dividend_cuts": divp.cuts,
            "debt_net_debt_latest": debtp.net_debt_latest,
            "debt_net_debt_to_ebit": debtp.net_debt_to_ebit,
            "debt_interest_coverage": debtp.interest_coverage,
            "debt_cagr": debtp.debt_cagr,
            "buyback_shares_cagr": bb.shares_cagr,
            "buyback_total_spent": bb.total_spent,
        },
        "missing_inputs": missing_inputs,
        "assumptions": assumptions,
    }


def render_quant_section(
    series: StatementSeries, market: dict[str, Any] | None = None
) -> ReportSection | None:
    """Render the quant engine results as a report section.

    Args:
        series: Aligned statement series (oldest → newest), one ticker.
        market: Optional market snapshot. Keys: ``price``, ``market_cap``,
            ``enterprise_value``, ``net_debt``, ``currency``, ``discount_rate``
            (an analyst assumption used for the implied-growth inversions;
            when absent those rows render as unavailable).

    Returns:
        A ``ReportSection`` with ``step_number=0``, or None when the series
        has zero usable periods.
    """
    market = market or {}
    if not series.periods:
        return None

    r = compute_quant_results(series, market)
    currency = market.get("currency") or series.currency or ""
    period_range: str = r["period_range"]
    t = r["trends"]
    d = r["dupont"]
    f = r["forensics"]
    v = r["valuation"]
    a = r["allocation"]

    lines: list[str] = []
    lines.append(f"*{_EDUCATION_NOTE}*")
    lines.append("")
    lines.append(f"Computed over {r['n_periods']} fiscal period(s): {period_range}.")
    lines.append("")

    lines.append("### Growth & Margins")
    lines.append("")
    lines.append("| Metric | Value | Formula | Periods |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| Revenue CAGR | {_fmt(t['revenue_cagr'], pct=True)} | (last/first)^(1/periods) − 1 | {period_range} |"
    )
    lines.append(
        f"| Diluted EPS CAGR | {_fmt(t['eps_cagr'], pct=True)} | (last/first)^(1/periods) − 1 | {period_range} |"
    )
    lines.append(
        f"| Free cash flow CAGR | {_fmt(t['fcf_cagr'], pct=True)} | (last/first)^(1/periods) − 1 | {period_range} |"
    )
    lines.append(
        f"| Latest YoY revenue growth | {_fmt(t['yoy_revenue_growth_latest'], pct=True)} "
        "| rev_t / rev_t−1 − 1 | latest |"
    )
    lines.append(
        f"| Latest gross margin | {_fmt(t['gross_margin_latest'], pct=True)} | gross_profit / revenue | latest |"
    )
    lines.append(
        f"| Latest net margin | {_fmt(t['net_margin_latest'], pct=True)} | net_income / revenue | latest |"
    )
    lines.append("")

    lines.append("### DuPont ROE Decomposition")
    lines.append("")
    dl = d["latest"]
    if dl["roe"] is not None:
        lines.append(f"Latest ROE: **{_fmt(dl['roe'], pct=True)}** = margin × turnover × leverage")
        lines.append("")
        lines.append("| Component | Value | Formula |")
        lines.append("|---|---|---|")
        lines.append(f"| Net margin | {_fmt(dl['net_margin'], pct=True)} | net_income / revenue |")
        lines.append(f"| Asset turnover | {_fmt(dl['asset_turnover'])} | revenue / avg total_assets |")
        lines.append(f"| Leverage | {_fmt(dl['leverage'])} | avg total_assets / avg total_equity |")
        attr = d["attribution"]
        first_period = d["rows"][0]["period"] if d["rows"] else "?"
        if attr["roe_change_pp"] is not None:
            lines.append("")
            lines.append(
                f"ROE change from {first_period} to {dl['period']}: "
                f"{_fmt(attr['roe_change_pp'], digits=1)}pp — "
                f"margin {_fmt(attr['margin_contribution_pp'], digits=1)}pp, "
                f"turnover {_fmt(attr['turnover_contribution_pp'], digits=1)}pp, "
                f"leverage {_fmt(attr['leverage_contribution_pp'], digits=1)}pp."
            )
    else:
        lines.append("DuPont decomposition unavailable — required inputs missing (see Missing inputs).")
    lines.append("")

    lines.append("### Forensic Screens")
    lines.append("")
    lines.append(
        "> Altman Z and Beneish M are statistical **screens, not verdicts**. "
        "A flag means 'look closer', never 'this company will fail / is fraudulent'."
    )
    lines.append("")
    if f["altman_z"] is not None and f["altman_zone"] is not None:
        lines.append(
            f"- **Altman Z-score:** {_fmt(f['altman_z'])} — zone **{f['altman_zone']}** "
            "(safe > 2.99, grey 1.81–2.99, distress < 1.81). Screen, not a verdict."
        )
    else:
        lines.append("- **Altman Z-score:** n/a")
    if f["beneish_m"] is not None:
        flag_txt = "FLAGGED (M > −1.78)" if f["beneish_flag"] else "not flagged"
        lines.append(f"- **Beneish M-score:** {_fmt(f['beneish_m'])} — {flag_txt}. Screen, not a verdict.")
    else:
        lines.append("- **Beneish M-score:** n/a")
    lines.append(
        f"- **Sloan accruals ratio:** {_fmt(f['sloan_accruals'])} — "
        "(net_income − operating_cash_flow) / total_assets"
    )
    lines.append(
        f"- **Cash conversion:** {_fmt(f['cash_conversion'], pct=True)} — "
        "operating_cash_flow / net_income"
    )
    lines.append("")

    lines.append("### Valuation Checks")
    lines.append("")
    lines.append("| Metric | Value | Formula |")
    lines.append("|---|---|---|")
    lines.append(f"| Graham number | {_fmt(v['graham_number'])} {currency} | √(22.5 × EPS × BVPS) |")
    lines.append(
        f"| Lynch fair value (PEG = 1) | {_fmt(v['lynch_fair_value'])} {currency} | EPS × EPS-growth-% |"
    )
    lines.append(
        f"| Implied explicit-stage growth | {_fmt(v['implied_explicit_stage_growth'], pct=True)} | "
        "reverse DCF bisection: constant g over 5 explicit years + Gordon terminal, solved for current EV |"
    )
    lines.append(
        f"| Implied perpetual growth | {_fmt(v['implied_perpetual_growth'], pct=True)} | "
        "Gordon algebra: g = (EV×r − FCF) / (EV + FCF) |"
    )
    lines.append("")

    lines.append("### Capital Allocation")
    lines.append("")
    if a["incremental_roic_average"] is not None:
        lines.append(f"- **Average incremental ROIC:** {_fmt(a['incremental_roic_average'], pct=True)}")
        lines.append(
            f"  - Operating tax rate (latest): {_fmt(a['operating_tax_rate_latest'], pct=True)} — "
            "t = tax_expense / (ebit − interest_expense), spec amendment A1"
        )
    else:
        lines.append("- **Incremental ROIC:** n/a — unavailable when tax/interest inputs are missing.")
    lines.append(
        f"- **Dividend:** payout on earnings {_fmt(a['dividend_payout_on_earnings'], pct=True)}, "
        f"payout on FCF {_fmt(a['dividend_payout_on_fcf'], pct=True)}, "
        f"{a['dividend_years_grown']} consecutive annual increase(s), {a['dividend_cuts']} cut(s)."
    )
    lines.append(
        f"- **Debt:** net debt {_fmt(a['debt_net_debt_latest'])} {currency}, "
        f"net debt / EBIT {_fmt(a['debt_net_debt_to_ebit'])}, "
        f"interest coverage {_fmt(a['debt_interest_coverage'])}, "
        f"debt CAGR {_fmt(a['debt_cagr'], pct=True)}."
    )
    lines.append(
        f"- **Buybacks:** shares CAGR {_fmt(a['buyback_shares_cagr'], pct=True)}, "
        f"total spent {_fmt(a['buyback_total_spent'])} {currency}."
    )
    lines.append("")

    lines.append("### Missing inputs")
    lines.append("")
    for m in r["missing_inputs"]:
        lines.append(f"- {m}")
    lines.append("")

    return ReportSection(
        step_number=_QUANT_STEP_NUMBER,
        title=QUANT_SECTION_TITLE,
        content="\n".join(lines),
        assumptions=[
            Assumption(
                label="Discount rate",
                value=x,
                source="quant section input",
                confidence="Low",
                note="Analyst assumption, not observed market data.",
            )
            for x in r["assumptions"]
        ],
        data_gaps=r["missing_inputs"],
    )
