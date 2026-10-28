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

"""Tests for Step 7 Decision Framework enrichment and Business Model Overview.

Covers: thesis tilt thresholds, catalyst grouping, framework narrative text,
thesis-balance and unit-economics SVG charts, catalyst watchlist D2 source,
and graceful handling of missing data.
"""

from __future__ import annotations

import pytest

from research_analyst.reports import diagrams, svg_charts
from research_analyst.reports.renderer import ReportRenderer

# ---------------------------------------------------------------------------
# Thesis tilt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "favor,disfavor,expected",
    [
        (5, 2, "positive"),
        (2, 0, "positive"),
        (4, 4, "mixed"),
        (3, 2, "mixed"),
        (1, 3, "negative"),
        (0, 2, "negative"),
        (0, 0, "mixed"),
    ],
)
def test_thesis_tilt_thresholds(favor, disfavor, expected):
    assert ReportRenderer._thesis_tilt(favor, disfavor) == expected


# ---------------------------------------------------------------------------
# Catalyst grouping
# ---------------------------------------------------------------------------


def test_group_catalysts_splits_near_term_and_structural():
    catalysts = [
        "Upcoming earnings report and guidance update.",
        "Macro regime shift (rate cuts, fiscal stimulus).",
        "Competitive dynamics (M&A, new product launch, market share shift).",
    ]
    near, structural = ReportRenderer._group_catalysts(catalysts)
    assert near == ["Upcoming earnings report and guidance update."]
    assert structural == [
        "Macro regime shift (rate cuts, fiscal stimulus).",
        "Competitive dynamics (M&A, new product launch, market share shift).",
    ]


def test_group_catalysts_empty():
    assert ReportRenderer._group_catalysts([]) == ([], [])


# ---------------------------------------------------------------------------
# Catalyst watchlist D2
# ---------------------------------------------------------------------------


def test_d2_catalyst_watchlist_structure():
    src = diagrams.d2_catalyst_watchlist(
        "META", ["Earnings report"], ["Macro shift", "M&A"]
    )
    assert "META" in src
    assert "near-term catalysts" in src
    assert "structural catalysts" in src
    assert "Earnings report" in src
    assert "Macro shift" in src


def test_d2_catalyst_watchlist_escapes_quotes():
    src = diagrams.d2_catalyst_watchlist("T", ['Say "hi" catalyst'], [])
    assert '"hi"' not in src  # quotes escaped so D2 stays valid


def test_d2_catalyst_watchlist_empty_groups():
    src = diagrams.d2_catalyst_watchlist("T", [], [])
    assert "watch" in src


# ---------------------------------------------------------------------------
# Thesis balance chart
# ---------------------------------------------------------------------------


def test_svg_thesis_balance_returns_visual():
    visual = svg_charts.svg_thesis_balance("META", 5, 2, "positive")
    assert visual.visual_type == "svg"
    assert "<svg" in visual.content
    assert "META" in visual.title
    assert visual.interactive["tilt"] == "positive"
    assert visual.interactive["favor"] == 5
    assert visual.interactive["disfavor"] == 2


def test_svg_thesis_balance_zero_counts():
    visual = svg_charts.svg_thesis_balance("T", 0, 0, "mixed")
    assert "<svg" in visual.content


# ---------------------------------------------------------------------------
# Unit economics chart
# ---------------------------------------------------------------------------


def test_svg_unit_economics_returns_visual():
    visual = svg_charts.svg_unit_economics(
        "META",
        {
            "Gross margin": 0.81,
            "Operating margin": 0.42,
            "Net margin": None,
            "FCF margin": 0.31,
        },
    )
    assert visual is not None
    assert visual.visual_type == "svg"
    assert "<svg" in visual.content
    assert "Gross margin" in visual.interactive["margins"]
    assert "Net margin" not in visual.interactive["margins"]  # None skipped


def test_svg_unit_economics_none_when_no_data():
    assert (
        svg_charts.svg_unit_economics("T", {"Gross margin": None}) is None
    )


def test_svg_unit_economics_handles_negative_margin():
    visual = svg_charts.svg_unit_economics(
        "T", {"Net margin": -0.05, "Gross margin": 0.60}
    )
    assert visual is not None
    assert "<svg" in visual.content
