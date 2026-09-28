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

"""Source-data bundle export (Phase 8c-2 — paid feature).

Builds a machine-ready bundle of the raw data behind a report: prices,
financials, key metrics, valuation scenarios, and (when available) peers.
Available as JSON (canonical) and CSV (spreadsheet-friendly). The bundle is
what a paid customer downloads to work the numbers in their own tools.
"""
# Module: research_analyst/data_export.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Any


def build_bundle(response: Any) -> dict[str, Any]:
    """Build the source-data bundle from a typed ResearchResponse."""
    bundle: dict[str, Any] = {
        # 1.1: metrics.payout_ratio removed (phantom field, always null) in
        # favour of payout_ratio_eps / payout_ratio_fcf; fcf_deployment keys
        # renamed to the model's *_pct_of_fcf; annual_dividends split into
        # complete vs partial years; peer_median_yield, peer_yields,
        # us_10y_yield, yield_vs_treasury_spread, risk_score_note, and the
        # scenario ev_ebitda_multiple / implied_upside_* / assumptions added;
        # scenarios and peers deduplicated; metrics merged instead of
        # last-report-wins.
        "schema_version": "1.1",
        "ticker": response.ticker,
        "company_name": getattr(response, "company_name", ""),
        "currency": getattr(response, "currency", "USD"),
        "generated_at": response.generated_at.isoformat() if response.generated_at else "",
        "security_type": (
            response.security_type.value if getattr(response, "security_type", None) else ""
        ),
        "tables": [],
        "metrics": {},
        "scenarios": [],
        "peers": [],
    }

    # --- report tables (financial summary, key metrics, dividend summary) ---
    # The typed ReportOutput exposes its content as markdown tables inside
    # section visuals; parse them into structured rows so a customer gets the
    # actual numbers, not just prose.
    seen_tables: set[str] = set()
    for rep in getattr(response, "reports", []):
        _extract_tables(rep, bundle, seen_tables)
        _extract_metrics(rep, bundle)
        _extract_scenarios(rep, bundle)
        _extract_peers(rep, bundle)

    return bundle


def _extract_tables(rep: Any, bundle: dict[str, Any], seen: set[str]) -> None:
    for sec in getattr(rep, "sections", []):
        for vis in getattr(sec, "visuals", []):
            if vis.visual_type != "table" or not vis.content:
                continue
            rows = _parse_md_table(vis.content)
            if not rows:
                continue
            title = (vis.title or sec.title or "table").strip()
            if title in seen:
                continue
            seen.add(title)
            bundle["tables"].append({"title": title, "rows": rows})


def _extract_metrics(rep: Any, bundle: dict[str, Any]) -> None:
    out: dict[str, Any] = {}
    valuation = getattr(rep, "valuation", None)
    if valuation:
        out["current_price"] = valuation.current_price
        out["primary_methodology"] = valuation.primary_methodology

    dividend = getattr(rep, "dividend", None)
    if dividend:
        d = dividend
        out["dividend_yield"] = getattr(d, "current_yield", None)
        # EPS and FCF payout are different numbers on different bases; they must
        # stay distinguishable. There is no single `payout_ratio` on the model.
        out["payout_ratio_eps"] = getattr(d, "payout_ratio_eps", None)
        out["payout_ratio_fcf"] = getattr(d, "payout_ratio_fcf", None)
        out["annual_dividend_rate"] = getattr(d, "annual_dividend_rate", None)
        out["peer_median_yield"] = getattr(d, "peer_median_yield", None)
        out["us_10y_yield"] = getattr(d, "us_10y_yield", None)
        out["yield_vs_treasury_spread"] = getattr(
            d, "yield_vs_treasury_spread", None
        )
        out["annual_dividends_complete_years"] = _complete_dividend_years(d)
        partial = _partial_dividend_years(d)
        if partial:
            out["annual_dividends_partial"] = partial

    risk_matrix = getattr(rep, "risk_matrix", None)
    if risk_matrix:
        # None here is meaningful: no material risks means no score is
        # published (renderer #71). Export the reason rather than a bare null.
        out["risk_score"] = risk_matrix.overall_risk_score
        if risk_matrix.overall_risk_score is None:
            out["risk_score_note"] = (
                "No score published: no material risks were identified "
                "(see the Risk Matrix table for the risk inventory)."
            )

    capital_allocation = getattr(rep, "capital_allocation", None)
    if capital_allocation:
        ca = capital_allocation
        out["fcf_deployment"] = {
            "capex_pct_of_fcf": getattr(ca, "capex_pct_of_fcf", None),
            "buyback_pct_of_fcf": getattr(ca, "buyback_pct_of_fcf", None),
            "dividend_pct_of_fcf": getattr(ca, "dividend_pct_of_fcf", None),
        }

    _merge_metrics(bundle, out)


def _merge_metrics(bundle: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Merge one report's metrics into the bundle.

    A bundle spans every requested report, so metrics accumulate. Precedence
    rule: a populated value is never overwritten by a null, so a later sparse
    report cannot erase what an earlier one computed. Two non-null values for
    the same key keep the first, which makes the result order-independent for
    any request whose reports describe the same security.
    """
    current: dict[str, Any] = bundle["metrics"]
    for key, value in incoming.items():
        if key not in current or current[key] is None:
            current[key] = value
        elif isinstance(current[key], dict) and isinstance(value, dict):
            merged = dict(current[key])
            for sub_key, sub_value in value.items():
                if sub_key not in merged or merged[sub_key] is None:
                    merged[sub_key] = sub_value
            current[key] = merged


def _complete_dividend_years(d: Any) -> dict[str, float]:
    """Annual DPS excluding the in-progress calendar year."""
    annual = getattr(d, "annual_dividends", {}) or {}
    current_year = date.today().year
    return {
        k: v for k, v in annual.items()
        if int(k) < current_year
    }


def _partial_dividend_years(d: Any) -> dict[str, float]:
    """Annual DPS for the in-progress calendar year, if any."""
    annual = getattr(d, "annual_dividends", {}) or {}
    current_year = date.today().year
    return {
        k: v for k, v in annual.items()
        if int(k) >= current_year
    }


def _extract_scenarios(rep: Any, bundle: dict[str, Any]) -> None:
    val = getattr(rep, "valuation", None)
    if not val:
        return
    existing = {s.get("scenario_type") for s in bundle["scenarios"]}
    for s in val.scenarios:
        stype = getattr(s, "scenario_type", None)
        stype = getattr(stype, "value", stype)
        if stype in existing:
            continue
        existing.add(stype)
        bundle["scenarios"].append({
            "scenario_type": stype,
            "label": s.label,
            "price_low": s.implied_price_low,
            "price_high": s.implied_price_high,
            "revenue_growth": getattr(s, "revenue_growth", None),
            "operating_margin": getattr(s, "operating_margin", None),
            "pe_multiple": getattr(s, "pe_multiple", None),
            "ev_ebitda_multiple": getattr(s, "ev_ebitda_multiple", None),
            "implied_upside_low": getattr(s, "implied_upside_low", None),
            "implied_upside_high": getattr(s, "implied_upside_high", None),
            # Provenance travels with the number rather than living only in
            # the rendered report.
            "assumptions": [
                {
                    "label": a.label,
                    "value": a.value,
                    "source": a.source,
                    "confidence": a.confidence,
                }
                for a in getattr(s, "assumptions", [])
            ],
        })


def _clean_cell(cell: str) -> str:
    """Strip markdown emphasis from a table cell.

    ``**VZ**`` -> ``VZ``. Both ends matter: ``lstrip("*")`` alone leaves the
    closing ``**`` attached, which would ship as a ``peer_yields`` dict key of
    ``"VZ**"`` and break dedupe against rows from another report.
    """
    return cell.strip().strip("*").strip()


def _extract_peers(rep: Any, bundle: dict[str, Any]) -> None:
    seen = {_clean_cell(row[0]) for row in bundle["peers"] if row}
    for sec in getattr(rep, "sections", []):
        for vis in getattr(sec, "visuals", []):
            if vis.visual_type != "table" or "Ticker" not in vis.content:
                continue
            rows = _parse_md_table(vis.content)
            if not rows:
                continue
            header = [c.strip() for c in rows[0]]
            yi = header.index("Div Yield") if "Div Yield" in header else None
            for row in rows[1:]:  # skip header
                if not row:
                    continue
                ticker = _clean_cell(row[0])
                if ticker in seen:
                    continue
                seen.add(ticker)
                bundle["peers"].append(row)
                if yi is not None and yi < len(row):
                    frac = _parse_pct(row[yi])
                    if frac is not None:
                        bundle["metrics"].setdefault("peer_yields", {})[ticker] = frac
            return


def _parse_pct(cell: str) -> float | None:
    """'3.41%' -> 0.0341. Returns None for N/A or unparseable cells."""
    cell = _clean_cell(cell)
    if not cell or cell.upper() in {"N/A", "NA", "N/M", "-"}:
        return None
    try:
        return float(cell.rstrip("%")) / 100.0
    except ValueError:
        return None


def _parse_md_table(md: str) -> list[list[str]]:
    rows = []
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("|") and not re_full_sep(line):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells:
                rows.append(cells)
    return rows


def re_full_sep(line: str) -> bool:
    """True when a markdown line is a separator row (--- / :--: / --:)."""
    stripped = line.replace(" ", "").replace("|", "")
    if not stripped:
        return False
    return set(stripped.replace(":", "").replace("-", "")) == set()


def bundle_to_csv(bundle: dict[str, Any]) -> str:
    """Flatten the bundle into a single CSV (spreadsheet-friendly)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ticker", "company", "currency", "generated_at", "security_type"])
    writer.writerow([
        bundle["ticker"], bundle["company_name"], bundle["currency"],
        bundle["generated_at"], bundle["security_type"],
    ])
    writer.writerow([])
    writer.writerow(["section", "key", "value"])
    for section, data in bundle.items():
        if section in ("ticker", "company_name", "currency", "generated_at", "security_type"):
            continue
        if section == "tables":
            for i, t in enumerate(data):
                writer.writerow([f"table[{i}]", t.get("title", ""), ""])
                for j, row in enumerate(t.get("rows", [])):
                    writer.writerow([
                        f"table[{i}].row[{j}]",
                        row[0] if row else "",
                        ", ".join(row[1:]),
                    ])
            continue
        if isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    for k, v in item.items():
                        writer.writerow([f"{section}[{i}]", k, _csv_val(v)])
                else:
                    writer.writerow([section, i, _csv_val(item)])
        elif isinstance(data, dict):
            for k, v in data.items():
                writer.writerow([section, k, _csv_val(v)])
    return buf.getvalue()


def _csv_val(v: Any) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    if v is None:
        return ""
    return str(v)
