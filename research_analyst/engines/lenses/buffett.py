"""Buffett lens — owner earnings and economic-moat proxies.

Public-domain Warren Buffett principles (original implementation). Owner
earnings = operating cash flow minus maintenance capex (approximated by total
capex here, stated). Moat proxies: margin persistence, ROE level, leverage.
"""
# Module: research_analyst/engines/lenses/buffett.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from .base import ATTRIBUTION, LensInput, LensResult, LensSignal, pct_change


def run(data: LensInput) -> LensResult:
    """Evaluate moat/quality through Buffett-style owner-earnings proxies."""
    signals: list[LensSignal] = []
    raw: dict[str, object] = {}
    missing: list[str] = []  # Issue #70: name every missing required input
    stmt = data.latest
    prior = data.prior

    if stmt is None:
        missing.append("financial_statements")

    # --- Owner earnings (FCF-based proxy) ---
    owner_earnings: float | None = None
    if stmt and stmt.operating_cash_flow and stmt.capex is not None:
        owner_earnings = float(stmt.operating_cash_flow) - float(stmt.capex)
        raw["owner_earnings"] = round(owner_earnings, 0)
        if owner_earnings > 0:
            signals.append(LensSignal(
                label="Owner Earnings", value=f"{owner_earnings / 1e9:.1f}B",
                read="favor",
                note="The business generates cash beyond its capital spending — the core Buffett test.",  # noqa: E501
            ))
        else:
            signals.append(LensSignal(
                label="Owner Earnings", value=f"{owner_earnings / 1e9:.1f}B",
                read="caution",
                note="Cash flow does not cover capex — growth may be consuming capital.",
            ))
    elif stmt is not None:
        if not stmt.operating_cash_flow:
            missing.append("operating_cash_flow")
        if stmt.capex is None:
            missing.append("capex")

    # --- Moat proxy 1: gross margin persistence ---
    gm = stmt.gross_margin if stmt else None
    gm_prior = prior.gross_margin if prior else None
    if gm is None:
        missing.append("gross_margin")
    if gm is not None:
        raw["gross_margin"] = gm
        stable = gm_prior is None or abs(gm - gm_prior) < 0.03
        read = "favor" if gm >= 0.45 and stable else "caution" if gm <= 0.15 else "neutral"
        signals.append(LensSignal(
            label="Gross Margin Persistence", value=f"{gm:.1%}",
            read=read,
            note="High and stable gross margins are a common moat signal (pricing power).",
        ))

    # --- Moat proxy 2: ROE with leverage context ---
    roe = stmt.roe if stmt else None
    d2e = stmt.debt_to_equity if stmt else None
    if roe is None:
        missing.append("roe")
    if d2e is None:
        missing.append("debt_to_equity")
    if roe is not None:
        raw["roe"] = roe
        read = "favor" if roe >= 0.18 and (d2e is None or d2e < 0.8) else (
            "caution" if roe < 0.08 else "neutral"
        )
        note = "High ROE with moderate leverage suggests real returns on equity."
        if d2e is not None and d2e >= 0.8:
            note = "High ROE but leverage is elevated — check how much is borrowed."
        signals.append(LensSignal(label="Return on Equity", value=f"{roe:.1%}", read=read, note=note))  # noqa: E501

    # --- Moat proxy 3: FCF trend ---
    if stmt and stmt.free_cash_flow and prior and prior.free_cash_flow:
        fcf_growth = pct_change(float(stmt.free_cash_flow), float(prior.free_cash_flow))
        raw["fcf_growth_yoy"] = fcf_growth
        if fcf_growth is not None and fcf_growth > 0:
            signals.append(LensSignal(
                label="Free Cash Flow Trend", value=f"{fcf_growth:+.1%} YoY",
                read="favor" if fcf_growth > 0.05 else "neutral",
                note="Free cash flow is compounding — a durable-earnings signal.",
            ))
    elif stmt is not None:
        if not stmt.free_cash_flow:
            missing.append("free_cash_flow")
        if prior is None or not prior.free_cash_flow:
            missing.append("prior_free_cash_flow")

    summary = "Buffett-style owner-earnings and moat-proxy screen applied."
    return LensResult(
        lens="buffett",
        name="Buffett — Owner Earnings & Moat",
        summary=summary,
        signals=signals,
        raw_values=raw,
        missing_inputs=sorted(set(missing)),
        attribution=ATTRIBUTION.format(name="Warren Buffett"),
    )
