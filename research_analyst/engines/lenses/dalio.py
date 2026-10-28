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

"""Dalio lens — macro regime framing and allocation levers (educational).

Public-domain Ray Dalio-style risk-parity framing (original implementation).
Reads whatever macro-proxy inputs are available (yield vs a stated treasury
proxy, market correlation proxy via beta) and frames regime-aware allocation
levers as educational questions — never as directives.
"""
# Module: research_analyst/engines/lenses/dalio.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from .base import ATTRIBUTION, LensInput, LensResult, LensSignal

# Stated educational assumption: a generic 10Y treasury proxy for the
# risk-free rate when no live rate is provided (clearly labeled as such).
TREASURY_PROXY = 0.042


def run(data: LensInput) -> LensResult:
    """Regime framing over available proxies (yield spread, beta)."""
    signals: list[LensSignal] = []
    raw: dict[str, object] = {}
    missing: list[str] = []  # Issue #70: name every missing required input

    yield_v = data.raw.get("dividend_yield")
    if yield_v is None and data.fundamental is not None:
        yield_v = getattr(data.fundamental, "current_yield", None)
    raw["dividend_yield"] = yield_v
    if yield_v is None:
        missing.append("dividend_yield")

    beta = data.raw.get("beta")
    raw["beta"] = beta
    if beta is None:
        missing.append("beta")

    # --- Yield vs treasury proxy: the income/macro lever ---
    if yield_v is not None:
        spread = yield_v - TREASURY_PROXY
        raw["yield_vs_treasury_proxy"] = round(spread, 4)
        if spread > 0.02:
            signals.append(LensSignal(
                label="Income vs Rate Regime", value=f"{yield_v:.1%} vs {TREASURY_PROXY:.1%} proxy",
                read="favor",
                note="Income yield meaningfully exceeds the treasury proxy — attractive in a stable-rate regime.",  # noqa: E501
            ))
        elif spread < -0.01:
            signals.append(LensSignal(
                label="Income vs Rate Regime", value=f"{yield_v:.1%} vs {TREASURY_PROXY:.1%} proxy",
                read="caution",
                note="Income yield trails the treasury proxy — competition from 'risk-free' income.",  # noqa: E501
            ))
        else:
            signals.append(LensSignal(
                label="Income vs Rate Regime", value=f"{yield_v:.1%} vs {TREASURY_PROXY:.1%} proxy",
                read="neutral",
                note="Income yield roughly matches the treasury proxy.",
            ))
        signals.append(LensSignal(
            label="Regime Question", value="Rates rising or falling?",
            read="neutral",
            note="Dalio-style framing: the same yield is worth more when rates are falling than when they rise.",  # noqa: E501
        ))

    # --- Beta: the risk/parity lever ---
    if beta is not None:
        raw["beta"] = beta
        if beta < 0.8:
            signals.append(LensSignal(
                label="Market Sensitivity (Beta)", value=f"{beta:.2f}",
                read="neutral",
                note="Lower beta — less market co-movement, a diversifying sleeve in a risk-parity frame.",  # noqa: E501
            ))
        elif beta > 1.4:
            signals.append(LensSignal(
                label="Market Sensitivity (Beta)", value=f"{beta:.2f}",
                read="caution",
                note="High beta amplifies regime swings; size the position accordingly.",
            ))
        else:
            signals.append(LensSignal(
                label="Market Sensitivity (Beta)", value=f"{beta:.2f}",
                read="neutral",
                note="Beta near the market — treat as a core, not a diversifier.",
            ))

    # --- Allocation-lever framing (educational, never prescriptive) ---
    signals.append(LensSignal(
        label="Allocation Lever", value="Correlation & diversification",
        read="neutral",
        note="Dalio-style risk parity asks how this asset behaves when everything else moves — check correlation, not just returns.",  # noqa: E501
    ))

    summary = "Macro-regime and allocation-lever framing applied to available proxies."
    return LensResult(
        lens="dalio",
        name="Dalio — Regime & Allocation Framing",
        summary=summary,
        signals=signals,
        raw_values=raw,
        missing_inputs=sorted(set(missing)),
        attribution=ATTRIBUTION.format(name="Ray Dalio"),
    )
