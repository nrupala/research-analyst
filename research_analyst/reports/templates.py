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

"""Report templates — exact 7-step structures for each report mode.

Non-negotiable rules (from spec):
  - Use the exact 7-Step template
  - Preserve section titles verbatim
  - Never reorder, merge, rename, or skip steps
  - Output Markdown only
  - Never blend content across report types

Each template defines the step number, title, and rendering instructions
for the report renderer.
"""
# Module: research_analyst/reports/templates.py | Version: 0.1.0 | Updated: 2026-05-15

from __future__ import annotations

from dataclasses import dataclass, field

from ..enums import ReportType


@dataclass
class StepTemplate:
    """Definition of a single report step."""

    step_number: int
    title: str
    description: str
    required_data: list[str] = field(default_factory=list)
    visual_requirement: str = ""  # What visual should appear in this step
    key_questions: list[str] = field(default_factory=list)


@dataclass
class ReportTemplate:
    """Complete 7-step template for a report mode."""

    report_type: ReportType
    title_format: str  # e.g., "{ticker} — Long-Term Research Report"
    steps: list[StepTemplate]
    description: str = ""


# ---------------------------------------------------------------------------
# Long-Term 7-Step Research Report
# ---------------------------------------------------------------------------

LONG_TERM_TEMPLATE = ReportTemplate(
    report_type=ReportType.LONG_TERM,
    title_format="{ticker} — Long-Term 7-Step Research Report",
    description=(
        "Deep, structural, timeless analysis. Focuses on business model durability, "
        "competitive moat, capital allocation, and multi-year value creation trajectory."
    ),
    steps=[
        StepTemplate(
            step_number=1,
            title="Business Overview & Structural Position",
            description=(
                "What the company does, how it makes money, and where it sits in the "
                "industry value chain. Structural competitive advantages and disadvantages."
            ),
            required_data=["profile", "fundamental"],
            visual_requirement="Mermaid business model flow or revenue segmentation table",
            key_questions=[
                "What is the core business model?",
                "What are the key revenue drivers?",
                "Where does the company sit in the value chain?",
                "What structural advantages exist?",
            ],
        ),
        StepTemplate(
            step_number=2,
            title="Financial Analysis & Quality of Earnings",
            description=(
                "Multi-year financial trajectory: growth, margins, returns, and balance sheet. "
                "Earnings quality assessment using accrual ratios and FCF conversion."
            ),
            required_data=["fundamental", "financials"],
            visual_requirement="Plotly revenue/margin trend chart or financial summary table",
            key_questions=[
                "What is the revenue growth trajectory?",
                "Are margins expanding or contracting?",
                "Is earnings quality high (cash > accruals)?",
                "Is the balance sheet healthy?",
            ],
        ),
        StepTemplate(
            step_number=3,
            title="Competitive Landscape & Moat Assessment",
            description=(
                "Peer comparison on key metrics. Competitive advantages, disadvantages, "
                "and moat durability assessment."
            ),
            required_data=["competitive"],
            visual_requirement="Peer comparison table with metric rankings",
            key_questions=[
                "Who are the key competitors?",
                "Where does the company rank on profitability, growth, valuation?",
                "What competitive moat indicators exist?",
                "What are the competitive risks?",
            ],
        ),
        StepTemplate(
            step_number=4,
            title="Capital Allocation & Shareholder Returns",
            description=(
                "How does management deploy capital? Capex, M&A, buybacks, dividends. "
                "ROIC vs WACC analysis. Marginal return on investment."
            ),
            required_data=["fundamental", "capital_allocation"],
            visual_requirement="Capital allocation breakdown chart or Mermaid flow",
            key_questions=[
                "Is ROIC above WACC (value creation)?",
                "How does the company allocate FCF?",
                "What is the shareholder yield?",
                "Is capital allocation improving or deteriorating?",
            ],
        ),
        StepTemplate(
            step_number=5,
            title="Risk Assessment",
            description=(
                "Structured risk map: Probability x Impact x Timing. "
                "Near-term vs long-term, operational vs macro vs regulatory. "
                "Transitory vs structural classification."
            ),
            required_data=["risk_matrix"],
            visual_requirement="Risk matrix table (Probability x Impact)",
            key_questions=[
                "What are the top 3 risks by severity?",
                "Which risks are structural vs transitory?",
                "What monitoring triggers should be watched?",
                "What are the second-order effects?",
            ],
        ),
        StepTemplate(
            step_number=6,
            title="Scenario-Based Valuation Range",
            description=(
                "Bull / Base / Bear scenarios with explicit operating and valuation assumptions. "
                "Mandatory ASCII chart. Variant perception vs consensus."
            ),
            required_data=["valuation"],
            visual_requirement="Mandatory ASCII scenario chart + Plotly scenario waterfall",
            key_questions=[
                "What assumptions drive each scenario?",
                "What is the implied price range?",
                "How does our view differ from consensus?",
                "What would change our base case?",
            ],
        ),
        StepTemplate(
            step_number=7,
            title="Long-Term Thesis & Decision Framework",
            description=(
                "Synthesize all analysis into a clear thesis. Frame as favors / disfavors, "
                "never buy / sell / hold. Identify catalysts and monitoring triggers."
            ),
            required_data=["all"],
            visual_requirement="Thesis summary table or Mermaid decision tree",
            key_questions=[
                "What factors favor the long-term thesis?",
                "What factors disfavor it?",
                "What catalysts could change the trajectory?",
                "What should be monitored going forward?",
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Tactical Near-Term 7-Step Research Report
# ---------------------------------------------------------------------------

TACTICAL_TEMPLATE = ReportTemplate(
    report_type=ReportType.TACTICAL,
    title_format="{ticker} — Tactical Near-Term 7-Step Research Report",
    description=(
        "Short-horizon, market-driven insights. Focuses on near-term catalysts, "
        "technical setup, event risk, and tactical positioning context."
    ),
    steps=[
        StepTemplate(
            step_number=1,
            title="Current Setup & Near-Term Context",
            description=(
                "Where the stock is now: price action, recent catalysts, "
                "upcoming events, and market sentiment."
            ),
            required_data=["profile", "prices", "technical"],
            visual_requirement="Price chart annotation or key levels table",
            key_questions=[
                "What has driven recent price action?",
                "What events are upcoming (earnings, ex-div, conferences)?",
                "What is current market sentiment?",
            ],
        ),
        StepTemplate(
            step_number=2,
            title="Technical Analysis & Price Structure",
            description=(
                "Technical regime, key indicators, support/resistance, "
                "patterns, and momentum signals."
            ),
            required_data=["technical"],
            visual_requirement="Plotly technical indicator chart or signal summary table",
            key_questions=[
                "What is the technical regime (bullish/bearish/neutral)?",
                "Where are key support and resistance levels?",
                "What patterns are detected?",
                "Is momentum accelerating or decelerating?",
            ],
        ),
        StepTemplate(
            step_number=3,
            title="Macro & Sector Context",
            description=(
                "How the current macro environment and sector dynamics "
                "affect the near-term outlook for this security."
            ),
            required_data=["macro"],
            visual_requirement="Macro regime summary table",
            key_questions=[
                "Is the macro environment a tailwind or headwind?",
                "What sector rotation dynamics are in play?",
                "How do rates and inflation affect the near-term setup?",
            ],
        ),
        StepTemplate(
            step_number=4,
            title="Near-Term Fundamental Catalysts",
            description=(
                "Earnings expectations, guidance trajectory, insider activity, "
                "institutional positioning changes."
            ),
            required_data=["fundamental", "estimates"],
            visual_requirement="Earnings estimate revision table or insider activity chart",
            key_questions=[
                "What are consensus earnings expectations?",
                "Are estimates being revised up or down?",
                "What does insider activity signal?",
                "Are institutional holders adding or trimming?",
            ],
        ),
        StepTemplate(
            step_number=5,
            title="Near-Term Risk Map",
            description=(
                "Risks with < 6 month horizon. Event risk, earnings risk, "
                "liquidity risk, gap risk."
            ),
            required_data=["risk_matrix"],
            visual_requirement="Near-term risk matrix (Probability x Impact)",
            key_questions=[
                "What events could cause a gap move?",
                "What is the earnings miss/beat probability?",
                "Is there a liquidity or positioning overhang?",
            ],
        ),
        StepTemplate(
            step_number=6,
            title="Scenario-Based Valuation Range",
            description=(
                "Near-term Bull / Base / Bear with emphasis on multiple expansion/contraction "
                "and earnings revisions rather than long-term DCF."
            ),
            required_data=["valuation"],
            visual_requirement="Mandatory ASCII scenario chart + near-term sensitivity table",
            key_questions=[
                "What drives the near-term price range?",
                "What multiples are implied at each scenario?",
                "What earnings revision would change the picture?",
            ],
        ),
        StepTemplate(
            step_number=7,
            title="Tactical Assessment & Positioning Context",
            description=(
                "Synthesize near-term signals. Frame as favors / disfavors for "
                "tactical positioning. Identify trigger points and invalidation levels."
            ),
            required_data=["all"],
            visual_requirement="Signal dashboard table or decision matrix",
            key_questions=[
                "What favors a near-term constructive view?",
                "What disfavors it?",
                "What price level invalidates the thesis?",
                "What catalyst would accelerate the move?",
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Comprehensive 7-Step Research Report (Hybrid)
# ---------------------------------------------------------------------------

COMPREHENSIVE_TEMPLATE = ReportTemplate(
    report_type=ReportType.COMPREHENSIVE,
    title_format="{ticker} — Comprehensive 7-Step Research Report",
    description=(
        "Integrated long-term structural analysis + tactical near-term positioning. "
        "The default report mode for all requests."
    ),
    steps=[
        StepTemplate(
            step_number=1,
            title="Executive Summary & Investment Context",
            description=(
                "High-level overview: what the company does, where it trades, "
                "current setup, and why it matters now. Combines structural and tactical framing."
            ),
            required_data=["profile", "prices", "fundamental"],
            visual_requirement="Key metrics summary table",
            key_questions=[
                "What is the investment case in 3 sentences?",
                "What makes this analysis timely?",
                "What are the key metrics an investor needs to see immediately?",
            ],
        ),
        StepTemplate(
            step_number=2,
            title="Fundamental Analysis & Financial Trajectory",
            description=(
                "Growth, profitability, balance sheet, earnings quality, and capital allocation. "
                "Combines historical trend with forward estimates."
            ),
            required_data=["fundamental", "financials", "capital_allocation"],
            visual_requirement="Plotly financial trend chart + margin table",
            key_questions=[
                "What is the financial growth trajectory?",
                "Are margins and returns improving?",
                "Is the balance sheet adequate for the strategy?",
                "How is management allocating capital?",
            ],
        ),
        StepTemplate(
            step_number=3,
            title="Competitive Position & Market Structure",
            description=(
                "Peer comparison, competitive advantages/disadvantages, moat indicators, "
                "and market share dynamics."
            ),
            required_data=["competitive"],
            visual_requirement="Peer comparison table + competitive positioning chart",
            key_questions=[
                "How does the company rank vs peers?",
                "What competitive moat indicators exist?",
                "What are the structural competitive risks?",
            ],
        ),
        StepTemplate(
            step_number=4,
            title="Technical Analysis & Market Structure",
            description=(
                "Price action, trend, momentum, volatility, key levels, and patterns. "
                "Contextualizes the technical picture within the fundamental narrative."
            ),
            required_data=["technical", "prices"],
            visual_requirement="Technical signal summary table or Plotly indicator chart",
            key_questions=[
                "What is the technical regime?",
                "Where are key support/resistance levels?",
                "Does the technical picture confirm or contradict the fundamental thesis?",
            ],
        ),
        StepTemplate(
            step_number=5,
            title="Macro Context & Sector Dynamics",
            description=(
                "How the macro environment and sector-specific dynamics affect both "
                "the structural thesis and near-term positioning."
            ),
            required_data=["macro"],
            visual_requirement="Macro regime table + sector sensitivity summary",
            key_questions=[
                "Is the macro environment favorable or unfavorable?",
                "What sector rotation dynamics matter?",
                "What second-order macro effects should be monitored?",
            ],
        ),
        StepTemplate(
            step_number=6,
            title="Risk Assessment & Scenario-Based Valuation",
            description=(
                "Combined risk matrix (Probability x Impact x Timing) and "
                "Bull / Base / Bear valuation scenarios. Variant perception."
            ),
            required_data=["risk_matrix", "valuation"],
            visual_requirement="Risk matrix + mandatory ASCII scenario chart",
            key_questions=[
                "What are the top risks and their structure?",
                "What are the Bull/Base/Bear price ranges?",
                "How does our view differ from consensus?",
                "What assumptions drive each scenario?",
            ],
        ),
        StepTemplate(
            step_number=7,
            title="Investment Thesis & Decision Framework",
            description=(
                "Integrated thesis: long-term structural view + near-term tactical context. "
                "Favors / disfavors framing. Catalysts, monitoring triggers, invalidation criteria."
            ),
            required_data=["all"],
            visual_requirement="Thesis summary table + Mermaid decision framework",
            key_questions=[
                "What factors favor the investment thesis?",
                "What factors disfavor it?",
                "What catalysts could accelerate or derail the thesis?",
                "What should be monitored going forward?",
                "What would invalidate the thesis?",
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

_TEMPLATES: dict[ReportType, ReportTemplate] = {
    ReportType.LONG_TERM: LONG_TERM_TEMPLATE,
    ReportType.TACTICAL: TACTICAL_TEMPLATE,
    ReportType.COMPREHENSIVE: COMPREHENSIVE_TEMPLATE,
}


def get_template(report_type: ReportType) -> ReportTemplate:
    """Retrieve the exact 7-step template for a report mode.

    Raises:
        KeyError: If report_type is not one of the three supported modes.
    """
    if report_type not in _TEMPLATES:
        raise KeyError(
            f"Unsupported report type '{report_type}'. "
            f"Valid options: {', '.join(t.value for t in ReportType)}"
        )
    return _TEMPLATES[report_type]
