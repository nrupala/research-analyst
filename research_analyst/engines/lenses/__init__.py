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

"""Mental-model lens registry (Phase 5).

Runs every registered lens over the same typed LensInput and returns typed
LensResults. Adding a lens = drop a module in this package + register it here.
"""
# Module: research_analyst/engines/lenses/__init__.py | Version: 1.1 | Updated: 2026-09-02

from __future__ import annotations

from collections.abc import Callable

from . import buffett, dalio, damodaran, graham, greenblatt, lynch, marks
from .base import ATTRIBUTION, LensInput, LensResult, LensSignal

LENSES: dict[str, Callable[[LensInput], LensResult]] = {
    "graham": graham.run,
    "greenblatt": greenblatt.run,
    "lynch": lynch.run,
    "damodaran": damodaran.run,
    "buffett": buffett.run,
    "dalio": dalio.run,
    "marks": marks.run,
}

LENS_ORDER = ["graham", "greenblatt", "lynch", "damodaran", "buffett", "dalio", "marks"]


def run_all(data: LensInput) -> list[LensResult]:
    """Run every registered lens over the input. Never raises: a failing lens
    yields an empty educational LensResult with the gap noted."""
    results: list[LensResult] = []
    for key in LENS_ORDER:
        fn = LENSES.get(key)
        if fn is None:
            continue
        try:
            result = fn(data)
        except Exception as e:  # lens isolation: one bad lens must not kill the report
            result = LensResult(
                lens=key,
                name=key.capitalize(),
                summary="Lens could not be computed for this security.",
                signals=[LensSignal(
                    label="Computation", value="error", read="neutral",
                    note=f"{type(e).__name__}: {e}"[:200],
                )],
                attribution=ATTRIBUTION.format(name=key.capitalize()),
            )
        results.append(result)
    return results


__all__ = ["ATTRIBUTION", "LensInput", "LensResult", "LensSignal", "LENSES", "run_all"]
