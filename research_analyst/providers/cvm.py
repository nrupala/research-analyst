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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# A separate commercial license is available for uses incompatible with
# the AGPL-3.0. See COMMERCIAL-LICENSE.md.

"""CVM (Comissão de Valores Mobiliários) — Brazil's securities
regulator open-data filings, the FIRST source for Brazilian listed
companies' financial statements (wire-the-unwired, matrix §7 #12).

Data: annual DFP filings published as bulk ZIPs on dados.cvm.gov.br
(keyless; license ODbL per the portal's own dataset record). Each
year's ZIP carries the statement CSVs (DRE income, BPA/BPP balance
sheets, DFC cash flow, capital composition) for every filer, plus a
filing index. Values are in BRL, scaled per ESCALA_MOEDA (MIL =
thousands). A filing carries its own year (ÚLTIMO) and the prior
year restated (PENÚLTIMO); the same period therefore appears in two
ZIPs — the newest filing wins.

Ticker resolution: CVM data carries CNPJ + CD_CVM, never B3 tickers.
A .SA ticker is resolved through the company NAME (from the market
profile) against the CVM register (cad_cia_aberta.csv): normalized
exact match on the legal or commercial name, else a unique
token-subset match. No confident match -> no CVM statements, and
the pipeline falls back to its other sources. Nothing is guessed.

Scope v1: ANNUAL statements from DFP (consolidated preferred,
individual as fallback). Quarterly ITR is a named fast-follow.
"""
# Module: research_analyst/providers/cvm.py | Version: 0.1.0 | Updated: 2026-10-15

from __future__ import annotations

import csv
import io
import json
import logging
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from ..config import settings
from ..models import FinancialStatement

logger = logging.getLogger(__name__)

BASE_URL = "https://dados.cvm.gov.br"
_CADASTRO_PATH = "/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
_DFP_PATH = "/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip"
_CACHE_TTL = timedelta(days=7)
_USER_AGENT = "ResearchAnalyst/0.4 (contact: info@aimlds.org)"

# Statement kinds inside a DFP zip: (income, assets, liabilities,
# cash flow indirect, cash flow direct, capital composition).
_KINDS = ("DRE", "BPA", "BPP", "DFC_MI", "DFC_MD", "composicao_capital")

# CVM standard chart-of-accounts codes (consolidated statements).
_DRE_MAP = {
    "3.01": "revenue",
    "3.03": "gross_profit",
    "3.05": "operating_income",
    "3.11.01": "net_income_attributable",
    "3.11": "net_income",
}
_BPA_MAP = {
    "1": "total_assets",
    "1.01": "current_assets",
    "1.01.01": "cash_and_equivalents",
    "1.02.03": "ppe_net",
}
_BPP_CODES = ("2", "2.01", "2.02", "2.03", "2.01.04", "2.02.01")


@dataclass(frozen=True)
class CadastroEntry:
    cnpj: str
    cd_cvm: str
    legal_name: str
    commercial_name: str


_SUFFIX_TOKENS = {"SA", "S", "A", "LTDA", "CIA", "COMPANHIA"}


def _normalize_name(name: str) -> str:
    """Uppercase, accent-free, punctuation-free company name."""
    decomposed = unicodedata.normalize("NFKD", name.upper())
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^A-Z0-9 ]+", " ", ascii_only)
    return re.sub(r"\s+", " ", cleaned).strip()


def _name_tokens(normalized: str) -> frozenset[str]:
    return frozenset(t for t in normalized.split() if t not in _SUFFIX_TOKENS)


def parse_cadastro(text: str) -> list[CadastroEntry]:
    """Parse cad_cia_aberta.csv (semicolon, latin-1 already decoded)."""
    entries: list[CadastroEntry] = []
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        if (row.get("SIT") or "").strip() != "ATIVO":
            continue
        cnpj = (row.get("CNPJ_CIA") or "").strip()
        cd_cvm = (row.get("CD_CVM") or "").strip()
        if not cnpj or not cd_cvm:
            continue
        entries.append(
            CadastroEntry(
                cnpj=cnpj,
                cd_cvm=cd_cvm,
                legal_name=(row.get("DENOM_SOCIAL") or "").strip(),
                commercial_name=(row.get("DENOM_COMERC") or "").strip(),
            )
        )
    return entries


def resolve_company(
    entries: list[CadastroEntry], company_name: str
) -> CadastroEntry | None:
    """Resolve a market-profile company name to a CVM register entry.

    Exact normalized match on legal or commercial name wins. Else a
    UNIQUE entry whose name tokens contain (or are contained by) the
    profile name's tokens. Anything else — no match or ambiguity —
    returns None: an unresolved ticker gets no CVM data, never a
    guess.
    """
    if not company_name.strip():
        return None
    target = _normalize_name(company_name)
    target_tokens = _name_tokens(target)
    exact: list[CadastroEntry] = []
    subset: list[CadastroEntry] = []
    for entry in entries:
        for candidate in (entry.legal_name, entry.commercial_name):
            normalized = _normalize_name(candidate)
            if normalized == target:
                exact.append(entry)
                break
            tokens = _name_tokens(normalized)
            if tokens and target_tokens and (
                tokens <= target_tokens or target_tokens <= tokens
            ):
                subset.append(entry)
                break
    # The register can carry duplicate rows for one company (same
    # CNPJ/CD_CVM, e.g. Petrobras) — identity is the company code,
    # not the row.
    unique_exact = {e.cd_cvm: e for e in exact}
    if len(unique_exact) == 1:
        return next(iter(unique_exact.values()))
    if len(unique_exact) > 1:
        return None
    unique_subset = {e.cd_cvm: e for e in subset}
    if len(unique_subset) == 1:
        return next(iter(unique_subset.values()))
    return None


def _decimal(raw: str | None, scale: Decimal) -> Decimal | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return Decimal(str(raw).strip()) * scale
    except InvalidOperation:
        return None


def _scale_for(escala: str | None) -> Decimal:
    # ESCALA_MOEDA: "MIL" = values in thousands of BRL; "UNIDADE" = 1.
    return Decimal(1000) if (escala or "").strip().upper() == "MIL" else Decimal(1)


def parse_statement_rows(text: str, cnpj: str) -> list[dict[str, str]]:
    """All rows of one statement CSV belonging to one company."""
    rows: list[dict[str, str]] = []
    for row in csv.DictReader(io.StringIO(text), delimiter=";"):
        if (row.get("CNPJ_CIA") or "").strip() == cnpj:
            rows.append(row)
    return rows


def _period_values(
    rows: list[dict[str, str]], codes: set[str]
) -> dict[str, dict[str, Decimal]]:
    """{period_end: {cd_conta: value}} — newest filing wins per cell.

    Rows carry DT_REFER (the filing's own year-end) and VERSAO; the
    same (period, account) can appear in the filing of its own year
    (ÚLTIMO) and the next year's filing (PENÚLTIMO, restated). The
    greatest (DT_REFER, VERSAO) is the value of record.
    """
    best: dict[tuple[str, str], tuple[tuple[str, int], Decimal]] = {}
    for row in rows:
        code = (row.get("CD_CONTA") or "").strip()
        period_end = (row.get("DT_FIM_EXERC") or "").strip()
        if code not in codes or not period_end:
            continue
        # Account 3.99 is EPS in R$/share — a unit value the
        # statement's money scale (MIL) must never touch.
        scale = Decimal(1) if code == "3.99" else _scale_for(row.get("ESCALA_MOEDA"))
        value = _decimal(row.get("VL_CONTA"), scale)
        if value is None:
            continue
        try:
            version = int(row.get("VERSAO") or 0)
        except ValueError:
            version = 0
        rank = ((row.get("DT_REFER") or ""), version)
        key = (period_end, code)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, value)
    out: dict[str, dict[str, Decimal]] = {}
    for (period_end, code), (_, value) in best.items():
        out.setdefault(period_end, {})[code] = value
    return out


def _neg(value: Decimal | None) -> Decimal | None:
    return -value if value is not None else None


def assemble_statements(
    dre_rows: list[dict[str, str]],
    bpa_rows: list[dict[str, str]],
    bpp_rows: list[dict[str, str]],
    dfc_rows: list[dict[str, str]],
    capital_rows: list[dict[str, str]],
    *,
    max_periods: int = 5,
) -> list[FinancialStatement]:
    """Build FinancialStatements from one company's raw CVM rows."""
    dre = _period_values(
        dre_rows,
        set(_DRE_MAP)
        | {"3.02", "3.04.01", "3.04.02", "3.06", "3.06.02", "3.08",
           "3.09", "3.09.01", "3.99"},
    )
    # Two charts share the DRE file. Industrials: net income at 3.11,
    # tax at 3.08, EBIT at 3.05. Financial institutions: net income
    # at 3.09, tax at 3.06, and 3.05 is PRE-TAX income (never EBIT).
    # The chart is read off the codes the company actually files.
    all_dre_codes = {code for values in dre.values() for code in values}
    financial_chart = "3.09" in all_dre_codes and not (
        {"3.11", "3.11.01"} & all_dre_codes
    )
    bpa = _period_values(bpa_rows, set(_BPA_MAP))
    bpp = _period_values(bpp_rows, set(_BPP_CODES))
    dfc = _period_values(dfc_rows, {"6.01"})

    shares: dict[str, int] = {}
    for row in capital_rows:
        period = (row.get("DT_REFER") or "").strip()
        try:
            issued = int(row.get("QT_ACAO_TOTAL_CAP_INTEGR") or 0)
            treasury = int(row.get("QT_ACAO_TOTAL_TESOURO") or 0)
        except ValueError:
            continue
        if period and issued:
            shares[period] = issued - treasury

    periods = sorted(set(dre) | set(bpa), reverse=True)[:max_periods]
    statements: list[FinancialStatement] = []
    for period_end in periods:
        try:
            end = date.fromisoformat(period_end)
        except ValueError:
            continue
        d_codes = dre.get(period_end, {})
        a_codes = bpa.get(period_end, {})
        d = {f: d_codes[c] for c, f in _DRE_MAP.items() if c in d_codes}
        a = {f: a_codes[c] for c, f in _BPA_MAP.items() if c in a_codes}
        p = bpp.get(period_end, {})
        revenue = d.get("revenue")
        gross = d.get("gross_profit")
        if financial_chart:
            operating = None  # 3.05 is pre-tax income for banks
            net = d_codes.get("3.09.01", d_codes.get("3.09"))
            tax = _neg(d_codes.get("3.06"))
            interest = None
        else:
            operating = d.get("operating_income")
            net = d.get("net_income_attributable", d.get("net_income"))
            tax = _neg(d_codes.get("3.08"))
            interest = d_codes.get("3.06.02")
        sga_parts = [d_codes[c] for c in ("3.04.01", "3.04.02") if c in d_codes]
        sga_total = sum(sga_parts, Decimal(0)) if sga_parts else None
        current_liab = p.get("2.01")
        noncurrent_liab = p.get("2.02")
        total_liabilities = (
            current_liab + noncurrent_liab
            if current_liab is not None and noncurrent_liab is not None
            else None
        )
        debt_parts = [p[c] for c in ("2.01.04", "2.02.01") if c in p]
        total_debt = sum(debt_parts, Decimal(0)) if len(debt_parts) == 2 else None
        cash = a.get("cash_and_equivalents")
        statements.append(
            FinancialStatement(
                period=f"FY{end.year}",
                period_end_date=end,
                is_annual=True,
                revenue=revenue,
                cost_of_revenue=_neg(d_codes.get("3.02")),
                gross_profit=gross,
                operating_income=operating,
                ebit=operating,
                net_income=net,
                interest_expense=_neg(interest) if interest is not None and interest < 0 else None,
                tax_expense=tax,
                sga_expense=_neg(sga_total),
                # A filed 3.99 of exactly 0 is a placeholder row
                # (observed on real industrial filings), not an EPS.
                eps_basic=(
                    float(d_codes["3.99"])
                    if d_codes.get("3.99") not in (None, 0)
                    else None
                ),
                gross_margin=_margin(gross, revenue),
                operating_margin=_margin(operating, revenue),
                net_margin=_margin(net, revenue),
                total_assets=a.get("total_assets"),
                current_assets=a.get("current_assets"),
                cash_and_equivalents=cash,
                ppe_net=a.get("ppe_net"),
                total_liabilities=total_liabilities,
                current_liabilities=current_liab,
                total_equity=p.get("2.03"),
                total_debt=total_debt,
                net_debt=(total_debt - cash)
                if total_debt is not None and cash is not None
                else None,
                operating_cash_flow=dfc.get(period_end, {}).get("6.01"),
                shares_outstanding=shares.get(period_end),
            )
        )
    return statements


def _margin(numerator: Decimal | None, revenue: Decimal | None) -> float | None:
    if numerator is None or revenue is None or revenue == 0:
        return None
    return float(numerator / revenue)


class CVMProvider:
    """Async CVM bulk-filings provider (disk-cached downloads)."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir or (settings.market.cache_dir.parent / "cvm")
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> CVMProvider:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=15.0),
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            # Fleet idiom: environment proxies must never reroute (or
            # break) provider traffic.
            trust_env=False,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_financials(
        self, ticker: str, company_name: str, periods: int = 5
    ) -> list[FinancialStatement]:
        """Annual statements for a Brazilian (.SA) listing, or []."""
        if not ticker.upper().strip().endswith(".SA"):
            return []
        entries = parse_cadastro(await self._cadastro_text())
        entry = resolve_company(entries, company_name)
        if entry is None:
            logger.debug("CVM: no register match for %s (%s)", ticker, company_name)
            return []
        con: dict[str, list[dict[str, str]]] = {kind: [] for kind in _KINDS}
        ind: dict[str, list[dict[str, str]]] = {kind: [] for kind in _KINDS}
        year = date.today().year
        for candidate_year in (year, year - 1, year - 2):
            zip_path = await self._dfp_zip(candidate_year)
            if zip_path is None:
                continue
            self._collect(zip_path, entry.cnpj, con, ind)
        # Consolidated statements are the value of record; individual
        # statements serve only companies that file no consolidated.
        rows = {kind: con[kind] or ind[kind] for kind in _KINDS}
        if not rows["DRE"] and not rows["BPA"]:
            return []
        return assemble_statements(
            rows["DRE"],
            rows["BPA"],
            rows["BPP"],
            rows["DFC_MI"] or rows["DFC_MD"],
            rows["composicao_capital"],
            max_periods=periods,
        )

    # -- downloads + cache ------------------------------------------------

    def _manifest(self) -> dict[str, str]:
        path = self._cache_dir / "manifest.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}

    def _mark_fetched(self, name: str) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        manifest = self._manifest()
        manifest[name] = datetime.now().isoformat()
        (self._cache_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def _fresh(self, path: Path) -> bool:
        if not path.exists():
            return False
        fetched = self._manifest().get(path.name)
        if not fetched:
            return False
        try:
            return datetime.now() - datetime.fromisoformat(fetched) < _CACHE_TTL
        except ValueError:
            return False

    async def _download(self, url: str, dest: Path) -> bool:
        assert self._client is not None
        try:
            async with self._client.stream("GET", url) as resp:
                if resp.status_code == 404:
                    return False
                resp.raise_for_status()
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".tmp")
                with tmp.open("wb") as f:
                    async for chunk in resp.aiter_bytes(1 << 16):
                        f.write(chunk)
                tmp.replace(dest)
            self._mark_fetched(dest.name)
            return True
        except Exception as e:
            logger.warning("CVM download failed %s: %s", url, e)
            return False

    async def _cadastro_text(self) -> str:
        path = self._cache_dir / "cad_cia_aberta.csv"
        if not self._fresh(path):
            await self._download(BASE_URL + _CADASTRO_PATH, path)
        if not path.exists():
            return ""
        return path.read_bytes().decode("latin-1")

    async def _dfp_zip(self, year: int) -> Path | None:
        path = self._cache_dir / f"dfp_cia_aberta_{year}.zip"
        if not self._fresh(path):
            ok = await self._download(BASE_URL + _DFP_PATH.format(year=year), path)
            if not ok and not path.exists():
                return None
        return path if path.exists() else None

    # -- extraction ---------------------------------------------------------

    def _collect(
        self,
        zip_path: Path,
        cnpj: str,
        con: dict[str, list[dict[str, str]]],
        ind: dict[str, list[dict[str, str]]],
    ) -> None:
        try:
            archive = zipfile.ZipFile(zip_path)
        except Exception as e:
            logger.warning("CVM: unreadable archive %s: %s", zip_path, e)
            return
        names = set(archive.namelist())
        year = zip_path.stem.rsplit("_", 1)[-1]
        for kind in _KINDS:
            if kind == "composicao_capital":
                member = f"dfp_cia_aberta_composicao_capital_{year}.csv"
                if member in names:
                    text = archive.read(member).decode("latin-1")
                    con[kind].extend(parse_statement_rows(text, cnpj))
                continue
            for suffix, bucket in (("con", con), ("ind", ind)):
                member = f"dfp_cia_aberta_{kind}_{suffix}_{year}.csv"
                if member not in names:
                    continue
                try:
                    text = archive.read(member).decode("latin-1")
                except Exception as e:
                    logger.warning("CVM: cannot read %s in %s: %s", member, zip_path, e)
                    continue
                bucket[kind].extend(parse_statement_rows(text, cnpj))
