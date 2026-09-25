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

"""Subject resolver -- map a free-text query (ticker or company name) to a listing.

Safe-confirm policy (v0.3.0 Slice A.4): resolve only when confident; otherwise
return candidates for the user to pick. NEVER silently guess a security -- a
fully-correct report on the WRONG listing is the worst outcome for a research
tool. The lookup itself lives in MarketDataProvider.search_symbols; this module
is pure (no I/O) so the disambiguation policy is deterministic and testable.
"""
# Module: research_analyst/resolver.py | Version: 0.3.0 | Slice A.4
from __future__ import annotations

from .models import SubjectResolution, SymbolMatch
from .providers import markets

# Quote types RA can actually research as a subject.
_ELIGIBLE = {"EQUITY", "ETF"}

# India-focused curated alias map: well-known bare names -> canonical NSE listing.
# These are deliberate, user-approved mappings (not a search guess); extend freely.
_INDIA_ALIASES = {
    "ICICI": "ICICIBANK.NS",
    "TECHM": "TECHM.NS",
    "INFY": "INFY.NS",
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "SBIN": "SBIN.NS",
    "WIPRO": "WIPRO.NS",
}


def _tokens(text: str) -> list[str]:
    cleaned = "".join(c.lower() if (c.isalnum() or c.isspace()) else " " for c in (text or ""))
    return cleaned.split()


def _name_has_all(name: str, query: str) -> bool:
    name_tokens = set(_tokens(name))
    q_tokens = _tokens(query)
    return bool(q_tokens) and all(t in name_tokens for t in q_tokens)


def resolve_subject(query: str, matches: list[SymbolMatch]) -> SubjectResolution:
    """Decide resolve-vs-candidates for a query against search matches."""
    q = markets.normalize_ticker(query)  # trimmed + upper-cased

    # 0) India alias: a curated bare name maps to its canonical NSE listing.
    alias = _INDIA_ALIASES.get(q)
    if alias:
        m = markets.resolve(alias)
        return SubjectResolution(
            query=query, status="resolved",
            resolved=SymbolMatch(symbol=alias, market=m.code, market_name=m.name, currency=m.currency),
            note=f"India alias: {q} -> {alias}",
        )

    # 1) Explicit exchange suffix -> the user named the listing. Resolve directly.
    if markets.suffix_of(q):
        m = markets.resolve(q)
        return SubjectResolution(
            query=query, status="resolved",
            resolved=SymbolMatch(symbol=q, market=m.code, market_name=m.name, currency=m.currency),
            note="explicit exchange suffix",
        )

    eligible = [m for m in (matches or []) if (m.quote_type or "").upper() in _ELIGIBLE]
    if not eligible:
        # India-focused fallback: a bare, suffix-less alphanumeric symbol that yfinance
        # could not match is very often an NSE listing typed without ".NS". Suggest it
        # (never silently resolve) so the safe-confirm policy holds.
        if not matches and q.isalnum() and 1 <= len(q) <= 12 and not markets.suffix_of(q):
            ns = f"{q}.NS"
            m = markets.resolve(ns)
            return SubjectResolution(
                query=query, status="ambiguous",
                candidates=[SymbolMatch(symbol=ns, market=m.code, market_name=m.name, currency=m.currency)],
                note=f"did you mean {ns}? (Indian NSE listing)",
            )
        return SubjectResolution(query=query, status="not_found",
                                 note="no equity or ETF listing matched")

    # 2) Exact symbol hit (user typed a bare symbol, e.g. AAPL).
    exact_sym = [m for m in eligible if m.symbol.upper() == q]
    if exact_sym:
        return SubjectResolution(query=query, status="resolved", resolved=exact_sym[0],
                                 note="exact symbol match")

    ranked = sorted(eligible, key=lambda m: m.score, reverse=True)

    # 3) Exact full-name hit.
    exact_name = [m for m in ranked if m.name.strip().lower() == query.strip().lower()]
    if len(exact_name) == 1:
        return SubjectResolution(query=query, status="resolved", resolved=exact_name[0],
                                 note="exact name match")

    # 4) Sole eligible match.
    if len(ranked) == 1:
        return SubjectResolution(query=query, status="resolved", resolved=ranked[0],
                                 note="sole match")

    top, second = ranked[0], ranked[1]
    dominant_score = top.score > 0 and top.score >= 2 * max(second.score, 1e-9)
    dominant_name = _name_has_all(top.name, query) and not _name_has_all(second.name, query)
    if dominant_score and dominant_name:
        return SubjectResolution(query=query, status="resolved", resolved=top,
                                 note="dominant match")

    # 5) Ambiguous -- never guess. Return top candidates for the user to pick.
    return SubjectResolution(query=query, status="ambiguous", candidates=ranked[:5],
                             note="multiple listings match; select one")
