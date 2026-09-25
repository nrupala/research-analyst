"""Graham lens — margin of safety, Graham Number, net-net value.

Public-domain Benjamin Graham methodology, original implementation.
"""
# Module: research_analyst/engines/lenses/graham.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

import math

from .base import ATTRIBUTION, LensInput, LensResult, LensSignal, bvps, ncav


def run(data: LensInput) -> LensResult:
    """Evaluate a security through the Graham margin-of-safety lens."""
    signals: list[LensSignal] = []
    raw: dict[str, object] = {}
    missing: list[str] = []  # Issue #70: name every missing required input
    stmt = data.latest
    price = data.current_price

    if stmt is None:
        missing.append("financial_statements")
    if price is None:
        missing.append("current_price")

    # --- Graham Number: sqrt(22.5 * EPS * BVPS) ---
    eps = stmt.eps_diluted if stmt else None
    book = bvps(stmt)
    if eps is None or eps <= 0:
        missing.append("eps_diluted")
    if book is None or book <= 0:
        missing.append("book_value_per_share")
    graham_number: float | None = None
    if eps and book and eps > 0 and book > 0:
        graham_number = math.sqrt(22.5 * eps * book)
        raw["graham_number"] = round(graham_number, 2)
        if price:
            raw["graham_margin_of_safety"] = round(1 - price / graham_number, 3)
            if price <= graham_number:
                signals.append(LensSignal(
                    label="Graham Number", value=f"{graham_number:.2f} vs price {price:.2f}",
                    read="favor", note="Price is at or below the Graham Number — margin of safety present.",  # noqa: E501
                ))
            else:
                signals.append(LensSignal(
                    label="Graham Number", value=f"{graham_number:.2f} vs price {price:.2f}",
                    read="caution", note="Price is above the Graham Number — limited margin of safety.",  # noqa: E501
                ))

    # --- Net-net (NCAV) ---
    n = ncav(stmt)
    if n is None and stmt is not None:
        # NCAV needs current assets, current liabilities and shares outstanding.
        if not stmt.current_assets or not stmt.current_liabilities:
            missing.append("current_assets/current_liabilities")
        if not stmt.shares_outstanding:
            missing.append("shares_outstanding")
    if n is not None and price:
        raw["ncav_per_share"] = round(n, 2)
        if price < n:
            signals.append(LensSignal(
                label="Net-Net Value (NCAV)", value=f"{n:.2f} per share",
                read="favor", note="Price is below net current asset value — deep-value territory.",
            ))
        else:
            signals.append(LensSignal(
                label="Net-Net Value (NCAV)", value=f"{n:.2f} per share",
                read="neutral", note="Price is above net current asset value (rare today for liquid names).",  # noqa: E501
            ))

    # --- Earnings / asset sanity ---
    if eps and eps > 0 and price:
        raw["earnings_yield"] = round(eps / price, 4)
        signals.append(LensSignal(
            label="Earnings Yield", value=f"{eps / price:.1%}",
            read="neutral",
            note="Earnings per $1 of price; Graham preferred a generous yield as the first test.",
        ))

    if not signals:
        summary = "Insufficient data to apply the Graham lens (need EPS, book value, and a price)."
    else:
        summary = "Graham-style margin-of-safety screen applied to available fundamentals."

    return LensResult(
        lens="graham",
        name="Graham — Margin of Safety",
        summary=summary,
        signals=signals,
        raw_values=raw,
        missing_inputs=sorted(set(missing)),
        attribution=ATTRIBUTION.format(name="Benjamin Graham"),
    )
