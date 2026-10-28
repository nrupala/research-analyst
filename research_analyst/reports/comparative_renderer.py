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

"""Comparative report renderer — Markdown + self-contained HTML (v0.2.0).

Renders a :class:`~research_analyst.comparative.ComparativeReport` into:
  * ``render_markdown`` — a Markdown document (scorecard + one table per dimension)
  * ``render_html``     — a fully self-contained HTML document (inline <style>,
    no external assets, opens offline), mirroring the v0.1.2 export conventions:
    a report footer ("Report prepared on https://ra.devinfo.dev" + date) and a
    Buy Me a Coffee link.

Both formats:
  * show a top SCORECARD (normalized 0-100 per metric, plus an overall roll-up),
  * show one side-by-side table per dimension with raw values, rank, and a
    winner marker,
  * carry the disclaimer and the compliance line on every output, and
  * frame everything as "here's how they rank and what would have to be true" —
    never buy / sell / hold or advice language.

This module is imported directly where needed (server, tests); it is deliberately
NOT re-exported from ``reports/__init__`` to avoid an import cycle with
``comparative`` (which imports the orchestrator, which imports ``reports``).
"""
# Module: research_analyst/reports/comparative_renderer.py | Version: 0.2.0 | Updated: 2026-07-18

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from ..entitlements import WhiteLabelProfile
from .currency import currency_symbol

if TYPE_CHECKING:  # avoid a runtime import cycle
    from ..comparative import ComparativeReport, MetricComparison

_PREPARED_ON_URL = "https://ra.devinfo.dev"
_BMAC_URL = "https://www.buymeacoffee.com/nrupalakolt"
_HOW_TO_READ = (
    "How to read this: the tool ranks and compares the numbers each ticker already "
    "produced in its own single-ticker report. It shows how they stack up on each "
    "metric and what would have to be true for the ranking to change — it does not "
    "tell you what to buy, sell, or hold."
)


# ---------------------------------------------------------------------------
# Value formatting
# ---------------------------------------------------------------------------


def _fmt_value(value: float | None, unit: str, currency: str | None = None) -> str:
    """Format a raw metric value for display, given its unit.

    ``currency`` (ISO 4217) selects the money symbol for the ``price`` unit;
    ``None`` / ``"USD"`` resolve to ``$`` so US output stays byte-identical.
    """
    if value is None:
        return "N/A"
    if unit == "pct":
        return f"{value * 100:.1f}%"
    if unit == "price":
        return f"{currency_symbol(currency)}{value:,.2f}"
    if unit == "score":
        return f"{value:.0f}"
    if unit == "ratio":
        return f"{value:.1f}x"
    if unit == "num":
        return f"{value:.1f}"
    return f"{value}"


def _metric_label(metric: MetricComparison) -> str:
    """Metric label annotated with orientation when it is ranked."""
    if metric.rankable and not metric.higher_is_better:
        return f"{metric.label} (lower is better)"
    return metric.label


def _rankable_metrics(report: ComparativeReport) -> list[MetricComparison]:
    return [m for dim in report.dimensions for m in dim.metrics if m.rankable and m.available]


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def render_markdown(report: ComparativeReport) -> str:
    """Render the comparative report as Markdown."""
    tickers = report.tickers
    out: list[str] = []

    heading = " vs ".join(tickers) if tickers else "(no valid tickers)"
    out.append(f"# Comparative Research Report — {heading}\n")
    out.append(f"**Generated:** {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    out.append(f"**Tickers analyzed:** {', '.join(tickers) if tickers else 'none'}")
    if list(report.requested_tickers) != tickers:
        out.append(f"**Requested:** {', '.join(report.requested_tickers)}")
    out.append("")
    out.append(f"*{_HOW_TO_READ}*\n")

    if report.errors:
        out.append("## Excluded Tickers\n")
        for err in report.errors:
            out.append(f"- **{err.ticker}** — skipped: {err.error}")
        out.append("")

    # --- Scorecard ---
    out.append("## Scorecard\n")
    scored = [r for r in report.scorecard if r.overall_score is not None]
    if scored:
        out.append("| Rank | Ticker | Company | Overall (0–100) | Metric wins |")
        out.append("|------|--------|---------|-----------------|-------------|")
        for i, row in enumerate(report.scorecard, 1):
            score = f"{row.overall_score:.1f}" if row.overall_score is not None else "N/A"
            out.append(
                f"| {i} | **{row.ticker}** | {row.company_name[:24]} | {score} | {row.wins} |"
            )
        out.append("")
        out.append(
            "*Overall = equal-weighted mean of each ticker's normalized score "
            "(0–100, higher = better) across every ranked metric it has data for. "
            "Descriptive ranking only, not a recommendation.*\n"
        )

        rankable = _rankable_metrics(report)
        if rankable:
            out.append(
                "### Normalized scorecard by metric (0–100, higher = better; ★ = best in set)\n"
            )
            out.append("| Metric | " + " | ".join(tickers) + " |")
            out.append("|--------|" + "|".join(["------"] * len(tickers)) + "|")
            for metric in rankable:
                cells = []
                for t in tickers:
                    norm = metric.normalized.get(t)
                    if norm is None:
                        cells.append("N/A")
                    else:
                        star = " ★" if t in metric.winners else ""
                        cells.append(f"{norm:.0f}{star}")
                out.append(f"| {_metric_label(metric)} | " + " | ".join(cells) + " |")
            out.append("")
    else:
        out.append("*No rankable metrics were available across the selected tickers.*\n")

    # --- One table per dimension (raw values + rank) ---
    for dim in report.dimensions:
        out.append(f"## {dim.name}\n")
        out.append("| Metric | " + " | ".join(tickers) + " |")
        out.append("|--------|" + "|".join(["------"] * len(tickers)) + "|")
        for metric in dim.metrics:
            cells = []
            for t in tickers:
                value = metric.values.get(t)
                text = _fmt_value(value, metric.unit, report.currencies.get(t))
                if metric.rankable and value is not None:
                    rank = metric.ranks.get(t)
                    star = " ★" if t in metric.winners else ""
                    if rank:
                        text = f"{text} (#{rank}){star}"
                cells.append(text)
            out.append(f"| {_metric_label(metric)} | " + " | ".join(cells) + " |")
        out.append("")

    # --- Provenance ---
    out.append("## Provenance & Data Sources\n")
    out.append("Every number above is carried, unchanged, from a per-ticker report field:\n")
    seen: set[str] = set()
    for dim in report.dimensions:
        for metric in dim.metrics:
            if metric.label not in seen:
                seen.add(metric.label)
                out.append(f"- **{metric.label}** — {metric.source}")
    out.append("")
    for t in tickers:
        # Issue #74: enumerate every source with its reference link when known.
        recs = (report.source_records or {}).get(t, [])
        if recs:
            rendered = []
            for i, rec in enumerate(recs, 1):
                rendered.append(f"[{rec.name}]({rec.url})" if rec.url else rec.name)
            out.append(f"- **{t} data sources:** " + "; ".join(rendered))
        else:
            srcs = report.data_sources.get(t, [])
            out.append(f"- **{t} data sources:** " + (", ".join(srcs) if srcs else "not reported"))
    out.append("")

    if report.deferred_dimensions:
        out.append("## Coverage Note\n")
        out.append(
            "These dimensions are computed inside each single-ticker report but are "
            "not yet surfaced as structured, cross-ticker metrics (they appear as "
            "narrative in the per-ticker reports): "
            + ", ".join(report.deferred_dimensions)
            + ". They are deferred to a later increment so the single-ticker path "
            "stays untouched.\n"
        )

    out.append("---\n")
    out.append(report.disclaimer)
    out.append("")
    out.append(f"**Compliance:** {report.compliance_note}")
    out.append("")
    out.append(
        f"*Report prepared on {_PREPARED_ON_URL} — {report.generated_at.strftime('%Y-%m-%d')}. "
        f"Support: {_BMAC_URL}*"
    )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Self-contained HTML
# ---------------------------------------------------------------------------

_HTML_STYLE = (
    "\n"
    ":root { color-scheme: light; "
    "}\n"
    "* { box-sizing: border-box; "
    "}\n"
    "body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, "
    "sans-serif;\n"
    "  margin: 0; padding: 2rem; color: #1f2937; background: #ffffff; line-height: 1.5; "
    "}\n"
    ".wrap { max-width: 1040px; margin: 0 auto; "
    "}\n"
    "h1 { font-size: 1.6rem; margin: 0 0 .25rem; "
    "}\n"
    "h2 { font-size: 1.2rem; margin: 1.8rem 0 .6rem; border-bottom: 2px solid #e5e7eb; "
    "padding-bottom: .25rem; "
    "}\n"
    "h3 { font-size: 1.02rem; margin: 1.2rem 0 .5rem; color: #374151; "
    "}\n"
    ".meta { color: #4b5563; font-size: .9rem; margin: .1rem 0; "
    "}\n"
    ".howto { background: #f8fafc; border-left: 3px solid #2563eb; padding: .6rem .9rem; "
    "margin: 1rem "
    "0;\n"
    "  font-size: .9rem; color: #334155; border-radius: 4px; "
    "}\n"
    "table { border-collapse: collapse; width: 100%; margin: .5rem 0 1rem; font-size: .9rem; "
    "}\n"
    "th, td { border: 1px solid #e5e7eb; padding: .45rem .6rem; text-align: left; "
    "}\n"
    "th { background: #f1f5f9; font-weight: 600; "
    "}\n"
    "tbody tr:nth-child(even) { background: #fafafa; "
    "}\n"
    ".table-scroll { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; "
    "border-radius: 4px; "
    "}\n"
    ".table-scroll table { min-width: 100%; "
    "}\n"
    "@media (max-width: 640px) "
    "{\n"
    "  body { padding: 1rem; "
    "}\n"
    "  .table-scroll { margin-left: -1rem; margin-right: -1rem; padding-left: 1rem; "
    "padding-right: 1rem; width: auto; "
    "}\n"
    "  th, td { padding: .35rem .45rem; font-size: .8rem; "
    "}\n"
    "  h1 { font-size: 1.3rem; "
    "}\n"
    "}\n"
    ".win { color: #15803d; font-weight: 700; "
    "}\n"
    ".na { color: #9ca3af; "
    "}\n"
    "ul { margin: .3rem 0 1rem 1.2rem; padding: 0; "
    "}\n"
    "li { margin: .15rem 0; font-size: .9rem; "
    "}\n"
    ".disclaimer { background: #fffbeb; border: 1px solid #fde68a; padding: .8rem 1rem; "
    "border-radius: "
    "6px;\n"
    "  font-size: .85rem; color: #78350f; margin-top: 1.2rem; "
    "}\n"
    ".compliance { font-size: .85rem; color: #4b5563; margin-top: .8rem; "
    "}\n"
    "footer { margin-top: 1.6rem; padding-top: .8rem; border-top: 1px solid "
    "#e5e7eb;\n"
    "  font-size: .8rem; color: #6b7280; "
    "}\n"
    "footer a { color: #2563eb; "
    "}\n"
    ""
).strip()


def _esc(text: object) -> str:
    return html.escape(str(text))


def _html_table(header: list[str], rows: list[list[str]]) -> str:
    parts = ['<div class="table-scroll"><table>', "<thead><tr>"]
    parts += [f"<th>{_esc(h)}</th>" for h in header]
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def _cell_with_marker(text: str, is_winner: bool) -> str:
    safe = _esc(text)
    if text == "N/A":
        return f'<span class="na">{safe}</span>'
    if is_winner:
        return f'<span class="win">{safe} ★</span>'
    return safe


def render_html(report: ComparativeReport, white_label: WhiteLabelProfile | None = None) -> str:
    """Render the comparative report as a self-contained HTML document.

    `white_label` only changes chrome (brand name, footer, accent color) —
    never evidence: numbers, sources, methodology and disclaimers are untouched.
    """
    tickers = report.tickers
    heading = " vs ".join(tickers) if tickers else "(no valid tickers)"
    body: list[str] = []

    body.append(f"<h1>Comparative Research Report — {_esc(heading)}</h1>")
    body.append(
        f'<p class="meta"><strong>Generated:</strong> '
        f"{_esc(report.generated_at.strftime('%Y-%m-%d %H:%M UTC'))}</p>"
    )
    body.append(
        f'<p class="meta"><strong>Tickers analyzed:</strong> '
        f"{_esc(', '.join(tickers) if tickers else 'none')}</p>"
    )
    if list(report.requested_tickers) != tickers:
        body.append(
            f'<p class="meta"><strong>Requested:</strong> '
            f"{_esc(', '.join(report.requested_tickers))}</p>"
        )
    body.append(f'<div class="howto">{_esc(_HOW_TO_READ)}</div>')

    if report.errors:
        body.append("<h2>Excluded Tickers</h2><ul>")
        for err in report.errors:
            body.append(
                f"<li><strong>{_esc(err.ticker)}</strong> — skipped: {_esc(err.error)}</li>"
            )
        body.append("</ul>")

    # --- Scorecard ---
    body.append("<h2>Scorecard</h2>")
    scored = [r for r in report.scorecard if r.overall_score is not None]
    if scored:
        rows = []
        for i, row in enumerate(report.scorecard, 1):
            score = f"{row.overall_score:.1f}" if row.overall_score is not None else "N/A"
            rows.append(
                [
                    _esc(i),
                    f"<strong>{_esc(row.ticker)}</strong>",
                    _esc(row.company_name[:24]),
                    _esc(score),
                    _esc(row.wins),
                ]
            )
        body.append(
            _html_table(["Rank", "Ticker", "Company", "Overall (0–100)", "Metric wins"], rows)
        )
        body.append(
            '<p class="meta">Overall = equal-weighted mean of each ticker\'s normalized score '
            "(0–100, higher = better) across every ranked metric it has data for. "
            "Descriptive ranking only, not a recommendation.</p>"
        )

        rankable = _rankable_metrics(report)
        if rankable:
            body.append(
                "<h3>Normalized scorecard by metric (0–100, higher = better; ★ = best in set)</h3>"
            )
            rows = []
            for metric in rankable:
                cells = [_esc(_metric_label(metric))]
                for t in tickers:
                    norm = metric.normalized.get(t)
                    if norm is None:
                        cells.append('<span class="na">N/A</span>')
                    else:
                        cells.append(_cell_with_marker(f"{norm:.0f}", t in metric.winners))
                rows.append(cells)
            body.append(_html_table(["Metric", *tickers], rows))
    else:
        body.append(
            '<p class="na">No rankable metrics were available across the selected tickers.</p>'
        )

    # --- Dimensions ---
    for dim in report.dimensions:
        body.append(f"<h2>{_esc(dim.name)}</h2>")
        rows = []
        for metric in dim.metrics:
            cells = [_esc(_metric_label(metric))]
            for t in tickers:
                value = metric.values.get(t)
                text = _fmt_value(value, metric.unit, report.currencies.get(t))
                if metric.rankable and value is not None:
                    rank = metric.ranks.get(t)
                    if rank:
                        text = f"{text} (#{rank})"
                    cells.append(_cell_with_marker(text, t in metric.winners))
                else:
                    cells.append(_cell_with_marker(text, False))
            rows.append(cells)
        body.append(_html_table(["Metric", *tickers], rows))

    # --- Provenance ---
    body.append("<h2>Provenance &amp; Data Sources</h2>")
    body.append(
        '<p class="meta">Every number above is carried, unchanged, from a per-ticker report '
        'field:</p><ul>'
    )
    seen: set[str] = set()
    for dim in report.dimensions:
        for metric in dim.metrics:
            if metric.label not in seen:
                seen.add(metric.label)
                body.append(
                    f"<li><strong>{_esc(metric.label)}</strong> — {_esc(metric.source)}</li>"
                )
    for t in tickers:
        # Issue #74: enumerate every source with its reference link when known.
        recs = (report.source_records or {}).get(t, [])
        if recs:
            items = []
            for rec in recs:
                label = _esc(rec.name)
                items.append(f'<a href="{_esc(rec.url)}">{label}</a>' if rec.url else label)
            body.append(f"<li><strong>{_esc(t)} data sources:</strong> {'; '.join(items)}</li>")
        else:
            srcs = report.data_sources.get(t, [])
            body.append(
                f"<li><strong>{_esc(t)} data sources:</strong> "
                f"{_esc(', '.join(srcs) if srcs else 'not reported')}</li>"
            )
    body.append("</ul>")

    if report.deferred_dimensions:
        body.append("<h2>Coverage Note</h2>")
        body.append(
            '<p class="meta">These dimensions are computed inside each single-ticker report '
            "but are not yet surfaced as structured, cross-ticker metrics (they appear as "
            "narrative in the per-ticker reports): "
            + _esc(", ".join(report.deferred_dimensions))
            + (
                ". They are deferred to a later increment so the single-ticker path stays "
                "untouched.</p>"
            )
        )

    body.append(f'<div class="disclaimer">{_esc(report.disclaimer)}</div>')
    body.append(
        f'<p class="compliance"><strong>Compliance:</strong> {_esc(report.compliance_note)}</p>'
    )
    body.append(_render_footer(report, white_label))

    title = _esc(f"Comparative Report — {heading}")
    style = _HTML_STYLE
    if white_label is not None and white_label.is_active() and white_label.accent_color:
        style += f"\n:root{{--accent:{_esc(white_label.accent_color)};}}\n"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title>"
        f"<style>{style}</style>"
        '</head><body><div class="wrap">' + "".join(body) + "</div></body></html>"
    )


def _render_footer(report: ComparativeReport, white_label: WhiteLabelProfile | None) -> str:
    """Report footer. White-label overrides chrome only — never evidence."""
    date = _esc(report.generated_at.strftime("%Y-%m-%d"))
    if white_label is not None and white_label.is_active():
        prepared_on = white_label.prepared_on_url or _PREPARED_ON_URL
        if white_label.org_name:
            brand = f"Report prepared by {_esc(white_label.org_name)} — {date}."
        else:
            brand = (
                f'Report prepared on <a href="{_esc(prepared_on)}">{_esc(prepared_on)}</a> — '
                f'{date}.'
            )
        support = (
            f' <a href="{_BMAC_URL}">Buy Me a Coffee</a>' if white_label.show_support_link else ""
        )
        note = f" {_esc(white_label.footer_note)}" if white_label.footer_note else ""
        return f"<footer>{brand}{support}{note}</footer>"
    return (
        f'<footer>Report prepared on <a href="{_PREPARED_ON_URL}">{_esc(_PREPARED_ON_URL)}</a> — '
        f"{date}. "
        f'<a href="{_BMAC_URL}">Buy Me a Coffee</a></footer>'
    )
