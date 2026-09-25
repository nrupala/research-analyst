"""Damodaran lens — intrinsic value via a simplified DCF with sanity bounds.

Public-domain Aswath Damodaran methodology (original implementation). Uses a
conservative two-stage DCF over existing data: free cash flow, a growth
estimate (analyst 5y or revenue trend), and an explicit cost-of-capital
assumption (default 10%). Assumptions are stated, never hidden.
"""
# Module: research_analyst/engines/lenses/damodaran.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from .base import ATTRIBUTION, LensInput, LensResult, LensSignal, pct_change

DEFAULT_WACC = 0.10
DEFAULT_TERMINAL_GROWTH = 0.03


def run(data: LensInput) -> LensResult:
    """Simplified intrinsic-value estimate + sanity band."""
    signals: list[LensSignal] = []
    raw: dict[str, object] = {}
    missing: list[str] = []  # Issue #70: name every missing required input
    stmt = data.latest
    price = data.current_price

    if stmt is None:
        missing.append("financial_statements")
    if price is None:
        missing.append("current_price")
    if not data.shares_outstanding:
        missing.append("shares_outstanding")

    # Free cash flow base: prefer reported FCF, else operating cash flow - capex
    fcf: float | None = None
    if stmt and stmt.free_cash_flow:
        fcf = float(stmt.free_cash_flow)
    elif stmt and stmt.operating_cash_flow and stmt.capex is not None:
        fcf = float(stmt.operating_cash_flow) - float(stmt.capex)
    else:
        missing.append("free_cash_flow")
    raw["fcf"] = fcf

    # Growth estimate: analyst 5y EPS growth first, else prior revenue growth
    growth: float | None = None
    if data.analyst and getattr(data.analyst, "earnings_growth_5y", None):
        growth = data.analyst.earnings_growth_5y
    elif stmt and data.prior and stmt.revenue and data.prior.revenue:
        growth = pct_change(float(stmt.revenue), float(data.prior.revenue))
    else:
        missing.append("growth_estimate")
    raw["growth_estimate"] = growth

    wacc = float(data.raw.get("wacc", DEFAULT_WACC))
    raw["wacc_assumption"] = wacc

    shares = data.shares_outstanding
    intrinsic_per_share: float | None = None
    if fcf and growth is not None and shares and fcf > 0 and growth > 0:
        g = min(growth, 0.15)  # sanity: never model permanent growth above 15%
        # Simplified two-stage: grow at g for 5 years, then terminal growth.
        pv = 0.0
        g_stage = g
        for year in range(1, 6):
            fcf_y = fcf * ((1 + g_stage) ** year)
            pv += fcf_y / ((1 + wacc) ** year)
        terminal = fcf * ((1 + g) ** 5) * (1 + DEFAULT_TERMINAL_GROWTH) / (wacc - DEFAULT_TERMINAL_GROWTH)  # noqa: E501
        pv += terminal / ((1 + wacc) ** 5)
        intrinsic_per_share = pv / shares
        raw["intrinsic_value_per_share"] = round(intrinsic_per_share, 2)
        if price and intrinsic_per_share:
            raw["margin_of_safety"] = round(1 - price / intrinsic_per_share, 3)
            if price <= intrinsic_per_share * 0.85:
                signals.append(LensSignal(
                    label="Intrinsic Value (simplified DCF)", value=f"{intrinsic_per_share:.2f} per share",  # noqa: E501
                    read="favor",
                    note="Price is at least 15% below the model's intrinsic value — margin of safety.",  # noqa: E501
                ))
            elif price >= intrinsic_per_share * 1.25:
                signals.append(LensSignal(
                    label="Intrinsic Value (simplified DCF)", value=f"{intrinsic_per_share:.2f} per share",  # noqa: E501
                    read="caution",
                    note="Price is more than 25% above the model's intrinsic value.",
                ))
            else:
                signals.append(LensSignal(
                    label="Intrinsic Value (simplified DCF)", value=f"{intrinsic_per_share:.2f} per share",  # noqa: E501
                    read="neutral",
                    note="Price is within the model's sanity band of intrinsic value.",
                ))
            signals.append(LensSignal(
                label="Assumptions", value=f"WACC {wacc:.0%} / growth {growth:.1%}",
                read="neutral",
                note="The value moves directly with these assumptions — stress them before relying on it.",  # noqa: E501
            ))
    else:
        raw["intrinsic_value_per_share"] = None

    summary = "Simplified DCF intrinsic-value estimate with stated assumptions."
    return LensResult(
        lens="damodaran",
        name="Damodaran — Intrinsic Value",
        summary=summary,
        signals=signals,
        raw_values=raw,
        missing_inputs=sorted(set(missing)),
        attribution=ATTRIBUTION.format(name="Aswath Damodaran"),
    )
