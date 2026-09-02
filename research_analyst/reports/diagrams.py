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
) -> str:
    """D2 source: free cash flow -> capex / buybacks / dividends."""
    edges = [
        '"Free Cash Flow" -> "Capex"',
        '"Free Cash Flow" -> "Buybacks"',
        '"Free Cash Flow" -> "Dividends"',
    ]
    labels = []
    if capex_pct is not None:
        labels.append(f'"Capex": {capex_pct:.0%} of FCF')
    if buyback_pct is not None:
        labels.append(f'"Buybacks": {buyback_pct:.0%} of FCF')
    if div_pct is not None:
        labels.append(f'"Dividends": {div_pct:.0%} of FCF')
    if not labels:
        labels = [
            '"Capex": capital expenditure',
            '"Buybacks": share repurchases',
            '"Dividends": shareholder payouts',
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
