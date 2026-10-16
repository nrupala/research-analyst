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

"""Research Analyst orchestrator — the main pipeline that ties everything together.

This is the single entry point for generating research reports. It:
  1. Validates and sanitizes the request
  2. Fetches data from all providers (parallel where possible)
  3. Runs all analysis engines
  4. Renders reports using the 7-step templates
  5. Returns typed ResearchResponse with full provenance

Design:
  - Async throughout — I/O-bound data fetching runs concurrently
  - Fail-safe: any individual provider or engine failure degrades gracefully
  - Full provenance: every data source, assumption, and gap is tracked
  - Deterministic: same request + same data = same report
  - No global state — each run is isolated

Architecture:
  Request → Validate → Fetch (parallel) → Analyze → Render → Response
"""
# Module: research_analyst/orchestrator.py | Version: 0.1.1 | Updated: 2026-06-02

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from .config import settings
from .engines.competitor import CompetitorEngine
from .engines.dividend import DividendEngine
from .engines.etf import ETFEngine
from .engines.fundamental import FundamentalEngine
from .engines.macro import MacroEngine
from .engines.risk import RiskEngine
from .engines.technical import TechnicalEngine
from .engines.valuation import ValuationEngine
from .enums import SecurityType
from .models import (
    PRICE_SOURCE_LABELS,
    AnalystEstimates,
    CompanyProfile,
    Competitor,
    DividendData,
    FinancialStatement,
    FundamentalData,
    InputSnapshot,
    InstitutionalHolder,
    PeerSetProvenance,
    PriceSeries,
    ReportOutput,
    ResearchMetadata,
    ResearchRequest,
    ResearchResponse,
    SourceRecord,
)
from .providers.cvm import CVMProvider
from .providers.edinet import EDINETProvider
from .providers.market_data import MarketDataProvider
from .providers.sec_edgar import SECEdgarProvider
from .providers.technical import TechnicalProvider
from .reports.renderer import ReportRenderer

logger = logging.getLogger(__name__)


# Issue #74: best-effort reference links for each declared data source so a
# report never shows a bare source count — every source is enumerated with a
# link or reference.
_SOURCE_URL_TEMPLATES: list[tuple[str, str]] = [
    ("SEC EDGAR", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=10-K"),
    ("US Treasury Fiscal Data", "https://fiscaldata.treasury.gov/datasets/average-interest-rates"),
    ("Bank of Canada", "https://www.bankofcanada.ca/valet/"),
    ("ECB Data Portal", "https://data.ecb.europa.eu"),
    ("Deutsche Bundesbank", "https://www.bundesbank.de/en/statistics/time-series-databases"),
    ("Eurostat", "https://ec.europa.eu/eurostat"),
    ("Bank of Japan", "https://www.stat-search.boj.or.jp"),
    ("EIA", "https://www.eia.gov/opendata/"),
    ("EDINET", "https://disclosure2.edinet-fsa.go.jp/"),
    ("CVM", "https://dados.cvm.gov.br"),
    ("Stooq", "https://stooq.com"),
    ("Nasdaq", "https://www.nasdaq.com/market-activity/stocks/{ticker}"),
    ("Tiingo", "https://www.tiingo.com"),
    ("Alpha Vantage", "https://www.alphavantage.co"),
    ("yfinance", "https://finance.yahoo.com/quote/{ticker}"),
]


def _source_records(ticker: str, data_sources: list[str]) -> list[SourceRecord]:
    """Build enumerated source records (#74) from the declared source labels."""
    records: list[SourceRecord] = []
    seen: set[str] = set()
    for label in data_sources:
        if label in seen:
            continue
        seen.add(label)
        url: str | None = None
        for marker, template in _SOURCE_URL_TEMPLATES:
            if marker.lower() in label.lower():
                url = template.format(ticker=ticker)
                break
        records.append(SourceRecord(name=label, url=url))
    return records


# Data Sources declaration per cascade step. The NAME always comes
# from models.PRICE_SOURCE_LABELS — the same map the price lines use —
# so a step can never wear two names (release-gate Low, 2026-10-15:
# "Yahoo Finance" beside the price, "yfinance" in Data Sources).
_PRICE_DECLARATION_SUFFIXES: dict[str, str] = {
    "nasdaq": "price data — exchange-published, end-of-day",
    "tiingo": "price data — end-of-day",
    "alphavantage": "price data — end-of-day",
    "stooq": "price data — free end-of-day",
    "yfinance": "price data",
}


def _price_declaration(data_source: str) -> str:
    """The Data Sources entry for the cascade step that served.

    An unknown/legacy stamp keeps the yfinance-era declaration name
    rather than inventing one.
    """
    name = PRICE_SOURCE_LABELS.get(data_source, "Yahoo Finance")
    suffix = _PRICE_DECLARATION_SUFFIXES.get(data_source, "price data")
    return f"{name} ({suffix})"


class ResearchOrchestrator:
    """Main research pipeline — coordinates providers, engines, and renderers.

    Usage:
        orchestrator = ResearchOrchestrator()
        response = await orchestrator.run(request)

    Thread safety: Each run() call is isolated. The orchestrator itself is
    stateless and can handle concurrent requests safely.
    """

    def __init__(self) -> None:
        self._market = MarketDataProvider()
        self._technical_provider = TechnicalProvider()
        self._fundamental_engine = FundamentalEngine()
        self._dividend_engine = DividendEngine()
        self._etf_engine = ETFEngine()
        self._technical_engine = TechnicalEngine()
        self._macro_engine = MacroEngine()
        self._competitor_engine = CompetitorEngine()
        self._valuation_engine = ValuationEngine()
        self._risk_engine = RiskEngine()
        self._renderer = ReportRenderer()

    async def run(self, request: ResearchRequest) -> ResearchResponse:
        """Execute the full research pipeline.

        Steps:
          1. Validate request
          2. Fetch data (parallel: SEC + market data + macro)
          3. Run analysis engines (sequential — each depends on prior)
          4. Render reports for each requested type
          5. Assemble response with metadata

        Args:
            request: Validated ResearchRequest.

        Returns:
            ResearchResponse with all requested reports.

        Raises:
            ValueError: If ticker cannot be resolved or no data available.
        """
        start_time = time.monotonic()
        ticker = request.ticker
        data_sources: list[str] = []
        data_freshness: dict[str, str] = {}
        warnings: list[str] = []
        all_assumptions: list[Any] = []

        logger.info("Starting research pipeline for %s (reports: %s)",
                     ticker, [r.value for r in request.report_types])

        # ================================================================
        # PHASE 1: Data Fetching (parallel where possible)
        # ================================================================

        # --- Company profile (market data is primary, SEC supplements) ---
        profile: CompanyProfile | None = None
        try:
            profile = await self._market.get_company_profile(ticker)
            data_sources.append("yfinance (company profile)")
        except Exception as e:
            logger.warning("Market data profile failed for %s: %s", ticker, e)
            warnings.append(f"Market data profile unavailable: {e}")

        # If market data failed, try SEC
        if profile is None:
            try:
                async with SECEdgarProvider() as sec:
                    profile = await sec.get_company_profile(ticker)
                    data_sources.append("SEC EDGAR (company profile)")
            except Exception as e:
                raise ValueError(
                    f"Cannot resolve ticker '{ticker}'. "
                    f"Neither market data nor SEC returned results: {e}"
                ) from e

        # --- Parallel data fetching ---
        price_task = self._fetch_prices(ticker, request)
        financials_yf_task = self._fetch_yf_financials(ticker)
        financials_sec_task = self._fetch_sec_financials(ticker)
        estimates_task = self._fetch_estimates(ticker)
        peers_task = self._fetch_peers(ticker)
        macro_task = self._fetch_macro()
        holders_task = self._fetch_holders(ticker)
        dividends_task = self._fetch_dividends(ticker)
        financials_cvm_task = self._fetch_cvm_financials(
            ticker, profile.name if profile else ""
        )
        financials_edinet_task = self._fetch_edinet_financials(ticker)

        results = await asyncio.gather(
            price_task,
            financials_yf_task,
            financials_sec_task,
            estimates_task,
            peers_task,
            macro_task,
            holders_task,
            dividends_task,
            financials_cvm_task,
            financials_edinet_task,
            return_exceptions=True,
        )

        # Unpack results with graceful degradation
        prices = self._safe_result(results[0], PriceSeries(
            ticker=ticker, data=[], period_start=datetime.now().date(),
            period_end=datetime.now().date(),
        ), "price data", warnings)
        if prices.data:
            # Declare the cascade step that actually served the
            # prices (owner cascade, 2026-10-15).
            data_sources.append(_price_declaration(prices.data_source))
            data_freshness["prices"] = prices.period_end.isoformat()

        financials_yf = self._safe_result(results[1], [], "yfinance financials", warnings)
        financials_sec = self._safe_result(results[2], [], "SEC XBRL financials", warnings)
        financials_cvm = self._safe_result(results[8], [], "CVM financials", warnings)
        financials_edinet = self._safe_result(results[9], [], "EDINET financials", warnings)

        # Merge financials: for Brazilian listings the regulator's own
        # filings (CVM) are the first source and lead — but only over
        # a completeness floor (newest statement carries revenue AND
        # net income), so a partial CVM parse can never degrade a
        # report yfinance would have served whole. Japanese listings
        # follow the same rule with EDINET. Elsewhere yfinance leads
        # with SEC XBRL as its fallback.
        cvm_leads = bool(
            financials_cvm
            and financials_cvm[0].revenue is not None
            and financials_cvm[0].net_income is not None
        )
        edinet_leads = bool(
            financials_edinet
            and financials_edinet[0].revenue is not None
            and financials_edinet[0].net_income is not None
        )
        if cvm_leads:
            financials = financials_cvm
        elif edinet_leads:
            financials = financials_edinet
        elif financials_yf:
            financials = financials_yf
        else:
            financials = financials_sec
        if cvm_leads:
            data_sources.append("CVM (financial statements — Brazil regulator filings)")
        if edinet_leads:
            data_sources.append("EDINET (financial statements — Japan regulator filings)")
        if financials_yf:
            data_sources.append("yfinance (financial statements)")
        if financials_sec:
            data_sources.append("SEC EDGAR XBRL (financial statements)")

        estimates = self._safe_result(results[3], None, "analyst estimates", warnings)
        if estimates:
            data_sources.append("yfinance (analyst estimates)")

        peers, peer_provenance = self._safe_result(
            results[4], ([], None), "peer data", warnings
        )
        if peers:
            data_sources.append("yfinance (sector peers)")
        # Issue #67: missing expected peers are flagged loudly, never silent.
        if peer_provenance is not None and peer_provenance.missing_tickers:
            warnings.append(
                "Peer universe incomplete: expected peers "
                + ", ".join(peer_provenance.missing_tickers)
                + " could not be enriched and were excluded. "
                f"Peer map v{peer_provenance.map_version} "
                f"(hash {peer_provenance.map_hash})."
            )

        macro_snapshot = self._safe_result(results[5], None, "macro data", warnings)
        if macro_snapshot:
            data_sources.append("yfinance (macro proxies)")
            # First-source supplements (registry step 1): named official
            # sources that contributed to the macro snapshot, if any.
            for label in getattr(macro_snapshot, "supplemental_sources", []):
                if label not in data_sources:
                    data_sources.append(label)

        holders = self._safe_result(results[6], [], "institutional holders", warnings)

        dividend_data = self._safe_result(
            results[7], DividendData(ticker=ticker), "dividend data", warnings
        )
        if dividend_data and (dividend_data.history or dividend_data.dividend_rate):
            data_sources.append("yfinance (dividends)")

        # ================================================================
        # PHASE 2: Analysis Engines
        # ================================================================

        # --- Fundamental ---
        fundamental_data = FundamentalData(
            profile=profile,
            financials=financials,
            analyst_estimates=estimates,
            institutional_holders=holders,
        )
        fundamental_analysis = self._fundamental_engine.analyze(fundamental_data)
        all_assumptions.extend(fundamental_analysis.assumptions)

        # --- Technical ---
        technical_indicators = self._technical_provider.compute(prices)
        technical_analysis = self._technical_engine.analyze(technical_indicators, prices)
        all_assumptions.extend(technical_analysis.assumptions)

        # --- Macro ---
        macro_analysis = None
        if macro_snapshot:
            macro_analysis = self._macro_engine.analyze(macro_snapshot, profile)
            all_assumptions.extend(macro_analysis.assumptions)

        # --- Competitive ---
        competitive_analysis = None
        if peers:
            competitive_analysis = self._competitor_engine.analyze(
                profile, peers, fundamental=fundamental_analysis
            )
            all_assumptions.extend(competitive_analysis.assumptions)
            # Issue #67: stamp the versioned peer-universe note on the landscape.
            if peer_provenance is not None and competitive_analysis.landscape is not None:
                competitive_analysis.landscape.peer_set_note = peer_provenance.coverage_note

        # --- Dividend & Yield (v0.1.1) ---
        dividend_analysis = self._dividend_engine.analyze(
            dividend_data,
            financials,
            macro=macro_snapshot,
            peers=peers,
            fundamental=fundamental_analysis,
            current_price=prices.current_price,
        )
        all_assumptions.extend(dividend_analysis.assumptions)

        # --- Valuation ---
        pe_comps_median = None
        ev_ebitda_comps_median = None
        if peers:
            import numpy as np
            pe_vals = [p.pe_ratio for p in peers if p.pe_ratio is not None and p.pe_ratio > 0]
            ev_vals = [p.ev_ebitda for p in peers if p.ev_ebitda is not None and p.ev_ebitda > 0]
            pe_comps_median = float(np.median(pe_vals)) if pe_vals else None
            ev_ebitda_comps_median = float(np.median(ev_vals)) if ev_vals else None

        valuation = self._valuation_engine.build_valuation(
            profile=profile,
            financials=financials,
            prices=prices,
            pe_comps_median=pe_comps_median,
            ev_ebitda_comps_median=ev_ebitda_comps_median,
            analyst_target_mean=estimates.target_price_mean if estimates else None,
            analyst_target_low=estimates.target_price_low if estimates else None,
            analyst_target_high=estimates.target_price_high if estimates else None,
            custom_assumptions=request.custom_assumptions,
        )

        # --- Risk ---
        risk_matrix = self._risk_engine.assess(
            profile=profile,
            fundamental=fundamental_analysis,
            technical=technical_analysis,
            macro=macro_analysis,
            competitive=competitive_analysis,
        )

        # --- ETF-as-subject (Slice B) ---
        etf_analysis = None
        if profile.security_type is SecurityType.ETF:
            etf_metadata = None
            try:
                etf_metadata = await self._market.fetch_etf_metadata(ticker)
                data_sources.append("yfinance (ETF metadata)")
            except Exception as e:
                logger.warning("ETF metadata fetch failed for %s: %s", ticker, e)
            etf_analysis = self._etf_engine.analyze(profile, etf_metadata)
            all_assumptions.extend(etf_analysis.get("assumptions", []))

        # ================================================================
        # PHASE 3: Report Rendering
        # ================================================================

        reports: list[ReportOutput] = []

        for report_type in request.report_types:
            try:
                report = self._renderer.render(
                    report_type=report_type,
                    profile=profile,
                    prices=prices,
                    financials=financials,
                    fundamental=fundamental_analysis,
                    technical_indicators=technical_indicators,
                    technical=technical_analysis,
                    macro=macro_analysis,
                    competitive=competitive_analysis,
                    valuation=valuation,
                    risk_matrix=risk_matrix,
                    capital_allocation=fundamental_analysis.capital_allocation,
                    dividend=dividend_analysis,
                    etf=etf_analysis,
                )
                reports.append(report)
            except Exception as e:
                logger.error("Report rendering failed for %s (%s): %s",
                             ticker, report_type.value, e, exc_info=True)
                warnings.append(f"Report '{report_type.value}' rendering failed: {e}")

        # ================================================================
        # PHASE 4: Assemble Response
        # ================================================================

        elapsed = time.monotonic() - start_time

        # Issue #69: one snapshotted input set per run; every number traces to it.
        input_snapshot = self._build_input_snapshot(
            ticker=ticker,
            request=request,
            profile=profile,
            prices=prices,
            financials=financials,
            macro_snapshot=macro_snapshot,
            peers=peers,
            peer_provenance=peer_provenance,
        )

        # Issue #66: data-as-of comes from the price series (EOD quotes).
        price_as_of = data_freshness.get("prices")
        metadata = ResearchMetadata(
            data_sources=data_sources,
            data_freshness=data_freshness,
            assumptions_used=all_assumptions,
            warnings=warnings,
            processing_time_seconds=round(elapsed, 2),
            data_as_of=f"{price_as_of} (previous close)" if price_as_of else None,
            source_records=_source_records(ticker, data_sources),
            peer_set=peer_provenance,
            input_snapshot=input_snapshot,
        )
        # Issue #66: SLA state from data-as-of age (weekends/holidays tolerated).
        if price_as_of:
            try:
                from datetime import date as _date

                as_of = _date.fromisoformat(price_as_of)
                age_days = (datetime.now(UTC).date() - as_of).days
                if age_days > 4:
                    metadata.sla_state = "stale"
                    metadata.stale_warning = (
                        f"Price data is {age_days} days old (as of {price_as_of}). "
                        "Quotes may not reflect the latest trading session."
                    )
            except ValueError:
                pass

        logger.info(
            "Research pipeline complete for %s: %d reports, %.1fs, %d warnings",
            ticker, len(reports), elapsed, len(warnings),
        )

        return ResearchResponse(
            ticker=ticker,
            security_type=profile.security_type,
            company_name=profile.name,
            currency=profile.currency,
            generated_at=datetime.now(UTC),
            reports=reports,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Evidence integrity (#66/#67/#69/#74)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_input_snapshot(
        *,
        ticker: str,
        request: ResearchRequest,
        profile: CompanyProfile,
        prices: PriceSeries,
        financials: list[FinancialStatement],
        macro_snapshot: Any,
        peers: list[Competitor],
        peer_provenance: PeerSetProvenance | None,
    ) -> InputSnapshot:
        """Capture the single snapshotted input set for this run (#69).

        Every number in the generated reports traces to these inputs. The
        hash is over canonical JSON so reproducibility is checkable.
        """
        ordered = sorted(financials, key=lambda f: f.period_end_date or datetime.min.date())
        latest = ordered[-1] if ordered else None

        def _fstmt_fields(s: Any) -> dict[str, Any]:
            if s is None:
                return {}
            keys = (
                "period", "revenue", "net_income", "eps_diluted", "ebitda",
                "operating_cash_flow", "free_cash_flow", "total_assets",
                "total_debt", "shareholders_equity", "shares_outstanding",
            )
            out: dict[str, Any] = {}
            for k in keys:
                v = getattr(s, k, None)
                out[k] = str(v) if v is not None else None
            return out

        def _macro_fields(m: Any) -> dict[str, Any]:
            if m is None:
                return {}
            keys = (
                "us_10y_yield", "cpi_yoy", "gdp_growth_latest",
                "credit_spread_hy", "yield_curve_spread",
            )
            return {k: getattr(m, k, None) for k in keys}

        inputs: dict[str, Any] = {
            "ticker": ticker,
            "report_types": [r.value for r in request.report_types],
            "timeframe": request.timeframe.value,
            "custom_assumptions": request.custom_assumptions,
            "profile": {
                "sector": profile.sector,
                "industry": profile.industry,
                "currency": profile.currency,
                "exchange": profile.exchange,
            },
            "price": {
                "current_price": prices.current_price,
                "period_end": prices.period_end.isoformat(),
            },
            "latest_financials": _fstmt_fields(latest),
            "macro": _macro_fields(macro_snapshot),
            "peer_tickers": sorted(p.ticker for p in peers),
            "peer_map_version": peer_provenance.map_version if peer_provenance else None,
            "peer_map_hash": peer_provenance.map_hash if peer_provenance else None,
        }
        canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), default=str)
        return InputSnapshot(
            captured_at_utc=datetime.now(UTC),
            input_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            inputs=inputs,
        )

    # ------------------------------------------------------------------
    # Data fetching helpers (each isolated, never crashes the pipeline)
    # ------------------------------------------------------------------
    async def _fetch_prices(self, ticker: str, request: ResearchRequest) -> PriceSeries:
        """Fetch price data with period based on request timeframe."""
        period_map = {
            "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y",
            "3Y": "3y", "5Y": "5y", "10Y": "10y",
        }
        period = period_map.get(request.timeframe.value, "1y")
        return await self._market.get_price_series(ticker, period=period)

    async def _fetch_yf_financials(self, ticker: str) -> list[FinancialStatement]:
        return await self._market.get_financials(ticker)

    async def _fetch_sec_financials(self, ticker: str) -> list[FinancialStatement]:
        try:
            async with SECEdgarProvider() as sec:
                return await sec.get_financials(ticker)
        except Exception as e:
            logger.debug("SEC financials unavailable for %s: %s", ticker, e)
            return []

    async def _fetch_cvm_financials(
        self, ticker: str, company_name: str
    ) -> list[FinancialStatement]:
        try:
            async with CVMProvider() as cvm:
                return await cvm.get_financials(ticker, company_name)
        except Exception as e:
            logger.debug("CVM financials unavailable for %s: %s", ticker, e)
            return []

    async def _fetch_edinet_financials(
        self, ticker: str
    ) -> list[FinancialStatement]:
        try:
            async with EDINETProvider() as edinet:
                return await edinet.get_financials(ticker)
        except Exception as e:
            logger.debug("EDINET financials unavailable for %s: %s", ticker, e)
            return []

    async def _fetch_estimates(self, ticker: str) -> AnalystEstimates | None:
        try:
            return await self._market.get_analyst_estimates(ticker)
        except Exception:
            return None

    async def _fetch_peers(self, ticker: str) -> tuple[list[Competitor], PeerSetProvenance | None]:
        try:
            peers, provenance = await self._market.get_sector_peers_with_provenance(
                ticker, max_peers=settings.analysis.max_competitors
            )
            return peers, provenance
        except Exception as e:
            logger.debug("Peer discovery failed for %s: %s", ticker, e)
            return [], None

    async def _fetch_macro(self) -> Any:
        try:
            return await self._market.get_macro_snapshot()
        except Exception as e:
            logger.debug("Macro snapshot failed: %s", e)
            return None

    async def _fetch_holders(self, ticker: str) -> list[InstitutionalHolder]:
        try:
            return await self._market.get_institutional_holders(ticker)
        except Exception:
            return []

    async def _fetch_dividends(self, ticker: str) -> Any:
        return await self._market.get_dividend_data(ticker)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_result(result: Any, default: Any, label: str, warnings: list[str]) -> Any:
        """Extract result from asyncio.gather, falling back to default on error."""
        if isinstance(result, Exception):
            logger.warning("Data fetch failed (%s): %s", label, result)
            warnings.append(f"{label} unavailable: {result}")
            return default
        return result
