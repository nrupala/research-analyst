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

"""Server-rendered diagrams (Phase F — presentation overhaul).

Replaces client-side Mermaid with D2 (Apache-2.0, terrastruct) rendered to
static SVG on the server — zero diagram JavaScript on the page. The D2 source
is generated deterministically here; if the ``d2`` binary is absent (dev/CI)
the source renders as a readable styled block instead of failing.

Diagram types (mirroring the previous Mermaid set):
  * business model    — revenue segments -> company -> customers
  * capital allocation — FCF -> capex / buybacks / dividends
  * decision framework — factors/catalysts -> decision
"""
# Module: research_analyst/reports/diagrams.py | Version: 1.0 | Updated: 2026-08-31

from __future__ import annotations

import html
import shutil
import subprocess

from ..models import ReportVisual
from .currency import compact_money

D2_BIN = "d2"
D2_TIMEOUT = 15


# ---------------------------------------------------------------------------
# D2 source generators (deterministic, testable)
# ---------------------------------------------------------------------------


def d2_business_model(
    ticker: str,
    revenue_segments: list[str] | None = None,
    customers: list[str] | None = None,
) -> str:
    """D2 source: segments -> {ticker} -> customers (simple edges)."""
    segments = revenue_segments or ["Product sales", "Services"]
    customers = customers or ["Consumers", "Enterprises", "Government"]
    lines = [f"company: {ticker}", "direction: right"]
    for seg in segments:
        lines.append(f'"{seg}" -> company')
    for cust in customers:
        lines.append(f'company -> "{cust}"')
    return "\n".join(lines) + "\n"


def _join_nodes(items: list[str]) -> str:
    if len(items) > 1:
        return " & ".join(f'"{s}"' for s in items)
    return f'"{items[0]}"'


def d2_capital_allocation(
    ticker: str,
    capex_pct: float | None = None,
    buyback_pct: float | None = None,
    div_pct: float | None = None,
    capex_abs: float | None = None,
    buyback_abs: float | None = None,
    div_abs: float | None = None,
    currency: str | None = "USD",
) -> str:
    """D2 source: free cash flow -> capex / buybacks / dividends.

    Percentages are shares of total capital deployed (they sum to ~100%),
    not shares of FCF; absolute amounts are shown alongside when provided.
    """
    edges = [
        '"Free Cash Flow" -> "Capex"',
        '"Free Cash Flow" -> "Buybacks"',
        '"Free Cash Flow" -> "Dividends"',
    ]

    def label(name: str, pct: float | None, abs_: float | None, fallback: str) -> str:
        bits = []
        if abs_ is not None:
            bits.append(compact_money(abs_, currency))
        if pct is not None:
            bits.append(f"{pct:.0%} of deployed")
        if not bits:
            return f'"{name}": {fallback}'
        return f'"{name}": "{" · ".join(bits)}"'

    labels = [
        label("Capex", capex_pct, capex_abs, "capital expenditure"),
        label("Buybacks", buyback_pct, buyback_abs, "share repurchases"),
        label("Dividends", div_pct, div_abs, "shareholder payouts"),
    ]
    out = ['direction: right', *edges]
    out.extend(labels)
    return "\n".join(out) + "\n"


def d2_decision_framework(
    ticker: str,
    favors: list[str] | None = None,
    disfavors: list[str] | None = None,
    catalysts: list[str] | None = None,
) -> str:
    """D2 source: factors -> decision (favors / disfavors / catalysts)."""
    favors = favors or []
    disfavors = disfavors or []
    catalysts = catalysts or []
    lines = [f'decision: "{ticker} — monitoring framework"']
    for f in favors[:4]:
        lines.append(f'"favors: {f[:40]}" -> decision')
    for d in disfavors[:4]:
        lines.append(f'"disfavors: {d[:40]}" -> decision')
    for c in catalysts[:3]:
        lines.append(f'"catalyst: {c[:40]}" -> decision')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_diagram(source: str) -> str:
    """Render D2 source to a static SVG string (or a readable fallback when the
    ``d2`` binary is unavailable, e.g. dev/CI)."""
    if shutil.which(D2_BIN) is None:
        return _fallback_block(source)
    try:
        proc = subprocess.run(
            [D2_BIN, "-", "--theme", "3", "--layout", "dagre"],
            input=source.encode("utf-8"),
            capture_output=True,
            timeout=D2_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return _fallback_block(source)
    if proc.returncode != 0:
        return _fallback_block(source)
    svg = proc.stdout.decode("utf-8", errors="replace")
    if "<svg" not in svg:
        return _fallback_block(source)
    return svg.strip()


def _fallback_block(source: str) -> str:
    """Readable styled fallback (never a blank gap when d2 is missing)."""
    safe = html.escape(source)
    return f'<pre class="diagram-fallback">{safe}</pre>'


def diagram_visual(
    d2_source: str,
    title: str,
    ties_to: str,
    caption: str = "",
) -> ReportVisual:
    """Assemble a diagram into a ReportVisual (static SVG, fluid)."""
    content = render_diagram(d2_source)
    return ReportVisual(
        visual_type="svg",
        title=title,
        content=content,
        ties_to=ties_to,
        caption=caption,
    )


def _d2_esc(text: str) -> str:
    """Escape double quotes for D2 label strings."""
    return text.replace('"', "'")


def d2_catalyst_watchlist(
    ticker: str,
    near_term: list[str] | None = None,
    structural: list[str] | None = None,
) -> str:
    """D2 source: near-term vs structural catalysts -> monitoring decision."""
    near_term = near_term or []
    structural = structural or []
    lines = [
        "direction: right",
        f'watch: "{ticker} \u2014 catalyst watchlist"',
        '"near-term catalysts" -> watch',
        '"structural catalysts" -> watch',
    ]
    for c in near_term[:3]:
        lines.append(f'"{_d2_esc(c[:44])}" -> "near-term catalysts"')
    for c in structural[:3]:
        lines.append(f'"{_d2_esc(c[:44])}" -> "structural catalysts"')
    return "\n".join(lines) + "\n"
