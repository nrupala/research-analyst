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

"""EDINET provider (Japan filings, wire-the-unwired matrix §7).

Golden values are Toyota's REAL FY2026 consolidated IFRS figures from
its annual securities report on EDINET (docID S100Y8NY, period ended
2026-03-31, filed 2026-06-10). The fixture is that filing's actual
XBRL instance, trimmed to the mapped concepts. Cross-check: the
balance sheet balances to the yen (assets == liabilities + equity).
"""
# Module: tests/test_edinet.py

import asyncio
import io
import json
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from research_analyst.config import settings
from research_analyst.providers import edinet
from research_analyst.providers.edinet import (
    EDINETProvider,
    find_report,
    parse_instance,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "edinet_toyota_asr_trimmed.xbrl"
)


@pytest.fixture(scope="module")
def toyota_statements():
    return parse_instance(FIXTURE.read_bytes())


def test_toyota_golden_current_year(toyota_statements):
    assert len(toyota_statements) == 2
    s = toyota_statements[0]
    assert s.period == "FY2026"
    assert s.period_end_date == date(2026, 3, 31)
    assert s.revenue == Decimal("50684952000000")
    assert s.cost_of_revenue == Decimal("39141418000000")
    # No gross-profit subtotal is tagged in Toyota's IFRS statement;
    # it is derived as revenue - cost of sales.
    assert s.gross_profit == Decimal("11543534000000")
    assert s.sga_expense == Decimal("4697524000000")
    assert s.operating_income == Decimal("3766216000000")
    assert s.ebit == Decimal("3766216000000")
    assert s.tax_expense == Decimal("1167234000000")
    assert s.net_income == Decimal("3848098000000")  # attributable
    assert s.total_assets == Decimal("105522331000000")
    assert s.current_assets == Decimal("42824081000000")
    assert s.cash_and_equivalents == Decimal("12659622000000")
    assert s.ppe_net == Decimal("17067365000000")
    assert s.total_liabilities == Decimal("64502263000000")
    assert s.current_liabilities == Decimal("33605019000000")
    assert s.total_equity == Decimal("41020068000000")
    # Balance identity in the real filing.
    assert s.total_assets == s.total_liabilities + s.total_equity
    # Interest-bearing liabilities (current + non-current), less cash.
    assert s.total_debt == Decimal("43205469000000")
    assert s.net_debt == Decimal("30545847000000")
    assert s.operating_cash_flow == Decimal("5472920000000")
    assert s.eps_basic == 295.25
    # Issued shares less treasury shares, from the filing itself.
    assert s.shares_outstanding == 13009058960
    assert s.gross_margin == pytest.approx(
        float(Decimal("11543534000000") / Decimal("50684952000000"))
    )


def test_toyota_prior_year(toyota_statements):
    s = toyota_statements[1]
    assert s.period == "FY2025"
    assert s.period_end_date == date(2025, 3, 31)
    assert s.total_assets == Decimal("93601350000000")
    assert s.sga_expense == Decimal("4782452000000")
    assert s.ppe_net == Decimal("15333693000000")


def _entry(doc_id, doc_type, period_end, submitted, sec="72030"):
    return {
        "docID": doc_id,
        "secCode": sec,
        "docTypeCode": doc_type,
        "periodEnd": period_end,
        "submitDateTime": submitted,
    }


def test_find_report_rules():
    filings = [
        _entry("S100OLD", "120", "2025-03-31", "2025-06-09 15:00"),
        _entry("S100NEW", "120", "2026-03-31", "2026-06-10 15:33"),
        _entry("S100FIX", "130", "2026-03-31", "2026-07-02 09:00"),
        _entry("S100Q", "140", "2026-06-30", "2026-08-07 15:00"),
        _entry("S999999", "120", "2026-03-31", "2026-06-20 15:00", sec="67580"),
    ]
    # The correction (130) of the newest period wins; the quarterly
    # report (140) and other filers are invisible to the search.
    assert find_report(filings, "7203")["docID"] == "S100FIX"
    assert find_report(filings, "6758")["docID"] == "S999999"
    assert find_report(filings, "9999") is None
    assert find_report([], "7203") is None


def test_dormant_without_key(monkeypatch, tmp_path):
    monkeypatch.setattr(settings.market, "edinet_api_key", "")

    async def run():
        async with EDINETProvider(cache_dir=tmp_path) as provider:
            return await provider.get_financials("7203.T")

    assert asyncio.run(run()) == []


def test_non_japanese_ticker_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(settings.market, "edinet_api_key", "test-key")

    async def run():
        async with EDINETProvider(cache_dir=tmp_path) as provider:
            return await provider.get_financials("AAPL")

    assert asyncio.run(run()) == []


class _FakeResponse:
    def __init__(self, payload=None, content=b""):
        self.status_code = 200
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


class _FakeClient:
    """Serves the document list + filing ZIP without any network."""

    def __init__(self, zip_bytes: bytes):
        self._zip_bytes = zip_bytes
        self.list_calls = 0

    async def get(self, url, params=None, headers=None):
        if url.endswith("/documents.json"):
            self.list_calls += 1
            day = (params or {}).get("date")
            results = []
            if day == "2026-06-10":
                results = [
                    _entry("S100Y8NY", "120", "2026-03-31", "2026-06-10 15:33")
                ]
            return _FakeResponse(
                payload={"metadata": {"status": "200"}, "results": results}
            )
        if url.endswith("/documents/S100Y8NY"):
            return _FakeResponse(content=self._zip_bytes)
        raise AssertionError(f"unexpected URL {url}")

    async def aclose(self):
        return None


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "XBRL/PublicDoc/jpcrp030000-asr-001_E02144-000_2026-03-31_01_2026-06-10.xbrl",
            FIXTURE.read_bytes(),
        )
    return buf.getvalue()


def test_end_to_end_and_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(settings.market, "edinet_api_key", "test-key")
    fake = _FakeClient(_zip_bytes())
    provider = EDINETProvider(cache_dir=tmp_path)

    async def run():
        provider._client = fake  # bypass __aenter__'s real client
        return await provider.get_financials("7203.T")

    statements = asyncio.run(run())
    assert len(statements) == 2
    assert statements[0].revenue == Decimal("50684952000000")
    assert fake.list_calls > 0
    cache_file = tmp_path / "7203.json"
    assert cache_file.exists()
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload["doc_id"] == "S100Y8NY"

    # A fresh provider serves the same statements from cache alone.
    provider2 = EDINETProvider(cache_dir=tmp_path)
    assert provider2._read_cache("7203")[0].net_income == Decimal("3848098000000")
    # An expired cache reads as a miss.
    payload["fetched_on"] = (date.today() - timedelta(days=31)).isoformat()
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    assert provider2._read_cache("7203") is None
    assert edinet._MAX_SCAN_DAYS >= 365
