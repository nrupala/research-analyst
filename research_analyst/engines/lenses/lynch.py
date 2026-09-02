"""Lynch lens — PEG, GARP classification.

Public-domain Peter Lynch methodology, original implementation:
classify the company into a growth archetype and check PEG.
"""
# Module: research_analyst/engines/lenses/lynch.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from .base import ATTRIBUTION, LensInput, LensResult, LensSignal, pct_change


def _archetype(rev_growth: float | None, eps_growth: float | None, dividend: float | None) -> str:
    """Lynch-style growth archetype classification (original mapping)."""
    if rev_growth is None or eps_growth is None:
        return "Unclassified (insufficient growth data)"
    if eps_growth > 0.25 and dividend is None:
        return "Fast Grower"
    if eps_growth > 0.25 and dividend is not None:
        return "Stalwart or Asset Play"
    if 0.06 <= eps_growth <= 0.25:
        return "Stalwart"
    if -0.06 < eps_growth < 0.06:
        return "Slow Grower / Cyclical (flat)"
    return "Turnaround / Cyclical"


def run(data: LensInput) -> LensResult:
    """Evaluate a security through the Lynch PEG / GARP lens."""
    signals: list[LensSignal] = []
    raw: dict[str, object] = {}
    stmt = data.latest
    prior = data.prior
    price = data.current_price

    eps = stmt.eps_diluted if stmt else None
    eps_prior = prior.eps_diluted if prior else None
    rev = float(stmt.revenue) if stmt and stmt.revenue else None
    rev_prior = float(prior.revenue) if prior and prior.revenue else None

    eps_growth = pct_change(eps, eps_prior)
    rev_growth = pct_change(rev, rev_prior)

    raw["eps_growth_yoy"] = eps_growth
    raw["revenue_growth_yoy"] = rev_growth

    archetype = _archetype(rev_growth, eps_growth, stmt.dividends_paid if stmt else None)
    raw["archetype"] = archetype
    signals.append(LensSignal(
        label="Growth Archetype", value=archetype,
        read="neutral",
        note="Lynch classified companies before pricing them: the archetype determines the fair-PEG expectation.",  # noqa: E501
    ))

    # --- PEG ---
    pe = None
    if eps and eps > 0 and price:
        pe = price / eps
        raw["pe_ttm"] = round(pe, 2)
    peg: float | None = None
    if pe is not None and eps_growth is not None:
        g = eps_growth * 100
        if g > 0:
            peg = pe / g
            raw["peg"] = round(peg, 2)
            read = "favor" if peg < 1.0 else "caution" if peg > 2.0 else "neutral"
            signals.append(LensSignal(
                label="PEG Ratio", value=f"{peg:.2f}",
                read=read,
                note="PEG near or below 1 is Lynch's 'fair price for growth'; well above 2 asks for aggressive growth to justify.",  # noqa: E501
            ))
        else:
            signals.append(LensSignal(
                label="PEG Ratio", value="n/a (declining EPS)",
                read="caution", note="Earnings are shrinking — PEG is not meaningful for a declining base.",  # noqa: E501
            ))

    summary = "Lynch-style growth-classification and PEG screen applied."
    return LensResult(
        lens="lynch",
        name="Lynch — Growth at a Reasonable Price",
        summary=summary,
        signals=signals,
        raw_values=raw,
        attribution=ATTRIBUTION.format(name="Peter Lynch"),
    )
