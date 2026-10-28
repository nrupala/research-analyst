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

"""EDINET — Japan Financial Services Agency disclosure system, the
FIRST source for Japanese listed companies' financial statements
(wire-the-unwired, matrix §7).

Data: the EDINET API v2 (api.edinet-fsa.go.jp). A free subscription
key is required (held in the Secure Vault since 2026-10-14; the
provider arms when RA_MARKET_EDINET_API_KEY is placed in the
environment — without a key it is dormant and returns nothing).
Filings are consumed for analysis and cited as EDINET + document ID
+ filing date; the filings themselves are never redistributed.

Resolution: EDINET filings carry the TSE securities code (secCode,
the 4-character listing code + a check digit), so a .T ticker maps
directly — no name matching. The provider scans the daily document
lists backwards for the filer's newest annual securities report
(docTypeCode 120, or its correction 130), downloads the filing ZIP,
and parses the plain XBRL instance inside (XBRL/PublicDoc/*.xbrl).

XBRL model (verified on Toyota's FY2026 report, docID S100Y8NY):
contexts WITHOUT dimension members are the consolidated statements
(non-consolidated and segment views carry members). Duration
contexts give the income/cash-flow year, instant contexts the
balance-sheet date; the instance carries the current and prior year
side by side. IFRS filers use IFRS-suffixed concepts (Revenue is
TotalNetRevenuesIFRS, equity is EquityIFRS); Japanese-GAAP filers
use the plain names (NetSales, OperatingIncome, NetAssets). Values
are literal JPY (the decimals attribute is precision, not scale).

Scope v1: ANNUAL statements (current + prior year from the newest
report). Quarterly reports are a named fast-follow.
"""
# Module: research_analyst/providers/edinet.py | Version: 0.1.0 | Updated: 2026-10-16

from __future__ import annotations

import asyncio
import io
import json
import logging
import zipfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
from lxml import etree

from ..config import settings
from ..models import FinancialStatement

logger = logging.getLogger(__name__)

_USER_AGENT = "ResearchAnalyst/0.1 (nrupalakolkar@gmail.com)"
# Annual securities report + its correction.
_REPORT_DOC_TYPES = frozenset({"120", "130"})
_MAX_SCAN_DAYS = 400
_SCAN_CHUNK_DAYS = 7
_CACHE_TTL_DAYS = 30


def _dec(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(raw.strip())
    except (InvalidOperation, ValueError):
        return None


def _margin(part: Decimal | None, whole: Decimal | None) -> float | None:
    if part is None or whole in (None, 0):
        return None
    return float(part) / float(whole)


def _abs(value: Decimal | None) -> Decimal | None:
    """Expense magnitudes are stored positive (fleet convention)."""
    return abs(value) if value is not None else None


# ----------------------------------------------------------------------
# Concept maps — ordered candidates per model field. IFRS-suffixed
# names first, then the Japanese-GAAP plain names. Summary-of-business
# -results concepts are the fallback pass (they duplicate the
# statements for headline figures and span more years).
# ----------------------------------------------------------------------

_FLOW_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "TotalNetRevenuesIFRS", "SalesRevenuesIFRS", "RevenueIFRS",
        "NetSales", "GrossOperatingRevenue", "OperatingRevenues",
    ),
    "cost_of_revenue": ("CostOfSalesIFRS", "CostOfSales"),
    "gross_profit": ("GrossProfitIFRS", "GrossProfit"),
    "sga_expense": (
        "SellingGeneralAndAdministrativeExpensesIFRS",
        "SellingGeneralAndAdministrativeExpenses",
    ),
    "operating_income": ("OperatingProfitLossIFRS", "OperatingIncome"),
    "interest_expense": (
        "InterestExpensesIFRS", "InterestExpenses", "InterestExpense",
    ),
    "tax_expense": ("IncomeTaxExpenseIFRS", "IncomeTaxExpense", "IncomeTaxes"),
    "net_income": (
        "ProfitLossAttributableToOwnersOfParentIFRS",
        "ProfitLossAttributableToOwnersOfParent",
        "ProfitLossIFRS", "ProfitLoss",
    ),
    "operating_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivitiesIFRS",
        "NetCashProvidedByUsedInOperatingActivities",
    ),
}

_STOCK_CONCEPTS: dict[str, tuple[str, ...]] = {
    "total_assets": ("AssetsIFRS", "TotalAssets"),
    "current_assets": ("CurrentAssetsIFRS", "TotalCurrentAssets", "CurrentAssets"),
    "cash_and_equivalents": (
        "CashAndCashEquivalentsIFRS", "CashAndCashEquivalents", "CashAndDeposits",
    ),
    "ppe_net": ("PropertyPlantAndEquipmentIFRS", "PropertyPlantAndEquipment"),
    "current_liabilities": (
        "TotalCurrentLiabilitiesIFRS", "CurrentLiabilities",
    ),
    "noncurrent_liabilities": (
        "TotalNonCurrentLiabilitiesIFRS", "NonCurrentLiabilities",
    ),
    "total_liabilities": ("LiabilitiesIFRS", "TotalLiabilities"),
    "total_equity": ("EquityIFRS", "TotalEquityIFRS", "NetAssets"),
    "debt_current": ("InterestBearingLiabilitiesCLIFRS",),
    "debt_noncurrent": ("InterestBearingLiabilitiesNCLIFRS",),
}

_SUMMARY_SUFFIX = "SummaryOfBusinessResults"
_SUMMARY_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "NetSales" + _SUMMARY_SUFFIX, "RevenueIFRS" + _SUMMARY_SUFFIX,
        "TotalNetRevenuesIFRS" + _SUMMARY_SUFFIX,
    ),
    "total_assets": (
        "TotalAssetsIFRS" + _SUMMARY_SUFFIX, "TotalAssets" + _SUMMARY_SUFFIX,
    ),
    "total_equity": ("NetAssets" + _SUMMARY_SUFFIX,),
    "cash_and_equivalents": (
        "CashAndCashEquivalentsIFRS" + _SUMMARY_SUFFIX,
        "CashAndCashEquivalents" + _SUMMARY_SUFFIX,
    ),
    "net_income": (
        "ProfitLossAttributableToOwnersOfParentIFRS" + _SUMMARY_SUFFIX,
        "ProfitLossAttributableToOwnersOfParent" + _SUMMARY_SUFFIX,
    ),
}

_EPS_CONCEPTS = (
    "BasicEarningsLossPerShareIFRS", "BasicAndDilutedEarningsLossPerShareIFRS",
    "NetIncomePerShare", "BasicEarningsLossPerShare", "EarningsPerShare",
)
_EPS_SUMMARY_CONCEPTS = (
    "BasicEarningsLossPerShareIFRS" + _SUMMARY_SUFFIX,
    "BasicEarningsLossPerShare" + _SUMMARY_SUFFIX,
)
_EPS_DILUTED_CONCEPTS = (
    "DilutedEarningsLossPerShareIFRS",
    "DilutedEarningsLossPerShareIFRS" + _SUMMARY_SUFFIX,
    "DilutedEarningsPerShare" + _SUMMARY_SUFFIX,
)
_ISSUED_SHARE_CONCEPTS = (
    "TotalNumberOfIssuedShares" + _SUMMARY_SUFFIX,
    "NumberOfSharesIssuedSharesVotingRights",
)
_TREASURY_SHARE_CONCEPTS = (
    "NumberOfSharesHeldInOwnNameTreasurySharesEtc",
    "TotalNumberOfSharesHeldTreasurySharesEtc",
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


class _Context:
    __slots__ = ("kind", "start", "end", "has_member")

    def __init__(self, kind: str, start: date | None, end: date, has_member: bool):
        self.kind = kind
        self.start = start
        self.end = end
        self.has_member = has_member


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


def _contexts(root: etree._Element) -> dict[str, _Context]:
    out: dict[str, _Context] = {}
    for el in root.iter():
        if _local(el.tag) != "context":
            continue
        cid = el.get("id")
        if not cid:
            continue
        has_member = any(_local(k.tag) == "explicitMember" for k in el.iter())
        instant = start = end = None
        for k in el.iter():
            name = _local(k.tag)
            if name == "instant":
                instant = _parse_date(k.text)
            elif name == "startDate":
                start = _parse_date(k.text)
            elif name == "endDate":
                end = _parse_date(k.text)
        if instant is not None:
            out[cid] = _Context("instant", None, instant, has_member)
        elif start is not None and end is not None:
            out[cid] = _Context("duration", start, end, has_member)
    return out


def _facts(root: etree._Element) -> dict[tuple[str, str], tuple[Decimal, str]]:
    """(concept, contextRef) -> (value, unitRef) for numeric facts."""
    out: dict[tuple[str, str], tuple[Decimal, str]] = {}
    for el in root.iter():
        ctx = el.get("contextRef")
        if not ctx or el.text is None:
            continue
        value = _dec(el.text)
        if value is None:
            continue
        out[(_local(el.tag), ctx)] = (value, el.get("unitRef") or "")
    return out


def _pick(
    facts: dict[tuple[str, str], tuple[Decimal, str]],
    concepts: tuple[str, ...],
    ctx_ids: frozenset[str],
    units: set[str] | frozenset[str] | None = None,
) -> Decimal | None:
    for name in concepts:
        for (concept, ctx), (value, unit) in facts.items():
            if concept == name and ctx in ctx_ids and (units is None or unit in units):
                return value
    return None


def parse_instance(xml_bytes: bytes) -> list[FinancialStatement]:
    """Parse an EDINET XBRL instance into annual statements.

    Returns the two statement years the report carries (current,
    then prior), newest first. Consolidated (member-free) contexts
    only. Missing line items stay None — never guessed.
    """
    root = etree.fromstring(xml_bytes)
    contexts = _contexts(root)
    facts = _facts(root)

    # Segment-free duration periods, newest first; statements exist
    # for the two newest (older contexts carry summary facts only).
    durations = sorted(
        {c.end for c in contexts.values() if c.kind == "duration" and not c.has_member},
        reverse=True,
    )
    statements: list[FinancialStatement] = []
    for period_end in durations[:2]:
        flow_ctx = frozenset(
            cid for cid, c in contexts.items()
            if c.kind == "duration" and c.end == period_end and not c.has_member
        )
        stock_ctx = frozenset(
            cid for cid, c in contexts.items()
            if c.kind == "instant" and c.end == period_end and not c.has_member
        )
        if not flow_ctx or not stock_ctx:
            continue

        def flow(field: str) -> Decimal | None:
            value = _pick(facts, _FLOW_CONCEPTS[field], flow_ctx, {"JPY"})
            if value is None and field in _SUMMARY_CONCEPTS:
                value = _pick(facts, _SUMMARY_CONCEPTS[field], flow_ctx, {"JPY"})
            return value

        def stock(field: str) -> Decimal | None:
            value = _pick(facts, _STOCK_CONCEPTS[field], stock_ctx, {"JPY"})
            if value is None and field in _SUMMARY_CONCEPTS:
                value = _pick(facts, _SUMMARY_CONCEPTS[field], stock_ctx, {"JPY"})
            return value

        revenue = flow("revenue")
        cost = _abs(flow("cost_of_revenue"))
        gross = flow("gross_profit")
        if gross is None and revenue is not None and cost is not None:
            gross = revenue - cost
        operating = flow("operating_income")
        # Financial institutions (banks/insurers) file ordinary income,
        # not operating income: their 3.x-equivalent has no EBIT line.
        if operating is None and _pick(
            facts, ("OrdinaryIncome",), flow_ctx, {"JPY"}
        ) is not None:
            operating = None
        net = flow("net_income")
        total_assets = stock("total_assets")
        total_liabilities = stock("total_liabilities")
        current_liabilities = stock("current_liabilities")
        noncurrent = stock("noncurrent_liabilities")
        if (
            noncurrent is None
            and total_liabilities is not None
            and current_liabilities is not None
        ):
            noncurrent = total_liabilities - current_liabilities
        cash = stock("cash_and_equivalents")
        debt_cur, debt_non = stock("debt_current"), stock("debt_noncurrent")
        total_debt = (
            debt_cur + debt_non
            if debt_cur is not None and debt_non is not None
            else None
        )
        eps = _pick(facts, _EPS_CONCEPTS, flow_ctx, {"JPYPerShares"})
        if eps is None:
            eps = _pick(facts, _EPS_SUMMARY_CONCEPTS, flow_ctx, {"JPYPerShares"})
        eps_diluted = _pick(facts, _EPS_DILUTED_CONCEPTS, flow_ctx, {"JPYPerShares"})
        issued = _pick(facts, _ISSUED_SHARE_CONCEPTS, stock_ctx, {"shares"})
        treasury = _pick(facts, _TREASURY_SHARE_CONCEPTS, stock_ctx, {"shares"})
        shares = None
        if issued is not None:
            shares = int(issued - treasury) if treasury is not None else int(issued)

        statements.append(
            FinancialStatement(
                period=f"FY{period_end.year}",
                period_end_date=period_end,
                is_annual=True,
                revenue=revenue,
                cost_of_revenue=cost,
                gross_profit=gross,
                operating_income=operating,
                ebit=operating,
                net_income=net,
                interest_expense=_abs(flow("interest_expense")),
                tax_expense=_abs(flow("tax_expense")),
                sga_expense=_abs(flow("sga_expense")),
                eps_basic=float(eps) if eps is not None else None,
                eps_diluted=float(eps_diluted) if eps_diluted is not None else None,
                shares_outstanding=shares,
                gross_margin=_margin(gross, revenue),
                operating_margin=_margin(operating, revenue),
                net_margin=_margin(net, revenue),
                total_assets=total_assets,
                current_assets=stock("current_assets"),
                cash_and_equivalents=cash,
                ppe_net=stock("ppe_net"),
                total_liabilities=total_liabilities,
                current_liabilities=current_liabilities,
                total_equity=stock("total_equity"),
                total_debt=total_debt,
                net_debt=(
                    total_debt - cash
                    if total_debt is not None and cash is not None
                    else None
                ),
                operating_cash_flow=flow("operating_cash_flow"),
            )
        )
    return statements


def find_report(filings: list[dict[str, Any]], sec_code4: str) -> dict[str, Any] | None:
    """Newest annual securities report for a 4-character TSE code.

    ``filings`` are EDINET document-list entries. Corrections (130)
    supersede the original (120) for the same period; across periods
    the latest period end wins.
    """
    matches = [
        f for f in filings
        if str(f.get("secCode") or "")[:4] == sec_code4
        and str(f.get("docTypeCode") or "") in _REPORT_DOC_TYPES
        and f.get("docID")
    ]
    if not matches:
        return None

    def rank(f: dict[str, Any]) -> tuple[str, str]:
        return (str(f.get("periodEnd") or ""), str(f.get("submitDateTime") or ""))

    return max(matches, key=rank)


class EDINETProvider:
    """Async EDINET filings provider (key-gated, disk-cached)."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or (settings.market.cache_dir.parent / "edinet")
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> EDINETProvider:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=15.0),
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            # Fleet idiom: environment proxies must never reroute
            # (or break) provider traffic.
            trust_env=False,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_financials(
        self, ticker: str, periods: int = 5
    ) -> list[FinancialStatement]:
        """Annual statements for a Japanese (.T) listing, or [].

        Dormant without an API key: EDINET requires a subscription
        key, and there is no honest keyless route.
        """
        api_key = settings.market.edinet_api_key.strip()
        if not api_key:
            return []
        symbol = ticker.upper().strip()
        if not symbol.endswith(".T"):
            return []
        code = symbol[:-2]
        if len(code) != 4:
            return []
        cached = self._read_cache(code)
        if cached is not None:
            return cached[:periods]
        report = await self._find_latest_report(code, api_key)
        if report is None:
            return []
        xml = await self._download_instance(str(report["docID"]), api_key)
        if xml is None:
            return []
        try:
            statements = parse_instance(xml)
        except Exception as e:
            logger.debug("EDINET instance parse failed for %s: %s", ticker, e)
            return []
        if statements:
            self._write_cache(code, str(report["docID"]), statements)
        return statements[:periods]

    # ------------------------------------------------------------------
    # API access
    # ------------------------------------------------------------------

    async def _documents_for(self, day: date, api_key: str) -> list[dict[str, Any]]:
        assert self._client is not None
        try:
            resp = await self._client.get(
                f"{settings.market.edinet_base_url}/documents.json",
                params={"date": day.isoformat(), "type": "2"},
                headers={"Ocp-Apim-Subscription-Key": api_key},
            )
            if resp.status_code != 200:
                return []
            payload = resp.json()
        except Exception:
            return []
        if str(payload.get("metadata", {}).get("status")) != "200":
            return []
        results = payload.get("results")
        return results if isinstance(results, list) else []

    async def _find_latest_report(
        self, code: str, api_key: str
    ) -> dict[str, Any] | None:
        today = date.today()
        for offset in range(0, _MAX_SCAN_DAYS, _SCAN_CHUNK_DAYS):
            days = [today - timedelta(days=offset + i) for i in range(_SCAN_CHUNK_DAYS)]
            payloads = await asyncio.gather(
                *(self._documents_for(d, api_key) for d in days)
            )
            filings = [f for batch in payloads for f in batch]
            report = find_report(filings, code)
            if report is not None:
                return report
        return None

    async def _download_instance(self, doc_id: str, api_key: str) -> bytes | None:
        assert self._client is not None
        try:
            resp = await self._client.get(
                f"{settings.market.edinet_base_url}/documents/{doc_id}",
                params={"type": "1"},
                headers={"Ocp-Apim-Subscription-Key": api_key},
            )
            if resp.status_code != 200:
                return None
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                members = [
                    n for n in zf.namelist()
                    if n.startswith("XBRL/PublicDoc/") and n.endswith(".xbrl")
                ]
                if not members:
                    return None
                return zf.read(members[0])
        except Exception as e:
            logger.debug("EDINET download failed for %s: %s", doc_id, e)
            return None

    # ------------------------------------------------------------------
    # Cache — parsed statements per securities code (annual filings;
    # a 30-day TTL bounds the rescan cost to once a month per filer).
    # ------------------------------------------------------------------

    def _cache_path(self, code: str) -> Path:
        return self._cache_dir / f"{code}.json"

    def _read_cache(self, code: str) -> list[FinancialStatement] | None:
        path = self._cache_path(code)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched = date.fromisoformat(payload["fetched_on"])
            if (date.today() - fetched).days > _CACHE_TTL_DAYS:
                return None
            return [FinancialStatement(**s) for s in payload["statements"]]
        except Exception:
            return None

    def _write_cache(
        self, code: str, doc_id: str, statements: list[FinancialStatement]
    ) -> None:
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "doc_id": doc_id,
                "fetched_on": date.today().isoformat(),
                "statements": [s.model_dump(mode="json") for s in statements],
            }
            self._cache_path(code).write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.debug("EDINET cache write failed for %s: %s", code, e)
