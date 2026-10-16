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

"""CVM provider (Brazil filings, wire-the-unwired matrix §7 #12).

Golden values are Petrobras's REAL FY2024 consolidated figures from
the CVM DFP 2024 bulk file (values in thousands of BRL in the file;
the provider scales by ESCALA_MOEDA=MIL). Cross-checks: the balance
sheet balances (assets == liabilities + equity) and attributable net
income is the publicly reported R$36.6B.
"""
# Module: tests/test_cvm.py

import io
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal

from research_analyst.providers.cvm import (
    CVMProvider,
    assemble_statements,
    parse_cadastro,
    parse_statement_rows,
    resolve_company,
)

CNPJ = "33.000.167/0001-01"
NAME = "PETROLEO BRASILEIRO S.A. PETROBRAS"

CADASTRO = (
    "CNPJ_CIA;DENOM_SOCIAL;DENOM_COMERC;SIT;CD_CVM\n"
    f"{CNPJ};{NAME};PETROBRAS;ATIVO;9512\n"
    "11.222.333/0001-44;VALE S.A.;VALE;ATIVO;4170\n"
    "55.666.777/0001-88;BANCO EXEMPLO S.A.;;ATIVO;1000\n"
    "99.888.777/0001-66;BANCO EXEMPLO S.A.;;ATIVO;1001\n"
    "00.111.222/0001-33;EMPRESA CANCELADA S.A.;;CANCELADO;2000\n"
)

_FLOW_HEADER = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;"
    "ESCALA_MOEDA;ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;"
    "DS_CONTA;VL_CONTA;ST_CONTA_FIXA"
)
_BS_HEADER = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;"
    "ESCALA_MOEDA;ORDEM_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;"
    "VL_CONTA;ST_CONTA_FIXA"
)


def _flow_row(code, value, *, fim="2024-12-31", refer="2024-12-31", ordem="ÚLTIMO"):
    return (
        f"{CNPJ};{refer};1;{NAME};009512;DF;REAL;MIL;{ordem};"
        f"{fim[:4]}-01-01;{fim};{code};Conta;{value};S"
    )


def _bs_row(code, value, *, fim="2024-12-31", refer="2024-12-31", ordem="ÚLTIMO"):
    return f"{CNPJ};{refer};1;{NAME};009512;DF;REAL;MIL;{ordem};{fim};{code};Conta;{value};S"


DRE_CSV = "\n".join([
    _FLOW_HEADER,
    _flow_row("3.01", "490829000.0000000000"),
    _flow_row("3.02", "-244367000.0000000000"),
    _flow_row("3.03", "246462000.0000000000"),
    _flow_row("3.04.01", "-26134000.0000000000"),
    _flow_row("3.04.02", "-9931000.0000000000"),
    _flow_row("3.05", "137201000.0000000000"),
    _flow_row("3.06.02", "-92959000.0000000000"),
    _flow_row("3.08", "-17721000.0000000000"),
    _flow_row("3.11", "37009000.0000000000"),
    _flow_row("3.11.01", "36606000.0000000000"),
    _flow_row("3.99", "0.0000000000"),  # placeholder row on the real filing
    # A cancelled-company row that must be filtered out by CNPJ.
    "00.111.222/0001-33;2024-12-31;1;EMPRESA CANCELADA S.A.;002000;DF;REAL;MIL;"
    "ÚLTIMO;2024-01-01;2024-12-31;3.01;Conta;999.0000000000;S",
])
BPA_CSV = "\n".join([
    _BS_HEADER,
    _bs_row("1", "1124797000.0000000000"),
    _bs_row("1.01", "135212000.0000000000"),
    _bs_row("1.01.01", "20254000.0000000000"),
    _bs_row("1.02.03", "843917000.0000000000"),
])
BPP_CSV = "\n".join([
    _BS_HEADER,
    _bs_row("2", "1124797000.0000000000"),
    _bs_row("2.01", "194808000.0000000000"),
    _bs_row("2.02", "562475000.0000000000"),
    _bs_row("2.03", "367514000.0000000000"),
    _bs_row("2.01.04", "68783000.0000000000"),
    _bs_row("2.02.01", "304684000.0000000000"),
])
DFC_CSV = "\n".join([_FLOW_HEADER, _flow_row("6.01", "204037000.0000000000")])
CAPITAL_CSV = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;QT_ACAO_ORDIN_CAP_INTEGR;"
    "QT_ACAO_PREF_CAP_INTEGR;QT_ACAO_TOTAL_CAP_INTEGR;"
    "QT_ACAO_ORDIN_TESOURO;QT_ACAO_PREF_TESOURO;QT_ACAO_TOTAL_TESOURO\n"
    f"{CNPJ};2024-12-31;1;{NAME};7442454142;5602042788;13044496930;"
    "222760;155541409;155764169"
)


def _petrobras_statements(**kwargs):
    return assemble_statements(
        parse_statement_rows(DRE_CSV, CNPJ),
        parse_statement_rows(BPA_CSV, CNPJ),
        parse_statement_rows(BPP_CSV, CNPJ),
        parse_statement_rows(DFC_CSV, CNPJ),
        parse_statement_rows(CAPITAL_CSV, CNPJ),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Register + resolution
# ---------------------------------------------------------------------------


def test_parse_cadastro_filters_inactive():
    entries = parse_cadastro(CADASTRO)
    assert {e.cd_cvm for e in entries} == {"9512", "4170", "1000", "1001"}


def test_resolve_exact_legal_name_with_accents():
    entries = parse_cadastro(CADASTRO)
    hit = resolve_company(entries, "Petróleo Brasileiro S.A. - Petrobras")
    assert hit is not None and hit.cd_cvm == "9512"


def test_resolve_commercial_name_and_subset():
    entries = parse_cadastro(CADASTRO)
    assert resolve_company(entries, "PETROBRAS").cd_cvm == "9512"
    assert resolve_company(entries, "Vale S.A.").cd_cvm == "4170"


def test_resolve_ambiguous_or_unknown_is_none():
    entries = parse_cadastro(CADASTRO)
    assert resolve_company(entries, "BANCO EXEMPLO S.A.") is None  # two registers
    assert resolve_company(entries, "Empresa Inexistente S.A.") is None
    assert resolve_company(entries, "") is None
    assert resolve_company(entries, "EMPRESA CANCELADA S.A.") is None  # filtered


# ---------------------------------------------------------------------------
# Assembly — the golden Petrobras FY2024
# ---------------------------------------------------------------------------


def test_golden_petrobras_fy2024():
    (stmt,) = _petrobras_statements()
    assert stmt.period == "FY2024"
    assert stmt.period_end_date == date(2024, 12, 31)
    assert stmt.is_annual is True
    assert stmt.revenue == Decimal("490829000000")
    assert stmt.cost_of_revenue == Decimal("244367000000")  # sign normalized
    assert stmt.gross_profit == Decimal("246462000000")
    assert stmt.sga_expense == Decimal("36065000000")
    assert stmt.operating_income == Decimal("137201000000")
    assert stmt.ebit == Decimal("137201000000")
    assert stmt.interest_expense == Decimal("92959000000000") / 1000
    assert stmt.tax_expense == Decimal("17721000000")
    # Attributable (3.11.01) wins over consolidated (3.11).
    assert stmt.net_income == Decimal("36606000000")
    assert stmt.gross_margin == 246462000 / 490829000
    # Balance sheet (internally consistent in the source file).
    assert stmt.total_assets == Decimal("1124797000000")
    assert stmt.current_assets == Decimal("135212000000")
    assert stmt.cash_and_equivalents == Decimal("20254000000")
    assert stmt.ppe_net == Decimal("843917000000")
    assert stmt.current_liabilities == Decimal("194808000000")
    assert stmt.total_liabilities == Decimal("757283000000")
    assert stmt.total_equity == Decimal("367514000000")
    assert (
        stmt.total_assets
        == stmt.total_liabilities + stmt.total_equity
    )
    assert stmt.total_debt == Decimal("373467000000")
    assert stmt.net_debt == Decimal("353213000000")
    assert stmt.operating_cash_flow == Decimal("204037000000")
    assert stmt.shares_outstanding == 12888732761
    assert stmt.eps_basic is None  # the filed 3.99 was a zero placeholder


def test_newest_filing_wins_for_restated_period():
    """FY2024 revenue as restated in the FY2025 filing (PENÚLTIMO
    there, DT_REFER later) overrides the original FY2024 filing."""
    restated = "\n".join([
        _FLOW_HEADER,
        _flow_row("3.01", "491000000.0000000000",
                  refer="2025-12-31", ordem="PENÚLTIMO"),
        _flow_row("3.03", "247000000.0000000000",
                  refer="2025-12-31", ordem="PENÚLTIMO"),
    ])
    rows = parse_statement_rows(DRE_CSV, CNPJ) + parse_statement_rows(restated, CNPJ)
    (stmt,) = assemble_statements(rows, [], [], [], [])
    assert stmt.revenue == Decimal("491000000000")


def test_missing_data_stays_missing():
    rows = parse_statement_rows(
        "\n".join([_FLOW_HEADER, _flow_row("3.01", "1000.0000000000")]), CNPJ
    )
    (stmt,) = assemble_statements(rows, [], [], [], [])
    assert stmt.revenue == Decimal("1000000")
    assert stmt.net_income is None
    assert stmt.total_debt is None
    assert stmt.net_debt is None
    assert stmt.shares_outstanding is None


# ---------------------------------------------------------------------------
# Provider behavior (cache-driven, no network)
# ---------------------------------------------------------------------------


async def test_non_brazilian_ticker_returns_empty():
    provider = CVMProvider()
    assert await provider.get_financials("AAPL", "Apple Inc.") == []
    assert await provider.get_financials("SHOP.TO", "Shopify Inc.") == []


def _write_zip(path, members: dict[str, str]) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, text in members.items():
            z.writestr(name, text)
    path.write_bytes(buffer.getvalue())


async def test_provider_end_to_end_from_cache(tmp_path):
    provider = CVMProvider(cache_dir=tmp_path)
    (tmp_path / "cad_cia_aberta.csv").write_text(CADASTRO, encoding="latin-1")
    year = date.today().year
    members = {
        "dfp_cia_aberta_DRE_con_2024.csv": DRE_CSV,
        "dfp_cia_aberta_BPA_con_2024.csv": BPA_CSV,
        "dfp_cia_aberta_BPP_con_2024.csv": BPP_CSV,
        "dfp_cia_aberta_DFC_MI_con_2024.csv": DFC_CSV,
        "dfp_cia_aberta_composicao_capital_2024.csv": CAPITAL_CSV,
    }
    _write_zip(tmp_path / "dfp_cia_aberta_2024.zip", members)
    _write_zip(tmp_path / f"dfp_cia_aberta_{year}.zip", {})
    _write_zip(tmp_path / f"dfp_cia_aberta_{year - 1}.zip", {})
    manifest = {
        name: datetime.now().isoformat()
        for name in (
            "cad_cia_aberta.csv",
            "dfp_cia_aberta_2024.zip",
            f"dfp_cia_aberta_{year}.zip",
            f"dfp_cia_aberta_{year - 1}.zip",
        )
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    statements = await provider.get_financials(
        "PETR4.SA", "Petróleo Brasileiro S.A. - Petrobras"
    )
    assert len(statements) == 1
    assert statements[0].revenue == Decimal("490829000000")
    # Unresolvable name -> no data, no guess.
    assert await provider.get_financials("XXXX3.SA", "Companhia Desconhecida") == []


# ---------------------------------------------------------------------------
# Financial-institution chart + register duplicates (real-data findings)
# ---------------------------------------------------------------------------

BANK_CNPJ = "60.872.504/0001-23"


def _bank_row(code, value):
    return (
        f"{BANK_CNPJ};2024-12-31;1;ITAÚ UNIBANCO HOLDING S.A.;001279;DF;"
        f"REAL;MIL;ÚLTIMO;2024-01-01;2024-12-31;{code};Conta;{value};S"
    )


def test_financial_institution_chart():
    """Banks file a shifted DRE (verified on Itaú's real FY2024):
    net income at 3.09, tax at 3.06, 3.05 is pre-tax — never EBIT."""
    dre_csv = "\n".join([
        _FLOW_HEADER,
        _bank_row("3.01", "335328000.0000000000"),
        _bank_row("3.02", "-199589000.0000000000"),
        _bank_row("3.03", "135739000.0000000000"),
        _bank_row("3.05", "47556000.0000000000"),
        _bank_row("3.06", "-5428000.0000000000"),
        _bank_row("3.09", "42128000.0000000000"),
        _bank_row("3.99", "16.7200000000"),
    ])
    (stmt,) = assemble_statements(parse_statement_rows(dre_csv, BANK_CNPJ), [], [], [], [])
    assert stmt.revenue == Decimal("335328000000")
    assert stmt.gross_profit == Decimal("135739000000")
    assert stmt.net_income == Decimal("42128000000")
    assert stmt.tax_expense == Decimal("5428000000")
    assert stmt.operating_income is None  # 3.05 pre-tax must not pose as EBIT
    assert stmt.ebit is None
    assert stmt.eps_basic == 16.72


def test_resolve_tolerates_duplicate_register_rows():
    """The real register lists Petrobras twice (same CNPJ/CD_CVM);
    duplicates of ONE company are not ambiguity."""
    entries = parse_cadastro(CADASTRO + f"{CNPJ};{NAME};PETROBRAS;ATIVO;9512\n")
    hit = resolve_company(entries, "Petróleo Brasileiro S.A. - Petrobras")
    assert hit is not None and hit.cd_cvm == "9512"
