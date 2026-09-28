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

"""Small null-safe guards shared by every quant_engine module.

The engine's contract: nulls in, nulls out — never throw on data gaps.
Ported from quant/src/guards.ts.
"""
# Module: research_analyst/quant_engine/guards.py | Version: 0.1.0 | Updated: 2026-09-28

from __future__ import annotations

import math

from .series import Series


def _defined_value(v: float | None) -> bool:
    return v is not None and math.isfinite(v)


def defined(values: Series) -> list[float]:
    """Non-null, finite values of a series, in order."""
    return [v for v in values if _defined_value(v)]


def last_value(values: Series) -> float | None:
    """Last non-null value, or None when the series is empty."""
    for v in reversed(values):
        if _defined_value(v):
            return v
    return None


def first_value(values: Series) -> float | None:
    """First non-null value, or None when the series is empty."""
    for v in values:
        if _defined_value(v):
            return v
    return None


def div_series(num: Series, den: Series) -> Series:
    """Element-wise division; None wherever either side is missing or divisor is 0.

    Output length is the longer of the two inputs (missing positions stay
    None), mirroring the TS ``?? null`` out-of-range handling.
    """
    n = max(len(num), len(den))
    out: Series = [None] * n
    for i in range(n):
        a = num[i] if i < len(num) else None
        b = den[i] if i < len(den) else None
        out[i] = a / b if a is not None and b is not None and b != 0 else None
    return out


def div(a: float | None, b: float | None) -> float | None:
    """Safe division of two scalars."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def mean(values: Series) -> float | None:
    """Arithmetic mean of non-null values; None when empty."""
    d = defined(values)
    if not d:
        return None
    return sum(d) / len(d)