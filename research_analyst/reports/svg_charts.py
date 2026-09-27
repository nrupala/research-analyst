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

"""Server-rendered SVG charts (Phase F — presentation overhaul).

Replaces client-side Plotly rendering with static SVG embedded in the report
HTML. Zero chart JavaScript on the page -> no resize observers, no layout
thrash, instant render, perfect print. Hover tooltips come free via native
SVG <title> elements.

Theme (institutional, JPM-like, entirely original): muted navy/steel palette,
light grid, no chart junk, tight layout. Every chart scales fluidly to the
container via viewBox (width=100%).
"""
# Module: research_analyst/reports/svg_charts.py | Version: 1.0 | Updated: 2026-08-31

from __future__ import annotations

import io
import re
from typing import Any

# MPLCONFIGDIR is already resolved by research_analyst/__init__.py, which runs
# before this module and before matplotlib resolves its config dir.
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..models import ReportVisual  # noqa: E402
from .currency import currency_symbol  # noqa: E402

# ---------------------------------------------------------------------------
# Institutional theme
# ---------------------------------------------------------------------------

C = {
    "navy": "#1b3a5c",      # primary / revenue / base case
    "steel": "#5b7a99",     # secondary series
    "green": "#3a7d44",     # dividends / bull case / positive
    "amber": "#c98a2d",     # operating margin / medium risk
    "red": "#b23a3a",       # bear case / critical risk
    "violet": "#6d5a9e",    # net margin / variant series
    "slate": "#7a8b99",     # neutral
    "grid": "#e8edf2",
    "text": "#1f2937",
    "muted": "#6b7280",
}

FONT = "DejaVu Sans"
FIG_WIDTH, FIG_HEIGHT = 9.6, 5.4
DPI = 100


def _new_ax(fig: Any) -> Any:
    ax = fig.add_subplot(111)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#d0d7de")
    ax.grid(True, axis="y", color=C["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=C["muted"], labelsize=10)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _p: _int(v)))
    return ax


def _int(v: float) -> str:
    if abs(v) >= 1e9:
        return f"{v/1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"{v/1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"{v/1e3:.0f}K"
    if v == int(v):
        return str(int(v))
    return f"{v:.1f}"


def _title(fig: Any, text: str) -> None:
    fig.suptitle(text, fontsize=13, fontweight="bold", color=C["navy"], y=0.99)


def _to_svg(fig: Any) -> str:
    """Render to SVG and make it fluid (width=100%, viewBox preserves ratio)."""
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", transparent=False,
                facecolor="white")
    plt.close(fig)
    svg = buf.getvalue()
    # matplotlib root <svg> has width/height in pt; swap to fluid 100% width.
    svg = re.sub(
        r'<svg[^>]*width="[^"]*"[^>]*height="[^"]*"[^>]*viewBox',
        '<svg xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto" viewBox',
        svg,
        count=1,
    )
    # Drop matplotlib's XML declaration + DOCTYPE so the div embed is clean.
    svg = re.sub(r'<\?xml[^>]*\?>\s*', "", svg, count=1)
    svg = re.sub(r'<!DOCTYPE[^>]*>\s*', "", svg, count=1)
    return svg.strip()


def _currency(currency: str | None) -> str:
    return currency_symbol(currency)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def svg_financial_trends(
    financials: list[Any],
    ticker: str,
    currency: str | None = None,
) -> ReportVisual | None:
    """Revenue bars (left) + margin lines (right, %) — the financial trajectory."""
    if len(financials) < 2:
        return None
    sym = _currency(currency)
    from datetime import date as _date

    sorted_fin = sorted(financials, key=lambda f: f.period_end_date or _date.min)
    periods = [f.period for f in sorted_fin]
    revenues = [float(f.revenue) / 1e9 if f.revenue else 0.0 for f in sorted_fin]
    margins: dict[str, list[float]] = {
        "Gross": [f.gross_margin * 100 if f.gross_margin else np.nan for f in sorted_fin],
        "Operating": [
            f.operating_margin * 100 if f.operating_margin else np.nan
            for f in sorted_fin
        ],
        "Net": [f.net_margin * 100 if f.net_margin else np.nan for f in sorted_fin],
    }

    fig, ax = _fig()
    ax.bar(periods, revenues, color=C["navy"], alpha=0.85, width=0.55,
           label=f"Revenue ({sym}B)")
    ax.set_ylabel(f"Revenue ({sym}B)", color=C["muted"], fontsize=10)
    ax.set_ylim(0, max(revenues) * 1.25 or 1)

    ax2 = ax.twinx()
    series = (
        ("Gross", C["green"], "-"),
        ("Operating", C["amber"], "-"),
        ("Net", C["violet"], "dotted"),
    )
    for name, color, ls in series:
        vals = margins[name]
        if not np.isnan(vals).all():
            ax2.plot(periods, vals, label=f"{name} margin %", color=color,
                     linewidth=1.8, marker="o", markersize=3, linestyle=ls)
    ax2.set_ylabel("Margin %", color=C["muted"], fontsize=10)
    ax2.grid(False)
    ax2.tick_params(colors=C["muted"], labelsize=10)

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9, frameon=False)

    _title(fig, f"{ticker} — Revenue & Margin Trends")
    code = (currency or "USD").strip().upper()
    return ReportVisual(
        visual_type="svg",
        title=f"{ticker} — Revenue & Margin Trends",
        content=_to_svg(fig),
        ties_to="Financial trajectory assessment (Step 2)",
        caption=f"Revenue in billions {code}. Margins as percentage of revenue.",
        interactive={
            "type": "financial_trends",
            "ticker": ticker,
            "currency": code,
            "periods": periods,
            "revenue_b": revenues,
            "margins_pct": {k: [None if v != v else round(v, 2) for v in vals] for k, vals in margins.items()},
        },
    )


def svg_scenario_valuation(
    valuation: Any,
    currency: str | None = None,
) -> ReportVisual:
    """Scenario valuation — horizontal range bars (bull/base/bear)."""
    sym = _currency(currency)
    lows, highs, labels, colors = [], [], [], []
    color_map = {"Bull Case": C["green"], "Base Case": C["navy"], "Bear Case": C["red"]}
    for s in valuation.scenarios:
        labels.append(s.label)
        lows.append(s.implied_price_low)
        highs.append(s.implied_price_high)
        colors.append(color_map.get(s.label, C["slate"]))
    widths = [h - lo for h, lo in zip(highs, lows)]

    fig, ax = _fig()
    ax.barh(labels, widths, left=lows, color=colors, alpha=0.9, height=0.5)
    for i, (lo, hi) in enumerate(zip(lows, highs)):
        ax.text(lo + (hi - lo) / 2, i, f"{sym}{lo:,.0f} \u2013 {sym}{hi:,.0f}",
                ha="center", va="center", color="white", fontsize=9.5, fontweight="bold")
    ax.set_xlabel(f"Price ({sym})", color=C["muted"], fontsize=10)
    ax.grid(True, axis="x", color=C["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    _title(fig, "Scenario-Based Valuation Range")
    return ReportVisual(
        visual_type="svg",
        title="Scenario-Based Valuation Range",
        content=_to_svg(fig),
        ties_to="Scenario-based valuation assessment (Step 6)",
        caption="Assumption-driven illustrations; not a price target.",
        interactive={
            "type": "scenario",
            "currency": (currency or "USD"),
            "scenarios": [
                {"label": s.label, "low": s.implied_price_low, "high": s.implied_price_high}
                for s in valuation.scenarios
            ],
        },
    )


def svg_peer_comparison(
    target_ticker: str,
    peers: list[Any],
    currency: str | None = None,
) -> ReportVisual:
    """Grouped bars for Gross/Operating margin + ROE across peers."""
    tickers = [target_ticker] + [p.ticker for p in peers]
    gm = [np.nan] + [p.gross_margin * 100 if p.gross_margin else np.nan for p in peers]
    om = [np.nan] + [p.operating_margin * 100 if p.operating_margin else np.nan for p in peers]
    roe = [np.nan] + [p.roe * 100 if p.roe else np.nan for p in peers]

    fig, ax = _fig()
    x = range(len(tickers))
    width = 0.25
    series = (
        (gm, C["green"], "Gross margin %"),
        (om, C["navy"], "Operating margin %"),
        (roe, C["violet"], "ROE %"),
    )
    for vals, color, label in series:
        ax.bar([i - width for i in x], vals, width, color=color, alpha=0.85, label=label)
    ax.set_xticks(list(x))
    ax.set_xticklabels(tickers, fontsize=9)
    ax.set_ylabel("%", color=C["muted"], fontsize=10)
    ax.set_ylim(0, max([v for v in gm + om + roe if v == v]) * 1.25 or 1)
    ax.legend(loc="upper right", fontsize=9, frameon=False)

    _title(fig, "Peer Comparison — Key Margins & Returns")
    return ReportVisual(
        visual_type="svg",
        title="Peer Comparison — Key Margins & Returns",
        content=_to_svg(fig),
        ties_to="Competitive position assessment (Step 3)",
        caption="Gross/operating margin and ROE versus peers.",
        interactive={
            "type": "peers",
            "tickers": tickers,
            "gross_margin_pct": [None if v != v else round(v, 2) for v in gm],
            "op_margin_pct": [None if v != v else round(v, 2) for v in om],
            "roe_pct": [None if v != v else round(v, 2) for v in roe],
        },
    )


def svg_risk_heatmap(matrix: Any) -> ReportVisual:
    """Risk scatter — probability x impact, size/color by severity."""
    fig, ax = _fig()
    for risk in matrix.risks:
        prob = _prob_value(risk.probability)
        imp = _impact_value(risk.impact)
        severity = prob * imp
        color = C["red"] if severity >= 8 else C["amber"] if severity >= 4 else C["green"]
        ax.scatter(prob, imp, s=180 + severity * 55, color=color, alpha=0.72,
                   edgecolors="white", linewidths=1, zorder=3)
        ax.annotate(risk.title[:22], (prob, imp), xytext=(7, 7),
                    textcoords="offset points", fontsize=8.5, color=C["text"])
    ax.set_xlim(0.5, 3.5)
    ax.set_ylim(0.5, 4.5)
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(["Low", "Medium", "High"])
    ax.set_yticks([1, 2, 3, 4])
    ax.set_yticklabels(["Low", "Medium", "High", "Critical"])
    ax.set_xlabel("Probability", color=C["muted"], fontsize=10)
    ax.set_ylabel("Impact", color=C["muted"], fontsize=10)
    ax.grid(True, color=C["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.axvline(2.0, color="#d0d7de", linewidth=0.7)
    ax.axhline(2.5, color="#d0d7de", linewidth=0.7)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    _title(fig, "Risk Matrix — Probability vs Impact")
    return ReportVisual(
        visual_type="svg",
        title="Risk Matrix — Probability vs Impact",
        content=_to_svg(fig),
        ties_to="Risk assessment (Step 5)",
        caption="Bubble size and color encode severity (probability x impact).",
        interactive={
            "type": "risks",
            "risks": [
                {
                    "title": r.title[:22],
                    "probability": _prob_value(r.probability),
                    "impact": _impact_value(r.impact),
                }
                for r in matrix.risks
            ],
        },
    )


def _prob_value(p: str) -> float:
    if not p:
        return 1.0
    if "High" in p or "high" in p:
        return 3.0
    if "Med" in p or "Medium" in p:
        return 2.0
    return 1.0


def _impact_value(i: str) -> float:
    if not i:
        return 1.0
    if "Critical" in i:
        return 4.0
    if "High" in i:
        return 3.0
    if "Medium" in i or "Med" in i:
        return 2.0
    return 1.0


def svg_dividend_history(div: Any, currency: str | None = None) -> ReportVisual:
    """Dividend per share by year — green bars."""
    sym = _currency(currency)
    annual = getattr(div, "annual_dividends", {}) or {}
    years = sorted(annual.keys(), key=lambda y: int(y))[-10:]
    values = [round(annual[y], 4) for y in years]
    if not years:
        raise ValueError("no dividend history")

    fig, ax = _fig()
    ax.bar(years, values, color=C["green"], alpha=0.85, width=0.55)
    ax.set_xlabel("Year", color=C["muted"], fontsize=10)
    ax.set_ylabel(f"DPS ({sym})", color=C["muted"], fontsize=10)
    ax.set_ylim(0, max(values) * 1.3)
    ax.tick_params(axis="x", rotation=0, labelsize=9)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    _title(fig, f"{div.ticker} — Dividend Per Share by Year")
    return ReportVisual(
        visual_type="svg",
        title=f"{div.ticker} — Dividend Per Share by Year",
        content=_to_svg(fig),
        ties_to="Dividend growth & consistency",
        caption=(
            "Annual dividends per share (calendar-year sums). "
            "The most recent year may be partial."
        ),
        interactive={
            "type": "dividends",
            "ticker": div.ticker,
            "years": years,
            "dps": values,
        },
    )


def _fig() -> tuple[Any, Any]:
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT), dpi=DPI)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    return fig, ax


def svg_thesis_balance(
    ticker: str, n_favor: int, n_disfavor: int, tilt: str
) -> ReportVisual:
    """Diverging evidence bar: thesis-favoring vs disfavoring factor counts.

    Bar length is a *count*, not a weight — one strong factor can outweigh
    several weak ones. Compact figure (not the default 9.6x5.4) because a
    single diverging bar needs little vertical space.
    """
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 2.8), dpi=DPI)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    span = max(n_favor, n_disfavor, 1)
    ax.barh([0], [n_favor], height=0.42, color=C["green"], alpha=0.88, zorder=3)
    ax.barh([0], [-n_disfavor], height=0.42, color=C["red"], alpha=0.88, zorder=3)
    ax.set_xlim(-span - 1, span + 1)
    ax.set_ylim(-0.8, 0.8)
    ax.axvline(0, color="#9aa7b4", linewidth=1.2, zorder=4)
    ax.set_yticks([])
    ax.set_xticks([])
    for spine in ("top", "right", "left", "bottom"):
        ax.spines[spine].set_visible(False)
    if n_favor:
        ax.text(n_favor / 2, 0, f"{n_favor} favor", ha="center", va="center",
                fontsize=11, fontweight="bold", color="white", zorder=5)
    if n_disfavor:
        ax.text(-n_disfavor / 2, 0, f"{n_disfavor} disfavor", ha="center",
                va="center", fontsize=11, fontweight="bold", color="white",
                zorder=5)
    ax.text(0, -0.62, f"Evidence balance tilts {tilt}", ha="center", va="top",
            fontsize=10, style="italic", color=C["muted"])
    _title(fig, f"{ticker} \u2014 Thesis Balance")
    return ReportVisual(
        visual_type="svg",
        title=f"{ticker} \u2014 Thesis Balance",
        content=_to_svg(fig),
        ties_to="Investment thesis evidence balance (Step 7)",
        caption=(
            "Count of favoring vs disfavoring factors. Length is a count, not a "
            "weight \u2014 one strong factor can outweigh several weak ones."
        ),
        interactive={
            "type": "thesis_balance",
            "favor": n_favor,
            "disfavor": n_disfavor,
            "tilt": tilt,
        },
    )


def svg_unit_economics(
    ticker: str, margins: dict[str, float | None]
) -> ReportVisual | None:
    """Horizontal margin bars — the company's unit economics at a glance.

    ``margins`` maps a label to a decimal margin (0.42 = 42%). Entries that
    are None are skipped; returns None when nothing is available.
    """
    items = [(label, value) for label, value in margins.items()
             if value is not None]
    if not items:
        return None
    labels = [label for label, _ in items]
    values = [value * 100 for _, value in items]
    fig, ax = plt.subplots(figsize=(FIG_WIDTH, 1.6 + 0.9 * len(items)), dpi=DPI)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    bars = ax.barh(labels, values, height=0.5, color=C["steel"], alpha=0.9,
                   zorder=3)
    ax.set_xlabel("Margin (%)", color=C["muted"], fontsize=10)
    ax.set_xlim(min(0, min(values) - 5), 100)
    ax.grid(True, axis="x", color=C["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=C["muted"], labelsize=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#d0d7de")
    for bar, value in zip(bars, values):
        ax.text(
            value + (1 if value >= 0 else -1),
            bar.get_y() + bar.get_height() / 2,
            f"{value:.1f}%",
            ha="left" if value >= 0 else "right",
            va="center", fontsize=10, color=C["text"],
        )
    _title(fig, f"{ticker} \u2014 Unit Economics (latest margins)")
    return ReportVisual(
        visual_type="svg",
        title=f"{ticker} \u2014 Unit Economics",
        content=_to_svg(fig),
        ties_to="Business model economics (Step 7)",
        caption=(
            "Latest reported margins \u2014 what the company keeps from each "
            "dollar of revenue."
        ),
        interactive={
            "type": "unit_economics",
            "margins": {label: value for label, value in items},
        },
    )
