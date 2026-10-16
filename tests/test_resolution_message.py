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

"""Unresolvable-ticker error wording (release-gate Low, 2026-10-15).

An international symbol that no longer resolves (e.g. TATAMOTORS.NS,
renamed in a demerger) used to surface SEC EDGAR's US-only format
check — "must be 1-5 uppercase letters" — as the explanation. The
400 was substantively right and the wording wrong: the symbol's
format is valid, the listing is gone. The orchestrator now composes
the message from the facts and keeps the inner error in the log.
"""
# Module: tests/test_resolution_message.py

import asyncio

import pytest

from research_analyst import orchestrator as orchestrator_module
from research_analyst.models import ResearchRequest
from research_analyst.orchestrator import ResearchOrchestrator


class _FakeSEC:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def get_company_profile(self, ticker):
        # The real SEC validator's wording for a dotted symbol.
        raise ValueError(
            f"Invalid ticker '{ticker}': must be 1-5 uppercase letters."
        )


def test_unresolvable_international_ticker_message(monkeypatch):
    orch = ResearchOrchestrator()

    async def _no_listing(ticker):
        raise RuntimeError("no listing found")

    monkeypatch.setattr(orch._market, "get_company_profile", _no_listing)
    monkeypatch.setattr(
        orchestrator_module, "SECEdgarProvider", lambda *a, **k: _FakeSEC()
    )

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(orch.run(ResearchRequest(ticker="TATAMOTORS.NS")))

    message = str(excinfo.value)
    assert "Cannot resolve ticker 'TATAMOTORS.NS'" in message
    assert "1-5 uppercase" not in message
    assert "exchange suffix" in message
