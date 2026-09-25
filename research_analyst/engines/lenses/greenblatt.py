"""Greenblatt lens — the Magic Formula (quality + value composite).

Public-domain Joel Greenblatt methodology, original implementation:
rank by ROIC (quality) and earnings yield (value), then combine.
"""
# Module: research_analyst/engines/lenses/greenblatt.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from .base import ATTRIBUTION, LensInput, LensResult, LensSignal


def run(data: LensInput) -> LensResult:
    """Evaluate a security through the Magic Formula lens."""
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

    # --- Quality: ROIC (returns on invested capital) ---
    roic = stmt.roic if stmt else None
    if roic is None:
        missing.append("roic")
    if roic is not None:
        raw["roic"] = round(roic, 4)
        read = "favor" if roic >= 0.20 else "caution" if roic <= 0.05 else "neutral"
        signals.append(LensSignal(
            label="Return on Invested Capital", value=f"{roic:.1%}",
            read=read,
            note="Greenblatt's quality filter: high ROIC means the business earns well on its capital.",  # noqa: E501
        ))
    else:
        raw["roic"] = None

    # --- Value: earnings yield (EBIT / enterprise value proxy) ---
    earnings_yield: float | None = None
    if stmt and stmt.ebit and price:
        ev = None
        mcap = data.shares_outstanding * price if data.shares_outstanding else None
        if mcap:
            debt = float(stmt.total_debt) if stmt.total_debt else 0
            cash = float(stmt.cash_and_equivalents) if stmt.cash_and_equivalents else 0
            ev = mcap + debt - cash
            if ev > 0:
                earnings_yield = float(stmt.ebit) / ev
                raw["ev"] = round(ev, 0)
                raw["earnings_yield_ebit"] = round(earnings_yield, 4)
                read = (
                    "favor" if earnings_yield >= 0.08
                    else "caution" if earnings_yield <= 0.03
                    else "neutral"
                )
                signals.append(LensSignal(
                    label="Earnings Yield (EBIT/EV)", value=f"{earnings_yield:.1%}",
                    read=read,
                    note="Greenblatt's value filter: the earnings yield from operating profit relative to enterprise value.",  # noqa: E501
                ))
    if earnings_yield is None:
        raw["earnings_yield_ebit"] = None
        if not (stmt and stmt.ebit):
            missing.append("ebit")

    # --- Composite read ---
    if roic is not None and earnings_yield is not None:
        composite = "favor" if roic >= 0.20 and earnings_yield >= 0.08 else (
            "caution" if roic <= 0.05 or earnings_yield <= 0.03 else "neutral"
        )
        raw["magic_formula_composite"] = composite
        signals.append(LensSignal(
            label="Magic Formula Composite",
            value="High quality + value" if composite == "favor" else (
                "Low quality or expensive" if composite == "caution" else "Mixed"
            ),
            read=composite,
            note="Combines the quality and value filters; rank against the universe for the full Magic Formula.",  # noqa: E501
        ))
    elif roic is not None or earnings_yield is not None:
        raw["magic_formula_composite"] = "partial"
        signals.append(LensSignal(
            label="Magic Formula Composite", value="Partial data",
            read="neutral", note="Only one of ROIC / earnings yield was computable.",
        ))

    summary = "Magic Formula screen (ROIC quality + EBIT/EV earnings yield) applied."
    return LensResult(
        lens="greenblatt",
        name="Greenblatt — Magic Formula",
        summary=summary,
        signals=signals,
        raw_values=raw,
        missing_inputs=sorted(set(missing)),
        attribution=ATTRIBUTION.format(name="Joel Greenblatt"),
    )
