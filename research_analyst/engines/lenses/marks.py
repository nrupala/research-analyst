# Copyright (C) 2026 2351485 ALBERTA INC.
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

"""Marks lens — cycle positioning and second-level thinking.

Public-domain Howard Marks principles (original implementation). Reads
valuation vs a stated long-term band and frames second-level questions —
positioning, not prediction.
"""
# Module: research_analyst/engines/lenses/marks.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from .base import ATTRIBUTION, LensInput, LensResult, LensSignal

# Stated educational band for cycle positioning (clearly an assumption):
# typical long-run P/E range for the broad market is used as the reference.
BAND_LOW = 12.0
BAND_HIGH = 22.0


def run(data: LensInput) -> LensResult:
    """Cycle-positioning read over the current multiple vs a stated band."""
    signals: list[LensSignal] = []
    raw: dict[str, object] = {}
    missing: list[str] = []  # Issue #70: name every missing required input
    stmt = data.latest
    price = data.current_price

    if stmt is None:
        missing.append("financial_statements")
    if price is None:
        missing.append("current_price")

    pe: float | None = None
    if stmt and stmt.eps_diluted and stmt.eps_diluted > 0 and price:
        pe = price / stmt.eps_diluted
        raw["pe_ttm"] = round(pe, 2)
    else:
        if not (stmt and stmt.eps_diluted and stmt.eps_diluted > 0):
            missing.append("eps_diluted")

    if pe is not None:
        # position within the band, 0=cheapest .. 1=dearest
        position = max(0.0, min(1.0, (pe - BAND_LOW) / (BAND_HIGH - BAND_LOW)))
        raw["cycle_position"] = round(position, 3)
        if position <= 0.35:
            read = "favor"
            note = "Multiple sits in the lower part of the long-run band — cycle positioning is less crowded."  # noqa: E501
        elif position >= 0.7:
            read = "caution"
            note = "Multiple sits in the upper part of the long-run band — the easy money may be made."  # noqa: E501
        else:
            read = "neutral"
            note = "Multiple sits mid-band — average positioning, pick your spots."
        signals.append(LensSignal(
            label="Cycle Position (P/E vs band)", value=f"{pe:.1f}x ({position:.0%} of band)",
            read=read, note=note,
        ))

    # Second-level thinking prompts — the Marks signature
    signals.append(LensSignal(
        label="Second-Level Question", value="What does the market already believe?",
        read="neutral",
        note="First-level thinking asks 'is it good?'; second-level asks 'is it good AND everyone else thinks it's good?'",  # noqa: E501
    ))
    signals.append(LensSignal(
        label="Second-Level Question", value="Where are we in the cycle?",
        read="neutral",
        note="Cycles look like never-ending trends at their extremes; positioning matters more than prediction.",  # noqa: E501
    ))

    summary = "Cycle-positioning and second-level-thinking framing applied."
    return LensResult(
        lens="marks",
        name="Marks — Cycle & Second-Level Thinking",
        summary=summary,
        signals=signals,
        raw_values=raw,
        missing_inputs=sorted(set(missing)),
        attribution=ATTRIBUTION.format(name="Howard Marks"),
    )
