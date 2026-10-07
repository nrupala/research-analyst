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

from research_analyst.models import SymbolMatch
from research_analyst.resolver import resolve_subject


def m(sym, name="", qt="EQUITY", score=1.0):
    return SymbolMatch(symbol=sym, name=name, quote_type=qt, score=score)


def test_explicit_suffix_resolves_without_search():
    r = resolve_subject("reliance.ns", [])
    assert r.status == "resolved" and r.resolved.symbol == "RELIANCE.NS"
    assert r.resolved.market == "IN" and r.resolved.currency == "INR"


def test_exact_symbol_resolves():
    r = resolve_subject(
        "AAPL", [m("AAPL", "Apple Inc.", score=10), m("APLE", "Apple Hospitality REIT", score=1)]
    )
    assert r.status == "resolved" and r.resolved.symbol == "AAPL"


def test_exact_name_resolves():
    r = resolve_subject(
        "Microsoft Corporation",
        [m("MSFT", "Microsoft Corporation", score=9), m("MSF.DE", "Microsoft XETRA", score=3)],
    )
    assert r.status == "resolved" and r.resolved.symbol == "MSFT"


def test_sole_match_resolves():
    r = resolve_subject("someco", [m("SMC", "Some Company PLC", score=5)])
    assert r.status == "resolved" and r.resolved.symbol == "SMC"


def test_dominant_resolves():
    r = resolve_subject(
        "microsoft",
        [m("MSFT", "Microsoft Corporation", score=20), m("XYZ", "Micro Systems", score=1)],
    )
    assert r.status == "resolved" and r.resolved.symbol == "MSFT"


def test_cross_exchange_is_ambiguous():
    r = resolve_subject(
        "reliance industries",
        [
            m("RELIANCE.NS", "Reliance Industries Limited", score=8),
            m("RELIANCE.BO", "Reliance Industries Limited", score=7),
        ],
    )
    assert r.status == "ambiguous"
    assert {c.symbol for c in r.candidates} == {"RELIANCE.NS", "RELIANCE.BO"}


def test_non_equity_filtered_to_not_found():
    r = resolve_subject("usd", [m("USDINR=X", "US Dollar / Rupee", qt="CURRENCY", score=5)])
    assert r.status == "not_found"


def test_no_matches_not_found():
    r = resolve_subject("zzzznotacompany", [])
    assert r.status == "not_found"


def test_etf_eligible():
    r = resolve_subject("INDA", [m("INDA", "iShares MSCI India ETF", qt="ETF", score=9)])
    assert r.status == "resolved" and r.resolved.symbol == "INDA"
