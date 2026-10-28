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

"""Stooq EOD price tests (price cascade step 3, owner directive 2026-10-15).

Fixtures are REAL recorded Stooq responses:
  - stooq_aapl_us_head.csv / stooq_aapl_us_split_window.csv: contiguous
    excerpts of the actual CSV Stooq served for s=AAPL.US&i=d, from a
    2025-02-15 capture of the endpoint (retrieved via the Wayback
    Machine — sandbox and production egress to stooq.com are refused
    today, see below).
  - stooq_verify_challenge.html: the proof-of-work verification page
    recorded live from stooq.com on 2026-10-14.
  - stooq_access_denied.txt: the download endpoint's recorded reply
    on 2026-10-14 — "Access denied" even after the verification is
    completed, which is precisely why a refusal must degrade to
    missing data with disclosure, never to a silent fallback.
Offline only: transport is mocked with the recorded payloads.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

import research_analyst.providers.nasdaq as nasdaq_module
import research_analyst.providers.stooq as stooq_module
from research_analyst.orchestrator import _source_records
from research_analyst.providers.market_data import MarketDataProvider, _DiskCache
from research_analyst.providers.stooq import (
    StooqProvider,
    parse_challenge,
    parse_daily_csv,
    solve_challenge,
    stooq_symbol,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


# ---------------------------------------------------------------------------
# Symbol mapping — verified mappings only; everything else stays missing
# ---------------------------------------------------------------------------


def test_symbol_mapping_us():
    assert stooq_symbol("AAPL") == "aapl.us"
    assert stooq_symbol("MSFT") == "msft.us"
    assert stooq_symbol("aapl") == "aapl.us"


def test_symbol_mapping_unmapped_markets_stay_missing():
    # No live-verified Stooq mapping exists for these markets yet, so
    # the symbol is None — the price stays missing, never guessed.
    assert stooq_symbol("RY.TO") is None
    assert stooq_symbol("VOD.L") is None
    assert stooq_symbol("SAP.DE") is None
    assert stooq_symbol("7203.T") is None


# ---------------------------------------------------------------------------
# CSV parsing on recorded responses
# ---------------------------------------------------------------------------


def test_parse_recorded_head_fixture():
    bars = parse_daily_csv(_load("stooq_aapl_us_head.csv"))
    assert len(bars) == 12
    assert bars[-1].date == date(2025, 2, 14)
    assert bars[-1].close == 244.6
    assert bars[0].date == date(2025, 1, 30)


def test_parse_split_window_shows_split_and_dividend_adjustment():
    bars = parse_daily_csv(_load("stooq_aapl_us_split_window.csv"))
    by_date = {b.date: b for b in bars}
    pre = by_date[date(2020, 8, 28)]  # last close before the 4:1 split
    post = by_date[date(2020, 8, 31)]  # split day
    assert pre.close == pytest.approx(121.967)
    assert post.close == pytest.approx(126.106)
    # No 4x discontinuity across the split -> split-adjusted. And the
    # pre-split close sits BELOW the split-only value (actual 499.23 /
    # 4 = 124.81) -> dividends are back-adjusted too.
    assert pre.close < 499.23 / 4


def test_parse_non_csv_bodies_yield_no_data():
    assert parse_daily_csv(_load("stooq_access_denied.txt")) == []
    assert parse_daily_csv(_load("stooq_verify_challenge.html")) == []
    assert parse_daily_csv("") == []


# ---------------------------------------------------------------------------
# Browser verification (proof-of-work) — recorded challenge page
# ---------------------------------------------------------------------------


def test_challenge_parse_and_solve_recorded_page():
    parsed = parse_challenge(_load("stooq_verify_challenge.html"))
    assert parsed is not None
    challenge, difficulty = parsed
    assert challenge.startswith("AAAAAGrP0qep")
    assert difficulty == 4
    n = solve_challenge(challenge, difficulty)
    assert n is not None
    digest = hashlib.sha256((challenge + str(n)).encode()).hexdigest()
    assert digest.startswith("0" * difficulty)


def test_challenge_absent_on_csv():
    assert parse_challenge(_load("stooq_aapl_us_head.csv")) is None


# ---------------------------------------------------------------------------
# Provider facade over mocked transport
# ---------------------------------------------------------------------------


async def test_provider_history_from_recorded_csv():
    with patch.object(
        stooq_module, "_download_csv_text", return_value=_load("stooq_aapl_us_head.csv")
    ):
        history = await StooqProvider().get_daily_history("AAPL")
    assert history is not None
    assert history.symbol == "aapl.us"
    assert history.latest is not None
    assert history.latest.date == date(2025, 2, 14)
    assert history.latest.close == 244.6


async def test_provider_refused_download_is_missing_not_error():
    with patch.object(
        stooq_module, "_download_csv_text", return_value=_load("stooq_access_denied.txt")
    ):
        assert await StooqProvider().get_daily_history("AAPL") is None


async def test_provider_unmapped_market_never_fetches():
    with patch.object(stooq_module, "_download_csv_text") as dl:
        assert await StooqProvider().get_daily_history("RY.TO") is None
        dl.assert_not_called()


# ---------------------------------------------------------------------------
# MarketDataProvider — Stooq serves production; NO silent yfinance fallback
# ---------------------------------------------------------------------------


def _provider(tmp_path: Path) -> MarketDataProvider:
    provider = MarketDataProvider()
    provider._cache = _DiskCache(tmp_path, ttl_seconds=3600)
    return provider


async def test_price_series_served_by_stooq(tmp_path):
    provider = _provider(tmp_path)
    with (
        patch.object(nasdaq_module, "_fetch_history_json", return_value=None),
        patch.object(
            stooq_module, "_download_csv_text", return_value=_load("stooq_aapl_us_head.csv")
        ),
    ):
        series = await provider.get_price_series("AAPL", period="max")
    assert series.data_source == "stooq"
    assert len(series.data) == 12
    assert series.period_end == date(2025, 2, 14)  # price_as_of source
    assert series.current_price == pytest.approx(244.6)
    # Stooq ships one adjusted series: adj_close equals close.
    assert series.data[-1].adj_close == series.data[-1].close == pytest.approx(244.6)


async def test_price_series_period_trim(tmp_path):
    provider = _provider(tmp_path)
    with (
        patch.object(nasdaq_module, "_fetch_history_json", return_value=None),
        patch.object(
            stooq_module, "_download_csv_text", return_value=_load("stooq_aapl_us_head.csv")
        ),
    ):
        series = await provider.get_price_series("AAPL", period="5d")
    assert series.data_source == "stooq"
    assert 0 < len(series.data) < 12
    assert series.period_end == date(2025, 2, 14)


# ---------------------------------------------------------------------------
# Report declaration — the Stooq label carries a stooq.com link
# ---------------------------------------------------------------------------


def test_stooq_label_gets_stooq_link():
    records = _source_records("AAPL", ["Stooq (price data — free end-of-day)"])
    assert len(records) == 1
    assert records[0].url == "https://stooq.com"
