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

"""Educational Context Layer (Phase 4).

Bridges "here are the numbers" -> "here is how to apply them". Deterministic,
single-source educational commentary injected into reports — the same
regulatory-shield positioning as the existing disclaimer, extended with an
explicit "educational framework" statement.

Components:
  * METRIC_CONTEXT  — per-metric "what it means / what risk it indicates"
  * context_block() — renders a compact, stylized context note
  * PLAYBOOKS      — reusable evaluation walkthrough templates
  * render_playbook() — injects a structured walkthrough section
  * EDUCATIONAL_NOTE + DISCLAIMER_VERSION bump — extended disclaimer language
"""
# Module: research_analyst/education.py | Version: 1.0 | Updated: 2026-09-02

from __future__ import annotations

from typing import Any

EDUCATIONAL_NOTE = (
    "This report applies an educational evaluation framework. Each metric is "
    "explained in context so you can understand how analysts interpret it; "
    "none of it is a recommendation or a forecast."
)

DISCLAIMER_VERSION = "2"
DISCLAIMER_EDUCATIONAL = (
    "Research Analyst is an educational tool. Its reports apply established "
    "evaluation frameworks to public market data so readers can understand "
    "how professional analysts reason about a company. Everything produced is "
    "for educational and informational purposes only — not investment, "
    "financial, tax, or legal advice, and not a recommendation or solicitation "
    "to buy or sell any security. Data comes from third-party sources and may "
    "be delayed or inaccurate; past performance does not guarantee future "
    "results. Do your own research and consult a licensed professional before "
    "making any decision."
)

# ---------------------------------------------------------------------------
# Metric context registry
# ---------------------------------------------------------------------------

METRIC_CONTEXT: dict[str, dict[str, str]] = {
    "pe_ratio": {
        "means": "Price per $1 of trailing earnings — how much the market pays for each dollar of profit.",  # noqa: E501
        "risk": "A high P/E can signal expected growth OR an overpriced, low-quality earnings base; a low P/E can signal a bargain OR deteriorating fundamentals.",  # noqa: E501
    },
    "peg_ratio": {
        "means": "P/E divided by earnings growth — prices in growth, so a PEG near 1 is often read as 'fairly valued for its growth'.",  # noqa: E501
        "risk": "PEG relies on a growth estimate; if that estimate is wrong, the whole reading shifts.",  # noqa: E501
    },
    "debt_to_equity": {
        "means": "Total liabilities relative to shareholders' equity — how much of the balance sheet is financed by borrowing.",  # noqa: E501
        "risk": "High leverage magnifies both returns and losses; a downturn can strain debt service.",  # noqa: E501
    },
    "roe": {
        "means": "Net income as a percentage of equity — how efficiently the company turns shareholder capital into profit.",  # noqa: E501
        "risk": "High ROE can come from high leverage rather than operating strength — check the composition.",  # noqa: E501
    },
    "gross_margin": {
        "means": "Gross profit as a share of revenue — the markup over direct cost of goods.",
        "risk": "Falling gross margin can signal pricing pressure, rising input costs, or a weaker mix.",  # noqa: E501
    },
    "operating_margin": {
        "means": "Operating profit as a share of revenue — profitability before financing and taxes.",  # noqa: E501
        "risk": "Compression here often precedes a full-blown earnings miss.",
    },
    "net_margin": {
        "means": "Net income as a share of revenue — the bottom line after everything.",
        "risk": "One-time items can distort it; compare to operating margin to spot noise.",
    },
    "free_cash_flow": {
        "means": "Cash left after capital spending — the cash the company can actually return or reinvest.",  # noqa: E501
        "risk": "Negative or volatile FCF can mean growth is consuming cash faster than it is produced.",  # noqa: E501
    },
    "current_yield": {
        "means": "Annual dividend per share as a percentage of price — the cash income you receive.",  # noqa: E501
        "risk": "A very high yield can be a signal the market doubts the dividend's sustainability.",  # noqa: E501
    },
    "payout_ratio": {
        "means": "Dividends as a share of earnings — how much profit is returned rather than reinvested.",  # noqa: E501
        "risk": "A payout above 100% is usually unsustainable unless backed by strong cash flow.",
    },
    "expense_ratio": {
        "means": "The annual fund fee as a percentage of assets — it directly reduces an ETF's return.",  # noqa: E501
        "risk": "Even small fee differences compound materially over a long holding period.",
    },
    "aum": {
        "means": "Assets under management — a scale proxy for an ETF's liquidity and tracking quality.",  # noqa: E501
        "risk": "Very small AUM can mean wider spreads and higher tracking error.",
    },
    "beta": {
        "means": "How much the stock moves relative to the market (market = 1.0).",
        "risk": "Beta above 1 amplifies both gains and losses in market swings.",
    },
}


def context_block(metric: str, value_label: str | None = None) -> str:
    """A compact 'what it means / what it indicates' note for a metric.

    Emitted as plain markdown so it renders in BOTH the web renderer (mdToHTML)
    and the raw Markdown export — no HTML that could be escaped or leaked.
    """
    entry = METRIC_CONTEXT.get(metric)
    if not entry:
        return ""
    head = f"*Why this metric matters: {entry['means']}*"
    risk = f"*What it can indicate: {entry['risk']}*"
    if value_label:
        return f"_{value_label}._\n\n{head}\n\n{risk}\n\n"
    return f"{head}\n\n{risk}\n\n"


# ---------------------------------------------------------------------------
# Playbook templates (reusable evaluation walkthroughs)
# ---------------------------------------------------------------------------

PLAYBOOKS: dict[str, dict[str, Any]] = {
    "balance_sheet_health": {
        "title": "Playbook — Reading Balance Sheet Health",
        "suitability": "Mid/large caps with debt; first screen before valuation.",
        "steps": [
            "1. **Liquidity first.** Check current ratio / quick ratio — can the firm cover near-term obligations without new borrowing?",  # noqa: E501
            "2. **Leverage.** Debt-to-equity and net-debt-to-EBITDA. Compare to the sector: capital-heavy sectors run higher leverage by design.",  # noqa: E501
            "3. **Coverage.** Interest coverage (EBIT / interest) above ~3x is a common comfort line; below that, stress the downside.",  # noqa: E501
            "4. **Cash conversion.** Free cash flow should trend with earnings — divergence is an earnings-quality warning.",  # noqa: E501
            "5. **Trajectory.** Are ratios improving, stable, or deteriorating over 3-5 years? The trend matters more than the snapshot.",  # noqa: E501
        ],
        "close": "Work through steps 1-5 before forming a view. Each step is a question, not a verdict.",  # noqa: E501
    },
    "cash_flow_quality": {
        "title": "Playbook — Earnings Quality via Cash Flow",
        "suitability": "Any company where reported earnings look strong.",
        "steps": [
            "1. **Reconcile.** Compare net income to operating cash flow over several years.",
            "2. **Working capital.** Persistent inventory or receivables growth eating cash is a red flag.",  # noqa: E501
            "3. **Capex.** Distinguish maintenance capex (needed to stay flat) from growth capex.",
            "4. **Owner earnings.** Roughly operating cash flow minus maintenance capex — the cash owners could take out.",  # noqa: E501
            "5. **Cross-check.** If earnings grow but owner earnings don't, the 'growth' may be accounting-driven.",  # noqa: E501
        ],
        "close": "Quality-of-earnings is a gate: if cash doesn't back the profit, discount the headline number.",  # noqa: E501
    },
    "valuation_sanity": {
        "title": "Playbook — Stress-Testing a Valuation",
        "suitability": "After any scenario range; validate assumptions before relying on them.",
        "steps": [
            "1. **Sensitivity.** Change growth and margin by +/-2 points — how wide does the value swing?",  # noqa: E501
            "2. **Compare to history.** Is today's multiple high/low relative to the company's own 5-10 year band?",  # noqa: E501
            "3. **Peer cross-check.** How does the multiple compare to closest competitors with similar growth?",  # noqa: E501
            "4. **Walk backward.** What growth rate is implied by the current price? Is that rate plausible?",  # noqa: E501
            "5. **Margin of safety.** Only act on a view when the price is well inside your comfort vs your base case.",  # noqa: E501
        ],
        "close": "A valuation is a range of scenarios, not a single number. The margin of safety is your protection.",  # noqa: E501
    },
}


def render_playbook(key: str) -> str:
    """A reusable walkthrough section for the given playbook key."""
    pb = PLAYBOOKS.get(key)
    if not pb:
        return ""
    lines = [f"### {pb['title']}", ""]
    if pb.get("suitability"):
        lines.append(f"*Best for: {pb['suitability']}*")
        lines.append("")
    lines.extend(pb["steps"])
    lines.append("")
    if pb.get("close"):
        lines.append(f"> {pb['close']}")
    lines.append("")
    return "\n".join(lines)
