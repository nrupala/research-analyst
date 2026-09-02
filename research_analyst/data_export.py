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
from typing import Any


def build_bundle(response: Any) -> dict[str, Any]:
    """Build the source-data bundle from a typed ResearchResponse."""
    bundle: dict[str, Any] = {
        "schema_version": "1.0",
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
    metrics = {
        "valuation": getattr(rep, "valuation", None),
        "risk_matrix": getattr(rep, "risk_matrix", None),
        "capital_allocation": getattr(rep, "capital_allocation", None),
        "dividend": getattr(rep, "dividend", None),
    }
    out: dict[str, Any] = {}
    if metrics["valuation"]:
        out["current_price"] = metrics["valuation"].current_price
        out["primary_methodology"] = metrics["valuation"].primary_methodology
    if metrics["dividend"]:
        d = metrics["dividend"]
        out["dividend_yield"] = getattr(d, "current_yield", None)
        out["payout_ratio"] = getattr(d, "payout_ratio", None)
        out["annual_dividends"] = getattr(d, "annual_dividends", {})
    if metrics["risk_matrix"]:
        out["risk_score"] = metrics["risk_matrix"].overall_risk_score
    if metrics["capital_allocation"]:
        ca = metrics["capital_allocation"]
        out["fcf_deployment"] = {
            "capex": getattr(ca, "capex_pct", None),
            "buybacks": getattr(ca, "buyback_pct", None),
            "dividends": getattr(ca, "dividend_pct", None),
        }
    if out:
        bundle["metrics"] = out


def _extract_scenarios(rep: Any, bundle: dict[str, Any]) -> None:
    val = getattr(rep, "valuation", None)
    if not val:
        return
    for s in val.scenarios:
        bundle["scenarios"].append({
            "label": s.label,
            "price_low": s.implied_price_low,
            "price_high": s.implied_price_high,
            "revenue_growth": getattr(s, "revenue_growth", None),
            "operating_margin": getattr(s, "operating_margin", None),
            "pe_multiple": getattr(s, "pe_multiple", None),
        })


def _extract_peers(rep: Any, bundle: dict[str, Any]) -> None:
    for sec in getattr(rep, "sections", []):
        for vis in getattr(sec, "visuals", []):
            if vis.visual_type == "table" and "Ticker" in vis.content:
                rows = _parse_md_table(vis.content)
                if rows:
                    bundle["peers"].extend(rows[1:])  # skip header
                    return


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
