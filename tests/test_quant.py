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

"""Tests for the centralized basis-point / percentage-point arithmetic (#68).

Known-value tests: a fraction of 0.02 is 200 bps (not 2), guarding against
the 100x unit error previously present at call sites.
"""
# Module: tests/test_quant.py | Version: 0.1.0 | Updated: 2026-09-25

from __future__ import annotations

import pytest

from research_analyst.quant import (
    fmt_bps,
    fmt_pct,
    fmt_pp,
    from_bps,
    from_percent,
    pp_spread,
    spread_bps,
    to_bps,
    to_percent,
)


def test_to_bps_known_values():
    assert to_bps(0.02) == pytest.approx(200.0)
    assert to_bps(0.0025) == pytest.approx(25.0)
    assert to_bps(0.0) == 0.0
    assert to_bps(-0.01) == pytest.approx(-100.0)


def test_from_bps_round_trip():
    assert from_bps(200.0) == pytest.approx(0.02)
    assert from_bps(to_bps(0.0123)) == pytest.approx(0.0123)


def test_to_from_percent():
    assert to_percent(0.0123) == pytest.approx(1.23)
    assert from_percent(1.23) == pytest.approx(0.0123)


def test_pp_spread():
    # 1.50% vs 1.25% -> 0.25 percentage points
    assert pp_spread(0.0150, 0.0125) == pytest.approx(0.25)
    assert pp_spread(0.0125, 0.0150) == pytest.approx(-0.25)


def test_spread_bps():
    # 1.50% vs 1.25% -> 25 bps
    assert spread_bps(0.0150, 0.0125) == pytest.approx(25.0)


def test_fmt_bps_guards_100x_error():
    # The historical bug: spread * 100 labelled "bps" printed "2 bps"
    # for a 200bp spread. The centralized formatter must print 200 bps.
    assert fmt_bps(0.02) == "200 bps"
    assert fmt_bps(0.0025) == "25 bps"
    assert fmt_bps(-0.01) == "-100 bps"


def test_fmt_pct_and_pp():
    assert fmt_pct(0.0123) == "1.23%"
    assert fmt_pp(0.0025) == "0.25 pp"
