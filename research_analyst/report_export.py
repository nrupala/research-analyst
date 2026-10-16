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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""Report export (Stream B / F1.6) — exports of OUR analysis only.

The licensing boundary (owner's ruling, 2026-10-15) is structural
here: exports carry the analysis RA produced — valuation scenarios,
risk scores, capital-allocation and dividend analysis, declared data
sources — and NEVER the underlying source data (no price-history
rows, no statement dumps). A CSV of daily prices would be source
data in a new jacket; it is deliberately not offered.

Formats:
  - CSV: the report's computed tables, one (group, metric, value)
    row set per report — spreadsheet-ready.
  - PDF: the report markdown rendered as a clean text document by a
    small stdlib-only PDF writer (Helvetica core font, no external
    dependencies to own or audit).
  - Embed card: a compact standalone HTML summary for third-party
    pages, always carrying the price's source label and the short
    disclaimer.
Missing values export as "Not available" — never as zero.
"""
# Module: research_analyst/report_export.py | Version: 0.1.0 | Updated: 2026-10-15

from __future__ import annotations

import csv
import html
import io
import textwrap

from .api_models import ResearchAPIResponse
from .disclaimer import DISCLAIMER_SHORT
from .models import PRICE_SOURCE_LABELS
from .reports.currency import money

NA = "Not available"


def _num(value: float | None) -> str:
    # No thousands grouping: a CSV is data, and "1,196.00" imports as
    # text in several spreadsheet tools; "1196.00" imports as a number.
    return NA if value is None else f"{value:.2f}"


def _pct(value: float | None) -> str:
    return NA if value is None else f"{value * 100:.1f}%"


def _price_source_name(resp: ResearchAPIResponse) -> str:
    """The serving price source's display name, from the declared
    Data Sources (e.g. "yfinance (price data)" -> "Yahoo Finance").
    "" when the report declares none — never guessed."""
    for entry in resp.metadata.data_sources:
        if "price data" in entry:
            key = entry.split(" (", 1)[0].strip().lower()
            return PRICE_SOURCE_LABELS.get(key, key)
    return ""


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def research_csv(resp: ResearchAPIResponse) -> str:
    """The analysis tables of every report in the response, as CSV."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["group", "metric", "value"])
    writer.writerow(["report", "ticker", resp.ticker])
    writer.writerow(["report", "company", resp.company_name])
    writer.writerow(["report", "security_type", resp.security_type])
    writer.writerow(["report", "currency", resp.currency])
    if resp.metadata.data_as_of:
        writer.writerow(["report", "data_as_of", resp.metadata.data_as_of])
    writer.writerow(
        ["report", "data_sources_declared", "; ".join(resp.metadata.data_sources)]
    )
    source_name = _price_source_name(resp)
    for report in resp.reports:
        writer.writerow(["report", "generated_at", report.generated_at.isoformat()])
        v = report.valuation
        if v is not None:
            writer.writerow(["valuation", "current_price", _num(v.current_price)])
            if source_name:
                writer.writerow(["valuation", "price_source", source_name])
            writer.writerow(["valuation", "methodology", v.primary_methodology])
            for s in v.scenarios:
                label = s.label or s.scenario_type.value
                scenario_rows = [
                    ("revenue growth", _pct(s.revenue_growth)),
                    ("operating margin", _pct(s.operating_margin)),
                    ("implied price low", _num(s.implied_price_low)),
                    ("implied price high", _num(s.implied_price_high)),
                    ("implied upside low", _pct(s.implied_upside_low)),
                    ("implied upside high", _pct(s.implied_upside_high)),
                ]
                for metric, value in scenario_rows:
                    writer.writerow(["valuation", f"{label} — {metric}", value])
        if report.risk_matrix is not None:
            writer.writerow(
                ["risk", "overall_risk_score", _num(report.risk_matrix.overall_risk_score)]
            )
        ca = report.capital_allocation
        if ca is not None:
            writer.writerow(["capital_allocation", "period", ca.period])
            writer.writerow(["capital_allocation", "roic", _pct(ca.roic)])
            writer.writerow(["capital_allocation", "roic_minus_wacc", _pct(ca.roic_minus_wacc)])
            writer.writerow(["capital_allocation", "shareholder_yield", _pct(ca.shareholder_yield)])
        d = report.dividend
        if d is not None:
            writer.writerow(["dividend", "pays_dividend", "yes" if d.pays_dividend else "no"])
            writer.writerow(["dividend", "current_yield", _pct(d.current_yield)])
            writer.writerow(["dividend", "payout_ratio_fcf", _pct(d.payout_ratio_fcf)])
            writer.writerow(["dividend", "safety_score", _num(d.safety_score)])
            writer.writerow(["dividend", "growth_5y_cagr", _pct(d.dividend_growth_5y_cagr)])
    return out.getvalue()


# ---------------------------------------------------------------------------
# PDF (stdlib-only writer; Helvetica core font, uncompressed streams)
# ---------------------------------------------------------------------------

# WinAnsi (cp1252) covers € £ — ' ' " " • – — but not the rupee sign;
# map it to its plain-text form rather than dropping or corrupting it.
_PDF_CHAR_MAP = {"\u20b9": "Rs. ", "\u2192": "->", "\u2713": "v", "\u2717": "x"}


def _pdf_text(text: str) -> str:
    for src, dst in _PDF_CHAR_MAP.items():
        text = text.replace(src, dst)
    return text.encode("cp1252", errors="replace").decode("cp1252")


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _markdown_lines(markdown: str) -> list[tuple[str, str]]:
    """Flatten report markdown to (style, text) lines for the writer.

    Styles: h1 (report title), h2 (section heads), body. Markdown
    punctuation is stripped; pipe tables survive as text rows (the
    PDF is the printable record of the same report, not a re-layout).
    """
    lines: list[tuple[str, str]] = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.strip() in ("---", "***", ""):
            lines.append(("body", ""))
            continue
        style = "body"
        if line.startswith("# "):
            style, line = "h1", line[2:]
        elif line.startswith("## "):
            style, line = "h2", line[3:]
        elif line.startswith("### "):
            style, line = "h2", line[4:]
        line = line.replace("**", "").replace("`", "")
        wrapped = textwrap.wrap(
            _pdf_text(line), width=108 if style == "body" else 60,
            break_long_words=True, break_on_hyphens=False,
        ) or [""]
        lines.extend((style, w) for w in wrapped)
    return lines


def research_pdf(resp: ResearchAPIResponse) -> bytes:
    """The full report (all reports in the response) as a PDF file."""
    markdown = "\n\n".join(resp.reports_markdown)
    styled = _markdown_lines(markdown)

    # Paginate: A4-ish letter page, 48pt margins, footer at 30pt.
    heights = {"h1": 22.0, "h2": 17.0, "body": 13.2}
    fonts = {"h1": ("F2", 15), "h2": ("F2", 11.5), "body": ("F1", 9.5)}
    pages: list[list[tuple[str, str]]] = []
    page: list[tuple[str, str]] = []
    y = 752.0
    for style, text in styled:
        h = heights[style]
        if y - h < 56 and page:
            pages.append(page)
            page, y = [], 752.0
        page.append((style, text))
        y -= h
    if page or not pages:
        pages.append(page)

    objects: list[bytes] = []

    def add(obj: str | bytes) -> int:
        objects.append(obj.encode("latin-1") if isinstance(obj, str) else obj)
        return len(objects)  # 1-based object number

    total_pages = len(pages)
    # Object layout: 1 catalog, 2 pages, 3/4 fonts, then page+content pairs.
    page_obj_numbers = [5 + 2 * i for i in range(total_pages)]
    kids = " ".join(f"{n} 0 R" for n in page_obj_numbers)
    add("<< /Type /Catalog /Pages 2 0 R >>")
    add(f"<< /Type /Pages /Kids [{kids}] /Count {total_pages} >>")
    add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    footer = "Research Analyst - research and analysis, not investment advice."
    for i, page_lines in enumerate(pages):
        content_obj = 6 + 2 * i
        ops: list[str] = []
        yy = 752.0
        for style, text in page_lines:
            fname, fsize = fonts[style]
            yy -= heights[style]
            if text:
                ops.append(
                    f"BT /{fname} {fsize} Tf 48 {yy:.1f} Td ({_pdf_escape(text)}) Tj ET"
                )
        ops.append(
            f"BT /F1 7.5 Tf 48 30 Td ({_pdf_escape(footer)}  Page {i + 1} of {total_pages}) Tj ET"
        )
        # cp1252, not latin-1: the WinAnsi high range (€, —, ‘’“”) sits
        # at 0x80-0x9F, which latin-1 would corrupt or fail to encode.
        stream = "\n".join(ops).encode("cp1252")
        add(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {content_obj} 0 R >>"
        )
        add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for num, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{num} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")
    xref_at = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode()
    )
    return out.getvalue()


# ---------------------------------------------------------------------------
# Embed card
# ---------------------------------------------------------------------------


def embed_card_html(resp: ResearchAPIResponse, *, app_url: str) -> str:
    """A compact, self-contained summary card for third-party pages.

    Inline styles + system fonts only (no external assets of any
    kind). Every value is escaped; the price always carries its
    source label, and the short disclaimer always rides along.
    """
    report = resp.reports[0] if resp.reports else None
    v = report.valuation if report else None
    price = money(v.current_price, resp.currency) if v else NA
    source_name = _price_source_name(resp)
    source_note = f" (source: {html.escape(source_name)})" if source_name else ""
    base = None
    if v and v.scenarios:
        base = next(
            (s for s in v.scenarios if s.scenario_type.value == "base"),
            v.scenarios[0],
        )
    range_line = ""
    if base is not None and base.implied_price_low is not None:
        range_line = (
            f"<p>Base case value range: {html.escape(money(base.implied_price_low, resp.currency))}"
            f" – {html.escape(money(base.implied_price_high, resp.currency))}</p>"
        )
    risk_line = ""
    risk = report.risk_matrix if report else None
    if risk is not None and risk.overall_risk_score is not None:
        risk_line = f"<p>Overall risk score: {risk.overall_risk_score:.1f} / 10</p>"
    as_of = resp.metadata.data_as_of or (report.generated_at.date().isoformat() if report else "")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(resp.company_name)} ({html.escape(resp.ticker)}) — Research Analyst</title>
<style>
body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; }}
.card {{ border: 1px solid #d4d4d8; border-radius: 12px; padding: 16px 18px;
  max-width: 420px; color: #18181b; }}
.card h1 {{ font-size: 17px; margin: 0 0 2px; }}
.card .ticker {{ color: #52525b; font-size: 13px; }}
.card .price {{ font-size: 22px; font-weight: 650; margin: 10px 0 4px; }}
.card p {{ margin: 4px 0; font-size: 14px; }}
.card .meta {{ color: #52525b; font-size: 12px; margin-top: 10px; }}
.card a {{ color: #1d4ed8; }}
</style></head><body>
<div class="card">
<h1>{html.escape(resp.company_name)}</h1>
<div class="ticker">{html.escape(resp.ticker)} · Research Analyst report</div>
<div class="price">{html.escape(price)}
<span style="font-size:12px;font-weight:400">{source_note}</span></div>
{range_line}
{risk_line}
<p class="meta">Data as of {html.escape(as_of)}. {html.escape(DISCLAIMER_SHORT)}</p>
<p class="meta"><a href="{html.escape(app_url)}" target="_blank" rel="noopener">Read the full
report</a></p>
</div>
</body></html>"""
