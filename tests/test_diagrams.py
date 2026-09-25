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

"""Tests for the D2 diagram layer (Phase F-B).

* D2 source generators are deterministic and carry the right edges/labels.
* render_diagram degrades to a readable styled fallback when the d2 binary is
  absent (dev/CI) — never a blank gap.
"""
# Module: tests/test_diagrams.py | Version: 1.0 | Updated: 2026-08-31

from __future__ import annotations

from unittest.mock import patch

from research_analyst.reports import diagrams
from research_analyst.reports.visuals import VisualEngine


def test_d2_business_model_source():
    src = diagrams.d2_business_model("AAPL", ["Hardware", "Services"])
    assert "AAPL" in src
    assert "Hardware" in src and "Services" in src
    assert "->" in src


def test_d2_capital_allocation_source():
    src = diagrams.d2_capital_allocation("AAPL", 0.30, 0.50, 0.15)
    assert "Free Cash Flow" in src
    assert "30% of FCF" in src and "50% of FCF" in src and "15% of FCF" in src


def test_d2_decision_framework_source():
    src = diagrams.d2_decision_framework(
        "AAPL", ["Revenue growth", "Strong margins"], ["Valuation rich"], ["Earnings"]
    )
    assert 'decision: "AAPL' in src
    assert "favors: Revenue growth" in src and "disfavors: Valuation rich" in src
    assert "catalyst: Earnings" in src
    # plain edges only — no connector expressions (valid D2)
    assert "-> decision" in src


def test_render_fallback_when_d2_absent():
    """No d2 binary in this environment -> readable pre fallback, never blank."""
    src = diagrams.d2_business_model("AAPL")
    with patch.object(diagrams.shutil, "which", return_value=None):
        rendered = diagrams.render_diagram(src)
    assert rendered.startswith('<pre class="diagram-fallback">')


def test_diagram_visual_emits_svg_type():
    from research_analyst.enums import SecurityType
    from research_analyst.models import CompanyProfile

    vis = VisualEngine.d2_business_model(CompanyProfile(
        ticker="AAPL", name="Apple", sector="T", industry="I",
        currency="USD", security_type=SecurityType.EQUITY, description="",
    ))
    assert vis.visual_type == "svg"
    assert "<pre" in vis.content or "<svg" in vis.content
    assert "Business Model Overview" in vis.title
