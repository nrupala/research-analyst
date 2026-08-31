"""thinkwithfinance cross-reference layer (Phase 4 cross-referencing support).

Intent: RA reports carry a "Learn more on thinkwithfinance" block that links to
supporting articles. The CONTENT lives in the thinkwithfinance site/repo (content
team / Milo); this module is the contract + deterministic renderer:

  * ``CROSSREF_INDEX`` — the single registry mapping a topic key to article
    metadata. Seeded with the DEFAULT entries; the live index is loaded from
    ``settings.market.cache_dir/crossref_index.json`` when present (so content
    can be published without a code release).
  * ``crossref_for(subject, ticker, report_type)`` — best-match lookup using a
    topic-key template mapped from the report; never crashes on a miss.

The loading of the real index is strictly additive: if the JSON file is absent
or invalid, the module falls back to the in-code default (which intentionally
contains no article URLs until thinkwithfinance content ships).
"""
# Module: research_analyst/crossref.py | Version: 1.0 | Updated: 2026-08-31

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TWF_ROOT = "https://thinkwithfinance.com"

# topic-key -> {"title": ..., "path": ..., "blurb": ...}
# DEFAULT entries are placeholders WITHOUT a path: they render only when a path
# is present, so the block disappears from reports until content exists.
# The live index (from cache_dir/crossref_index.json) ADDS paths; it never
# removes the default topic skeleton.
_CROSSREF_DEFAULT: dict[str, dict[str, str]] = {
    "valuation": {
        "title": "How to think about valuation", "path": "",
        "blurb": "Frameworks for intrinsic value and scenario analysis.",
    },
    "dividends": {
        "title": "Dividend investing fundamentals", "path": "",
        "blurb": "Yield, payout, and reinvestment basics.",
    },
    "etf_101": {
        "title": "ETF mechanics", "path": "",
        "blurb": "Expense ratios, tracking, and fund structure.",
    },
    "technical_analysis": {
        "title": "Reading charts and indicators", "path": "",
        "blurb": "Trend, momentum, and support/resistance.",
    },
    "macro": {
        "title": "Macro regimes and your portfolio", "path": "",
        "blurb": "Rates, inflation, and growth cycles.",
    },
    "risk_management": {
        "title": "Risk and position sizing", "path": "",
        "blurb": "Probability, impact, and drawdown thinking.",
    },
}

# Which topic keys a report should surface, per report type + subject kind.
_TOPIC_MAP: dict[str, list[str]] = {
    "comprehensive": ["valuation", "risk_management", "technical_analysis"],
    "long_term": ["valuation", "dividends", "macro"],
    "tactical": ["technical_analysis", "macro", "risk_management"],
    "etf": ["etf_101", "valuation", "risk_management"],
}


def load_crossref_index(path: str | Path | None = None) -> dict[str, dict[str, str]]:
    """Load the live index (additive over the default). Never raises."""
    index: dict[str, dict[str, str]] = {k: dict(v) for k, v in _CROSSREF_DEFAULT.items()}
    if not path:
        return index
    try:
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("index must be an object")
        for key, entry in data.items():
            if isinstance(entry, dict):
                base = dict(index.get(key, {}))
                base.update({k: str(v) for k, v in entry.items() if isinstance(v, str)})
                index[key] = base
    except (OSError, ValueError, json.JSONDecodeError) as e:
        logger.warning("crossref index load failed (%s); using defaults: %s", path, e)
    return index


def _topics(report_type: str, is_etf: bool) -> list[str]:
    keys = _TOPIC_MAP.get(report_type, _TOPIC_MAP["comprehensive"])
    if is_etf and "etf_101" not in keys:
        keys = ["etf_101", *keys]
    return keys


def crossref_for(
    subject: str,
    ticker: str,
    report_type: str = "comprehensive",
    is_etf: bool = False,
    index: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Return the cross-reference links for a report (empty list when content
    hasn't been published for any matched topic — the block then disappears)."""
    index = index if index is not None else _CROSSREF_DEFAULT
    links: list[dict[str, str]] = []
    for key in _topics(report_type, is_etf):
        entry = index.get(key)
        if not entry or not entry.get("path"):
            continue
        links.append({
            "topic": key,
            "title": entry.get("title", key.replace("_", " ").title()),
            "url": f"{TWF_ROOT}/{entry['path'].lstrip('/')}",
            "blurb": entry.get("blurb", ""),
        })
    return links


def render_crossref_block(
    subject: str,
    ticker: str,
    report_type: str = "comprehensive",
    is_etf: bool = False,
    index: dict[str, dict[str, str]] | None = None,
) -> str:
    """Markdown block appended to a report. Empty string when no content exists —
    so the section is invisible until thinkwithfinance actually ships articles."""
    links = crossref_for(subject, ticker, report_type, is_etf, index)
    if not links:
        return ""
    out = ["", "## Learn More — thinkwithfinance", ""]
    for link in links:
        blurb = f" — {link['blurb']}" if link["blurb"] else ""
        out.append(f"- [{link['title']}]({link['url']}){blurb}")
    out.append("")
    return "\n".join(out)
