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
# Module: research_analyst/orchestrator.py | Version: 0.3.0 | Updated: 2026-08-23

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from .config import settings
from .engines.competitor import CompetitorEngine
from .engines.dividend import DividendEngine
from .engines.fundamental import FundamentalEngine
from .engines.macro import MacroEngine
from .engines.risk import RiskEngine
from .engines.technical import TechnicalEngine
from .engines.valuation import ValuationEngine
from .enums import ReportType, SecurityType
from .models import (
    AnalystEstimates,
    CompanyProfile,
    DividendData,
    FundamentalData,
    PriceSeries,
    ReportOutput,
    ResearchMetadata,
    ResearchRequest,
    ResearchResponse,
)
from .providers import markets
from .providers.market_data import MarketDataProvider
from .providers.sec_edgar import SECEdgarProvider
from .providers.technical import TechnicalProvider
from .reports.renderer import ReportRenderer

logger = logging.getLogger(__name__)


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
        market = markets.resolve(ticker)  # international market registry (v0.3.0)
        data_sources: list[str] = []
        data_freshness: dict[str, str] = {}
        warnings: list[str] = []
        all_assumptions: list[Any] = []

        logger.info("Starting research pipeline for %s [%s] (reports: %s)",
                     ticker, market.name, [r.value for r in request.report_types])

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

        # If market data failed, try SEC — US listings only (SEC EDGAR is US-scope)
        if profile is None and market.code == "US":
            try:
                async with SECEdgarProvider() as sec:
                    profile = await sec.get_company_profile(ticker)
                    data_sources.append("SEC EDGAR (company profile)")
            except Exception as e:
                raise ValueError(
                    f"Cannot resolve ticker '{ticker}'. "
                    f"Neither market data nor SEC returned results: {e}"
                ) from e
        if profile is None:
            hint = "." if market.code == "US" else (
                f" (SEC EDGAR not applicable for {market.name} listing)."
            )
            raise ValueError(
                f"Cannot resolve ticker '{ticker}'. Market data returned no profile" + hint
            )

        # Reporting/quote currency: prefer the profile's own (yfinance), else registry.
        reporting_currency = profile.currency or market.currency

        # --- Parallel data fetching ---
        price_task = self._fetch_prices(ticker, request)
        financials_yf_task = self._fetch_yf_financials(ticker)
        financials_sec_task = self._fetch_sec_financials(ticker)
        estimates_task = self._fetch_estimates(ticker)
        peers_task = self._fetch_peers(ticker)
        macro_task = self._fetch_macro()
        holders_task = self._fetch_holders(ticker)
        dividends_task = self._fetch_dividends(ticker)

        results = await asyncio.gather(
            price_task,
            financials_yf_task,
            financials_sec_task,
            estimates_task,
            peers_task,
            macro_task,
            holders_task,
            dividends_task,
            return_exceptions=True,
        )

        # Unpack results with graceful degradation
        prices = self._safe_result(results[0], PriceSeries(
            ticker=ticker, data=[], period_start=datetime.now().date(),
            period_end=datetime.now().date(),
        ), "price data", warnings)
        if prices.data:
            data_sources.append("yfinance (price data)")
            data_freshness["prices"] = prices.period_end.isoformat()

        financials_yf = self._safe_result(results[1], [], "yfinance financials", warnings)
        financials_sec = self._safe_result(results[2], [], "SEC XBRL financials", warnings)

        # Merge financials: prefer yfinance (cleaner), fill gaps with SEC
        financials = financials_yf if financials_yf else financials_sec
        if financials_yf:
            data_sources.append("yfinance (financial statements)")
        if financials_sec:
            data_sources.append("SEC EDGAR XBRL (financial statements)")

        estimates = self._safe_result(results[3], None, "analyst estimates", warnings)
        if estimates:
            data_sources.append("yfinance (analyst estimates)")

        peers = self._safe_result(results[4], [], "peer data", warnings)
        if peers:
            data_sources.append("yfinance (sector peers)")

        macro_snapshot = self._safe_result(results[5], None, "macro data", warnings)
        if macro_snapshot:
            data_sources.append("yfinance (macro proxies)")

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
        valuation.currency = reporting_currency
        await self._attach_usd_equivalent(valuation, reporting_currency)

        # --- Risk ---
        risk_matrix = self._risk_engine.assess(
            profile=profile,
            fundamental=fundamental_analysis,
            technical=technical_analysis,
            macro=macro_analysis,
            competitive=competitive_analysis,
        )

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

        # Explicit data-gap: a non-US listing with no fundamentals from either source.
        if market.code != "US" and not financials:
            warnings.append(
                f"No fundamentals for {market.name} listing ({ticker}): "
                f"SEC EDGAR is US-only and yfinance financials were empty."
            )

        metadata = ResearchMetadata(
            data_sources=data_sources,
            data_freshness=data_freshness,
            assumptions_used=all_assumptions,
            warnings=warnings,
            processing_time_seconds=round(elapsed, 2),
            market=market.name,
            reporting_currency=reporting_currency,
        )

        logger.info(
            "Research pipeline complete for %s: %d reports, %.1fs, %d warnings",
            ticker, len(reports), elapsed, len(warnings),
        )

        return ResearchResponse(
            ticker=ticker,
            security_type=profile.security_type,
            company_name=profile.name,
            generated_at=datetime.now(timezone.utc),
            reports=reports,
            metadata=metadata,
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

    async def _fetch_yf_financials(self, ticker: str) -> list:
        return await self._market.get_financials(ticker)

    async def _fetch_sec_financials(self, ticker: str) -> list:
        # SEC EDGAR is US-only; skip the (rate-limited) call for non-US listings.
        if not markets.should_query_sec(ticker):
            logger.debug(
                "SEC financials skipped for %s: non-US listing (%s)",
                ticker, markets.resolve(ticker).name,
            )
            return []
        try:
            async with SECEdgarProvider() as sec:
                return await sec.get_financials(ticker)
        except Exception as e:
            logger.debug("SEC financials unavailable for %s: %s", ticker, e)
            return []

    async def _fetch_estimates(self, ticker: str) -> AnalystEstimates | None:
        try:
            return await self._market.get_analyst_estimates(ticker)
        except Exception:
            return None

    async def _fetch_peers(self, ticker: str) -> list:
        try:
            return await self._market.get_sector_peers(
                ticker, max_peers=settings.analysis.max_competitors
            )
        except Exception as e:
            logger.debug("Peer discovery failed for %s: %s", ticker, e)
            return []

    async def _fetch_macro(self) -> Any:
        try:
            return await self._market.get_macro_snapshot()
        except Exception as e:
            logger.debug("Macro snapshot failed: %s", e)
            return None

    async def _fetch_holders(self, ticker: str) -> list:
        try:
            return await self._market.get_institutional_holders(ticker)
        except Exception:
            return []

    async def _fetch_dividends(self, ticker: str) -> Any:
        return await self._market.get_dividend_data(ticker)

    async def _attach_usd_equivalent(self, valuation: Any, currency: str) -> None:
        """Best-effort USD-equivalent of the current price via an FX pair.

        Skips when already USD or when the quote currency is a minor unit
        (e.g. GBp pence), where a naive conversion would be off by ~100x.
        """
        if not currency or currency.upper() == "USD":
            return
        if currency in {"GBp", "GBX", "ZAc", "ILA"}:
            logger.debug("USD-equivalent skipped: minor-unit quote currency %s", currency)
            return
        pair = markets.fx_pair(currency)
        if not pair or valuation.current_price <= 0:
            return
        try:
            fx = await self._market.get_price_series(pair, period="5d")
            rate = fx.current_price
            if rate and rate > 0:
                valuation.fx_rate_to_usd = round(rate, 6)
                valuation.current_price_usd = round(valuation.current_price * rate, 2)
        except Exception as e:
            logger.debug("FX fetch failed for %s: %s", pair, e)

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
