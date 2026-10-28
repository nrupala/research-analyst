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

"""Peer-set determinism regression tests (issue #67).

Offline, deterministic. Synthetic fixtures only — no network, no yfinance.

Pins the #67 acceptance criterion: two runs for the same ticker on the same
data vintage produce the identical peer set in the identical order, and any
peer that fails enrichment is surfaced in provenance (never silently dropped).
"""
# Module: tests/test_peer_determinism.py | Version: 1.0.0

from unittest.mock import AsyncMock, patch

from research_analyst.enums import SecurityType
from research_analyst.models import CompanyProfile
from research_analyst.providers import market_data as md
from research_analyst.providers.market_data import (
    PEER_MAP_VERSION,
    MarketDataProvider,
    peer_map_hash,
)

# Synthetic market caps with deliberate ties (AMD/CSCO, INTC/QCOM).
_CAPS = {
    "MSFT": 3.0e12,
    "NVDA": 2.5e12,
    "AVGO": 1.0e12,
    "ORCL": 5.0e11,
    "CRM": 3.0e11,
    "ADBE": 2.5e11,
    "AMD": 2.0e11,
    "CSCO": 2.0e11,
    "ACN": 1.8e11,
    "INTC": 1.5e11,
    "QCOM": 1.5e11,
    "TXN": 1.4e11,
    "IBM": 1.3e11,
    "NOW": 1.2e11,
    "INTU": 1.1e11,
    "AMAT": 1.0e11,
    "LRCX": 9.0e10,
    "MU": 8.0e10,
    "ADI": 7.0e10,
}

_FAILING = {"ORCL"}  # simulated enrichment failure, like the #67 report


class _FakeYF:
    """Stands in for yfinance.Ticker — .info only, no network."""

    def __init__(self, ticker: str):
        self._ticker = ticker

    @property
    def info(self) -> dict:
        if self._ticker in _FAILING:
            raise RuntimeError("simulated enrichment failure")
        return {
            "totalRevenue": 1.0e11,
            "grossMargins": 0.60,
            "trailingPE": 25.0,
            "debtToEquity": 50.0,
        }


def _provider(caps: dict | None = None) -> MarketDataProvider:
    """Provider with network seams stubbed — fully offline."""
    caps = _CAPS if caps is None else caps
    prov = MarketDataProvider.__new__(MarketDataProvider)

    async def fake_profile(ticker: str) -> CompanyProfile:
        return CompanyProfile(
            ticker=ticker,
            name=f"{ticker} Inc",
            sector="Technology",
            security_type=SecurityType.EQUITY,
            market_cap=caps.get(ticker),
        )

    async def fake_yf(ticker: str) -> _FakeYF:
        return _FakeYF(ticker)

    prov.get_company_profile = fake_profile  # type: ignore[method-assign]
    prov._yf_ticker = fake_yf  # type: ignore[method-assign]
    return prov


async def _run(prov: MarketDataProvider, max_peers: int = 8):
    # Retry backoff must not sleep in tests.
    with patch.object(md.asyncio, "sleep", new=AsyncMock()):
        return await MarketDataProvider.get_sector_peers_with_provenance(prov, "AAPL", max_peers)


async def test_two_runs_same_data_vintage_produce_identical_peer_set():
    """#67 acceptance: same inputs twice -> identical peer set AND order."""
    peers1, _ = await _run(_provider())
    peers2, _ = await _run(_provider())
    tickers1 = [p.ticker for p in peers1]
    tickers2 = [p.ticker for p in peers2]
    assert tickers1 == tickers2
    assert len(tickers1) == 8
    # The failing peer is excluded both times, identically.
    assert "ORCL" not in tickers1


async def test_market_cap_tie_breaks_deterministically_by_ticker():
    """Equal/unknown market caps order by ticker — never by sort stability."""
    peers, _ = await _run(_provider(caps={}))
    tickers = [p.ticker for p in peers]
    assert tickers == sorted(tickers), f"tie order must be alphabetical, got {tickers}"


async def test_failed_peer_is_surfaced_not_silently_dropped():
    """#67: a peer that fails enrichment lands in missing_tickers, loudly."""
    peers, provenance = await _run(_provider())
    assert "ORCL" not in [p.ticker for p in peers]
    assert "ORCL" in provenance.missing_tickers
    note = provenance.coverage_note
    assert "Missing expected peers" in note
    assert "ORCL" in note


async def test_provenance_carries_versioned_map_identity():
    """Every run logs which peer-map version/hash it used."""
    _, provenance = await _run(_provider())
    assert provenance.map_version == PEER_MAP_VERSION
    assert provenance.map_hash == peer_map_hash()
    assert len(provenance.expected_tickers) > 0
    assert set(provenance.resolved_tickers) | set(provenance.missing_tickers) <= set(
        provenance.expected_tickers
    )
