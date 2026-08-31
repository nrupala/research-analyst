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
# Module: research_analyst/crossref.py | Version: 1.1 | Updated: 2026-08-31

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
    "how_to_read": {
        "title": "How to read this research report",
        "path": "p/how-to-read-an-equity-research-report",
        "blurb": "What the 7-step structure means and how to use it.",
    },
    "business_model": {
        "title": "Understanding a company's business model",
        "path": "p/understanding-a-company-business-model",
        "blurb": "Revenue streams, cost structure, and value chains.",
    },
    "fundamentals": {
        "title": "Reading financial statements like an analyst",
        "path": "p/reading-financial-statements-like-an-analyst",
        "blurb": "Growth, profitability, balance sheet, and earnings quality.",
    },
    "valuation": {
        "title": "How to think about valuation",
        "path": "p/how-to-think-about-valuation",
        "blurb": "Frameworks for intrinsic value and scenario analysis.",
    },
    "dividends": {
        "title": "Dividend investing fundamentals",
        "path": "p/reading-the-dividend-payout-ratio",
        "blurb": "Yield, payout, and reinvestment basics.",
    },
    "etf_101": {
        "title": "ETF mechanics",
        "path": "p/index-funds-and-etfs-explained",
        "blurb": "Expense ratios, tracking, and fund structure.",
    },
    "technical_analysis": {
        "title": "Reading charts and indicators",
        "path": "p/reading-stock-charts-and-technical-indicators",
        "blurb": "Trend, momentum, and support/resistance.",
    },
    "macro": {
        "title": "Macro regimes and your portfolio",
        "path": "p/macro-regimes-and-your-portfolio",
        "blurb": "Rates, inflation, and growth cycles.",
    },
    "risk_management": {
        "title": "Risk and position sizing",
        "path": "p/managing-risk-and-position-sizing",
        "blurb": "Probability, impact, and drawdown thinking.",
    },
    "competitive_moat": {
        "title": "Competitive moats and durable advantage",
        "path": "p/competitive-moats-and-durable-advantage",
        "blurb": "How companies defend their economics.",
    },
    "capital_allocation": {
        "title": "Capital allocation and shareholder returns",
        "path": "p/capital-allocation-and-shareholder-returns",
        "blurb": "Capex, buybacks, dividends, and ROIC.",
    },
    "decision_framework": {
        "title": "Building your own decision framework",
        "path": "p/building-an-investment-decision-framework",
        "blurb": "Favors, disfavors, catalysts, and monitoring.",
    },
}

# The report format is FIXED (7 steps per template). So is the article set:
# one explainer topic per section, per report type. This mapping is the
# contract with thinkwithfinance content — publish an article, add its path
# to the index, and every report of that type links that section to it.
_SECTION_TOPICS: dict[str, dict[int, list[str]]] = {
    "comprehensive": {
        1: ["how_to_read"],
        2: ["fundamentals"],
        3: ["competitive_moat"],
        4: ["technical_analysis"],
        5: ["macro"],
        6: ["valuation", "risk_management"],
        7: ["decision_framework"],
    },
    "long_term": {
        1: ["business_model"],
        2: ["fundamentals"],
        3: ["competitive_moat"],
        4: ["capital_allocation", "dividends"],
        5: ["risk_management"],
        6: ["valuation"],
        7: ["decision_framework"],
    },
    "tactical": {
        1: ["how_to_read"],
        2: ["technical_analysis"],
        3: ["macro"],
        4: ["fundamentals"],
        5: ["risk_management"],
        6: ["valuation"],
        7: ["decision_framework"],
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


def section_topics(report_type: str, step_number: int, is_etf: bool = False) -> list[str]:
    """Fixed topic keys for a report section (the report format is fixed, so the
    article set per section is fixed too). ETF subjects get etf_101 on step 1."""
    defaults = _SECTION_TOPICS.get(report_type, _SECTION_TOPICS["comprehensive"])
    topics = list(defaults.get(step_number, []))
    if is_etf and step_number == 1 and "etf_101" not in topics:
        topics.append("etf_101")
    return topics


def section_crossref_links(
    report_type: str,
    step_number: int,
    is_etf: bool = False,
    index: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Article links for a single report section (empty until content ships)."""
    index = index if index is not None else _CROSSREF_DEFAULT
    links: list[dict[str, str]] = []
    for key in section_topics(report_type, step_number, is_etf):
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


def render_section_link(
    report_type: str,
    step_number: int,
    is_etf: bool = False,
    index: dict[str, dict[str, str]] | None = None,
) -> str:
    """Inline markdown hyperlink(s) for a report section. Empty string when no
    article for the section exists yet — the link simply doesn't appear."""
    links = section_crossref_links(report_type, step_number, is_etf, index)
    if not links:
        return ""
    lines = [""]
    for link in links:
        lines.append(
            f"*Learn more — [{link['title']}]({link['url']}) "
            f"(thinkwithfinance)*"
        )
    lines.append("")
    return "\n".join(lines)


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
