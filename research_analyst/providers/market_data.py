"""Market data provider — price data, fundamentals, and macro indicators.

Design:
  - Primary source: yfinance (free, no API key, comprehensive)
  - Optional fallback: Alpha Vantage (keyed)
  - Disk-based TTL cache to avoid redundant API calls (O(1) lookup via hash key)
  - All data returned as typed Pydantic models
  - Thread-safe: yfinance calls wrapped in asyncio.to_thread for non-blocking I/O
  - Input sanitized before any external call
  - Graceful degradation: missing fields logged, never crash
"""
# Module: research_analyst/providers/market_data.py | Version: 0.1.1 | Updated: 2026-06-02

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import settings
from . import markets
from ..models import SymbolMatch
from ..models import (
    AnalystEstimates,
    CompanyProfile,
    Competitor,
    DividendData,
    DividendPayment,
    FinancialStatement,
    InstitutionalHolder,
    MacroSnapshot,
    PriceData,
    PriceSeries,
    SecurityType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------
_TICKER_RE = re.compile(r"^[A-Z0-9\.\-]{1,10}$")


def _sanitize_ticker(ticker: str) -> str:
    """Validate ticker: 1-10 chars, uppercase alphanumeric + dot/hyphen only."""
    cleaned = ticker.strip().upper()
    if not _TICKER_RE.match(cleaned):
        raise ValueError(f"Invalid ticker: must be 1-10 alphanumeric chars, got '{cleaned}'")
    return cleaned


def _safe_decimal(val: Any) -> Decimal | None:
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else int(f)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Disk cache — avoids hammering yfinance on repeat requests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Slice 0 (data-integrity): curated peer universe + FRED client
# ---------------------------------------------------------------------------

# Deterministic sector -> representative large-cap peers. Replaces the fragile
# yfinance funds_data.top_holdings lookup (empty from datacenter IPs). yfinance
# is still used to ENRICH per-peer metrics, but discovery no longer depends on it.
_SECTOR_PEERS: dict[str, list[str]] = {
    "Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "ADBE", "AMD", "CSCO", "ACN", "INTC", "QCOM", "TXN", "IBM", "NOW", "INTU", "AMAT", "LRCX", "MU", "ADI"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR", "EA"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "BKNG", "TJX", "GM", "F"],
    "Consumer Defensive": ["WMT", "PG", "KO", "PEP", "COST", "MDLZ", "CL", "MO", "PM", "TGT"],
    "Financial Services": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "SPGI", "V", "MA"],
    "Financials": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "SPGI"],
    "Healthcare": ["UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO", "ABT", "DHR", "BMY", "AMGN", "GILD"],
    "Industrials": ["CAT", "BA", "HON", "UPS", "GE", "RTX", "UNP", "DE", "LMT", "MMM", "EMR", "ETN"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "WMB"],
    "Utilities": ["NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL", "ED", "PEG"],
    "Real Estate": ["PLD", "AMT", "EQIX", "CCI", "PSA", "O", "SPG", "WELL", "DLR", "VICI"],
    "Basic Materials": ["LIN", "SHW", "APD", "ECL", "FCX", "NEM", "DOW", "DD", "NUE", "CTVA"],
}


def _sector_peer_candidates(sector: str, industry: str = "") -> list[str]:
    """Return a deterministic peer universe for a sector (no network call)."""
    return list(_SECTOR_PEERS.get(sector or "", []))


def _fred_observations(series_id: str, api_key: str, base_url: str, limit: int = 14) -> list[tuple[str, float]]:
    """Fetch recent FRED observations as (date, value), newest first. Stdlib only.

    Missing values (a literal dot) are skipped. Raises on transport/HTTP
    errors so the caller can degrade gracefully.
    """
    import json
    import urllib.parse
    import urllib.request

    params = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    })
    url = f"{base_url.rstrip('/')}/series/observations?{params}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        payload = json.loads(resp.read().decode())
    out: list[tuple[str, float]] = []
    for obs in payload.get("observations", []):
        val = obs.get("value")
        if val in (None, ".", ""):
            continue
        try:
            out.append((obs.get("date", ""), float(val)))
        except (TypeError, ValueError):
            continue
    return out


class _DiskCache:
    """Simple TTL-based disk cache using JSON files.

    Key: SHA-256 hash of (ticker + data_type + params)
    Value: JSON payload + timestamp
    Lookup: O(1) via filesystem hash
    """

    def __init__(self, cache_dir: Path, ttl_seconds: int) -> None:
        self._dir = cache_dir
        self._ttl = ttl_seconds
        self._dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self._dir / f"{h}.json"

    def get(self, key: str) -> Any | None:
        path = self._key_path(key)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
            if time.time() - raw.get("ts", 0) > self._ttl:
                path.unlink(missing_ok=True)
                return None
            return raw.get("data")
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)
            return None

    def put(self, key: str, data: Any) -> None:
        path = self._key_path(key)
        try:
            path.write_text(json.dumps({"ts": time.time(), "data": data}))
        except OSError as e:
            logger.warning("Cache write failed: %s", e)


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class MarketDataProvider:
    """Async market data provider backed by yfinance.

    Usage:
        provider = MarketDataProvider()
        prices = await provider.get_price_series("AAPL", period="1y")
        profile = await provider.get_company_profile("AAPL")
    """

    def __init__(self) -> None:
        self._cfg = settings.market
        self._cache = _DiskCache(
            cache_dir=self._cfg.cache_dir,
            ttl_seconds=self._cfg.cache_ttl_seconds,
        )

    # ------------------------------------------------------------------
    # yfinance wrapper — runs blocking calls in thread pool
    # ------------------------------------------------------------------

    @staticmethod
    async def _yf_ticker(ticker: str) -> Any:
        """Create yfinance Ticker object in thread pool.

        yfinance is synchronous; wrapping in to_thread prevents
        blocking the event loop.
        """
        import yfinance as yf
        return await asyncio.to_thread(lambda: yf.Ticker(ticker))

    @staticmethod
    async def _yf_download(
        ticker: str, period: str = "1y", interval: str = "1d"
    ) -> pd.DataFrame:
        """Download OHLCV data via yfinance in thread pool."""
        import yfinance as yf

        def _dl() -> pd.DataFrame:
            df = yf.download(
                ticker, period=period, interval=interval,
                auto_adjust=False, progress=False, threads=False,
            )
            return df

        return await asyncio.to_thread(_dl)

    # ------------------------------------------------------------------
    # Price data
    # ------------------------------------------------------------------

    async def get_price_series(
        self,
        ticker: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> PriceSeries:
        """Fetch OHLCV price series.

        Args:
            ticker: Security ticker.
            period: yfinance period string (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, max).
            interval: Bar interval (1d, 1wk, 1mo).

        Returns:
            PriceSeries with computed summary stats.
        """
        ticker = _sanitize_ticker(ticker)

        cache_key = f"prices:{ticker}:{period}:{interval}"
        cached = self._cache.get(cache_key)
        if cached:
            return PriceSeries.model_validate(cached)

        df = await self._yf_download(ticker, period=period, interval=interval)

        if df.empty:
            logger.warning("No price data returned for %s (period=%s)", ticker, period)
            return PriceSeries(
                ticker=ticker, data=[], period_start=date.today(), period_end=date.today()
            )

        # Handle multi-level columns from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        data_points: list[PriceData] = []
        for idx, row in df.iterrows():
            dt = idx.date() if hasattr(idx, "date") else idx
            o = _safe_float(row.get("Open"))
            h = _safe_float(row.get("High"))
            l_ = _safe_float(row.get("Low"))
            c = _safe_float(row.get("Close"))
            ac = _safe_float(row.get("Adj Close", row.get("Close")))
            v = _safe_int(row.get("Volume"))

            if c is not None:
                data_points.append(PriceData(
                    date=dt,
                    open=o or c,
                    high=h or c,
                    low=l_ or c,
                    close=c,
                    adj_close=ac or c,
                    volume=v or 0,
                ))

        if not data_points:
            return PriceSeries(
                ticker=ticker, data=[], period_start=date.today(), period_end=date.today()
            )

        # Compute summary stats — O(n) single pass where possible
        closes = [p.adj_close for p in data_points]
        volumes = [p.volume for p in data_points]
        current = closes[-1]
        high_52w = max(p.high for p in data_points[-252:]) if len(data_points) >= 1 else current
        low_52w = min(p.low for p in data_points[-252:]) if len(data_points) >= 1 else current

        # Average volumes
        avg_vol_30 = float(np.mean(volumes[-30:])) if len(volumes) >= 30 else float(np.mean(volumes))
        avg_vol_90 = float(np.mean(volumes[-90:])) if len(volumes) >= 90 else float(np.mean(volumes))

        # YTD return
        year_start = date(data_points[-1].date.year, 1, 1)
        ytd_start_price = next(
            (p.adj_close for p in data_points if p.date >= year_start), closes[0]
        )
        ytd_return = (current - ytd_start_price) / ytd_start_price if ytd_start_price else 0.0

        # 1Y return
        if len(closes) >= 252:
            ret_1y = (current - closes[-252]) / closes[-252] if closes[-252] else 0.0
        elif len(closes) >= 2:
            ret_1y = (current - closes[0]) / closes[0] if closes[0] else 0.0
        else:
            ret_1y = 0.0

        series = PriceSeries(
            ticker=ticker,
            data=data_points,
            period_start=data_points[0].date,
            period_end=data_points[-1].date,
            current_price=current,
            price_52w_high=high_52w,
            price_52w_low=low_52w,
            avg_volume_30d=avg_vol_30,
            avg_volume_90d=avg_vol_90,
            ytd_return=ytd_return,
            total_return_1y=ret_1y,
        )

        self._cache.put(cache_key, series.model_dump(mode="json"))
        return series

    # ------------------------------------------------------------------
    # Company profile (from yfinance .info)
    # ------------------------------------------------------------------

    async def get_company_profile(self, ticker: str) -> CompanyProfile:
        """Fetch company profile from yfinance.

        This is richer than SEC for market data fields (market cap, EV, etc.)
        but SEC is authoritative for legal/filing data.
        """
        ticker = _sanitize_ticker(ticker)

        cache_key = f"profile:{ticker}"
        cached = self._cache.get(cache_key)
        if cached:
            return CompanyProfile.model_validate(cached)

        yf_ticker = await self._yf_ticker(ticker)
        info = await asyncio.to_thread(lambda: yf_ticker.info)

        if not info:
            raise ValueError(f"No data returned from yfinance for '{ticker}'")

        # Resolution guard: reject symbols that do not map to a real listed
        # security. yfinance returns a sparse dict for unknown tickers (no
        # name, no price), which previously fell through to a *fabricated*
        # report (name defaulted to the raw ticker). A real equity/ETF —
        # including international listings such as RY.TO — always has at least
        # a name or a market price, so require one before proceeding.
        _name = info.get("longName") or info.get("shortName")
        _price_fields = (
            "regularMarketPrice", "currentPrice", "previousClose",
            "regularMarketPreviousClose", "open", "navPrice", "bid", "ask",
        )
        _has_price = any(
            _safe_float(info.get(f)) not in (None, 0) for f in _price_fields
        )
        if not _name and not _has_price:
            raise ValueError(
                f"Could not resolve ticker '{ticker}' to a listed security "
                f"(no company name or market price returned). "
                f"Check the symbol and try again."
            )

        # Determine security type
        quote_type = info.get("quoteType", "EQUITY").upper()
        is_etf = quote_type == "ETF"

        profile = CompanyProfile(
            ticker=ticker,
            name=info.get("longName") or info.get("shortName") or ticker,
            security_type=SecurityType.ETF if is_etf else SecurityType.EQUITY,
            sector=info.get("sector", ""),
            industry=info.get("industry", ""),
            market_cap=_safe_decimal(info.get("marketCap")),
            enterprise_value=_safe_decimal(info.get("enterpriseValue")),
            employees=_safe_int(info.get("fullTimeEmployees")),
            country=info.get("country", ""),
            exchange=info.get("exchange", ""),
            currency=info.get("currency", "USD"),
            description=info.get("longBusinessSummary", ""),
            website=info.get("website", ""),
        )

        self._cache.put(cache_key, profile.model_dump(mode="json"))
        return profile

    # ------------------------------------------------------------------
    # Symbol / name search (v0.3.0 Slice A.4)
    # ------------------------------------------------------------------

    async def search_symbols(self, query: str, max_results: int = 8) -> list[SymbolMatch]:
        """Resolve a name or symbol to candidate listings via yfinance search.

        Thin wrapper over yfinance's Search; the safe-confirm disambiguation lives
        in research_analyst.resolver. Returns [] on any lookup failure (no silent
        exception leaks). Each match's market/currency is enriched from the ticker
        suffix via the market registry. v0.3.0 Slice A.4.
        """
        q = (query or "").strip()
        if not q:
            return []

        def _search() -> list[dict]:
            import yfinance as yf
            try:
                s = yf.Search(q, max_results=max_results, enable_fuzzy_query=True)
            except TypeError:
                s = yf.Search(q)
            except Exception:
                return []
            try:
                return list(getattr(s, "quotes", []) or [])
            except Exception:
                return []

        raw = await asyncio.to_thread(_search)
        out: list[SymbolMatch] = []
        for r in raw:
            sym = str(r.get("symbol") or "").strip().upper()
            if not sym:
                continue
            mkt = markets.resolve(sym)
            out.append(SymbolMatch(
                symbol=sym,
                name=r.get("longname") or r.get("shortname")
                     or r.get("longName") or r.get("shortName") or "",
                exchange=r.get("exchDisp") or r.get("exchange") or "",
                quote_type=str(r.get("quoteType") or r.get("typeDisp") or "").upper(),
                market=mkt.code,
                market_name=mkt.name,
                currency=mkt.currency,
                score=float(r.get("score") or 0.0),
            ))
        return out

    # ------------------------------------------------------------------
    # Analyst estimates
    # ------------------------------------------------------------------

    async def get_analyst_estimates(self, ticker: str) -> AnalystEstimates:
        """Fetch analyst consensus estimates from yfinance."""
        ticker = _sanitize_ticker(ticker)

        cache_key = f"estimates:{ticker}"
        cached = self._cache.get(cache_key)
        if cached:
            return AnalystEstimates.model_validate(cached)

        yf_ticker = await self._yf_ticker(ticker)
        info = await asyncio.to_thread(lambda: yf_ticker.info)

        estimates = AnalystEstimates(
            target_price_mean=_safe_float(info.get("targetMeanPrice")),
            target_price_median=_safe_float(info.get("targetMedianPrice")),
            target_price_high=_safe_float(info.get("targetHighPrice")),
            target_price_low=_safe_float(info.get("targetLowPrice")),
            num_analysts=_safe_int(info.get("numberOfAnalystOpinions")) or 0,
            recommendation_mean=_safe_float(info.get("recommendationMean")),
            eps_estimate_current_year=_safe_float(info.get("epsCurrentYear")),
            eps_estimate_next_year=_safe_float(info.get("epsForward")),
            revenue_estimate_current_year=_safe_decimal(info.get("revenueEstimate")),
            earnings_growth_5y=_safe_float(info.get("earningsQuarterlyGrowth")),
        )

        self._cache.put(cache_key, estimates.model_dump(mode="json"))
        return estimates

    # ------------------------------------------------------------------
    # Institutional holders
    # ------------------------------------------------------------------

    async def get_institutional_holders(self, ticker: str) -> list[InstitutionalHolder]:
        """Fetch top institutional holders."""
        ticker = _sanitize_ticker(ticker)

        cache_key = f"inst_holders:{ticker}"
        cached = self._cache.get(cache_key)
        if cached:
            return [InstitutionalHolder.model_validate(h) for h in cached]

        yf_ticker = await self._yf_ticker(ticker)
        try:
            holders_df = await asyncio.to_thread(lambda: yf_ticker.institutional_holders)
        except Exception as e:
            logger.warning("Could not fetch institutional holders for %s: %s", ticker, e)
            return []

        if holders_df is None or holders_df.empty:
            return []

        holders: list[InstitutionalHolder] = []
        for _, row in holders_df.iterrows():
            holders.append(InstitutionalHolder(
                holder_name=str(row.get("Holder", "")),
                shares=_safe_int(row.get("Shares")) or 0,
                value=_safe_decimal(row.get("Value")),
                pct_held=_safe_float(row.get("% Out")),
                date_reported=(
                    row["Date Reported"].date()
                    if pd.notna(row.get("Date Reported"))
                    else None
                ),
            ))

        data = [h.model_dump(mode="json") for h in holders]
        self._cache.put(cache_key, data)
        return holders

    # ------------------------------------------------------------------
    # Financials from yfinance (supplement to SEC XBRL)
    # ------------------------------------------------------------------

    async def get_financials(self, ticker: str) -> list[FinancialStatement]:
        """Fetch annual financials from yfinance as a supplement/fallback to SEC.

        yfinance provides pre-computed ratios and cleaner data for recent periods.
        SEC XBRL is authoritative; use this to fill gaps.
        """
        ticker = _sanitize_ticker(ticker)

        cache_key = f"yf_financials:{ticker}"
        cached = self._cache.get(cache_key)
        if cached:
            return [FinancialStatement.model_validate(f) for f in cached]

        yf_ticker = await self._yf_ticker(ticker)

        try:
            income = await asyncio.to_thread(lambda: yf_ticker.financials)
            balance = await asyncio.to_thread(lambda: yf_ticker.balance_sheet)
            cashflow = await asyncio.to_thread(lambda: yf_ticker.cashflow)
        except Exception as e:
            logger.warning("Could not fetch yfinance financials for %s: %s", ticker, e)
            return []

        statements: list[FinancialStatement] = []

        if income is not None and not income.empty:
            for col in income.columns:
                period_date = col.date() if hasattr(col, "date") else None
                fy_label = f"FY{period_date.year}" if period_date else str(col)

                # Helper to pull row value safely
                def _row(df: pd.DataFrame | None, key: str) -> Any:
                    if df is None or df.empty or key not in df.index:
                        return None
                    val = df.loc[key, col] if col in df.columns else None
                    return val if pd.notna(val) else None

                revenue = _safe_decimal(_row(income, "Total Revenue"))
                gross_profit = _safe_decimal(_row(income, "Gross Profit"))
                op_income = _safe_decimal(_row(income, "Operating Income"))
                ebitda = _safe_decimal(_row(income, "EBITDA"))
                net_income = _safe_decimal(_row(income, "Net Income"))
                eps = _safe_float(_row(income, "Diluted EPS"))

                total_assets = _safe_decimal(_row(balance, "Total Assets"))
                total_liabilities = _safe_decimal(_row(balance, "Total Liabilities Net Minority Interest"))
                total_equity = _safe_decimal(_row(balance, "Stockholders Equity"))
                cash = _safe_decimal(_row(balance, "Cash And Cash Equivalents"))
                total_debt = _safe_decimal(_row(balance, "Total Debt"))

                op_cf = _safe_decimal(_row(cashflow, "Operating Cash Flow"))
                capex = _safe_decimal(_row(cashflow, "Capital Expenditure"))
                fcf = _safe_decimal(_row(cashflow, "Free Cash Flow"))
                divs = _safe_decimal(_row(cashflow, "Cash Dividends Paid"))
                buybacks = _safe_decimal(_row(cashflow, "Repurchase Of Capital Stock"))

                # Margins
                gm = float(gross_profit / revenue) if gross_profit and revenue and revenue != 0 else None
                om = float(op_income / revenue) if op_income and revenue and revenue != 0 else None
                nm = float(net_income / revenue) if net_income and revenue and revenue != 0 else None
                em = float(ebitda / revenue) if ebitda and revenue and revenue != 0 else None

                # Ratios
                roe = float(net_income / total_equity) if net_income and total_equity and total_equity != 0 else None
                roa = float(net_income / total_assets) if net_income and total_assets and total_assets != 0 else None
                d_e = float(total_debt / total_equity) if total_debt and total_equity and total_equity != 0 else None

                net_debt = total_debt - cash if total_debt is not None and cash is not None else None

                statements.append(FinancialStatement(
                    period=fy_label,
                    period_end_date=period_date,
                    is_annual=True,
                    revenue=revenue,
                    gross_profit=gross_profit,
                    operating_income=op_income,
                    ebitda=ebitda,
                    net_income=net_income,
                    eps_diluted=eps,
                    gross_margin=gm,
                    operating_margin=om,
                    net_margin=nm,
                    ebitda_margin=em,
                    total_assets=total_assets,
                    total_liabilities=total_liabilities,
                    total_equity=total_equity,
                    cash_and_equivalents=cash,
                    total_debt=total_debt,
                    net_debt=net_debt,
                    operating_cash_flow=op_cf,
                    capex=capex,
                    free_cash_flow=fcf,
                    dividends_paid=divs,
                    share_buybacks=buybacks,
                    roe=roe,
                    roa=roa,
                    debt_to_equity=d_e,
                ))

        data = [s.model_dump(mode="json") for s in statements]
        self._cache.put(cache_key, data)
        return statements

    # ------------------------------------------------------------------
    # Dividend / yield data (v0.1.1)
    # ------------------------------------------------------------------

    async def get_dividend_data(self, ticker: str) -> DividendData:
        """Fetch dividend / yield data from yfinance (.info + .dividends).

        Returns raw figures only — the DividendEngine computes the headline
        yield, payout ratios, safety, and attractiveness from these. Graceful:
        missing fields are left None and never crash the pipeline.
        """
        ticker = _sanitize_ticker(ticker)

        cache_key = f"dividends:{ticker}"
        cached = self._cache.get(cache_key)
        if cached:
            return DividendData.model_validate(cached)

        def _to_date(ts: Any) -> date | None:
            """yfinance returns ex/last dividend dates as UNIX epoch seconds."""
            if ts is None:
                return None
            try:
                f = float(ts)
                if np.isnan(f) or np.isinf(f) or f <= 0:
                    return None
                return datetime.utcfromtimestamp(f).date()
            except (ValueError, TypeError, OverflowError, OSError):
                return None

        yf_ticker = await self._yf_ticker(ticker)
        try:
            info = await asyncio.to_thread(lambda: yf_ticker.info)
        except Exception as e:
            logger.warning("Could not fetch dividend info for %s: %s", ticker, e)
            info = {}
        info = info or {}

        quote_type = str(info.get("quoteType", "EQUITY")).upper()
        is_etf = quote_type == "ETF"
        currency = info.get("currency", "USD")
        current_price = (
            _safe_float(info.get("currentPrice"))
            or _safe_float(info.get("regularMarketPrice"))
            or _safe_float(info.get("previousClose"))
        )

        # Full per-share dividend history
        history: list[DividendPayment] = []
        try:
            div_series = await asyncio.to_thread(lambda: yf_ticker.dividends)
            if div_series is not None and not div_series.empty:
                for idx, val in div_series.items():
                    d = idx.date() if hasattr(idx, "date") else idx
                    amt = _safe_float(val)
                    if isinstance(d, date) and amt is not None and amt > 0:
                        history.append(DividendPayment(ex_date=d, amount=amt))
        except Exception as e:
            logger.debug("Dividend history unavailable for %s: %s", ticker, e)

        data = DividendData(
            ticker=ticker,
            currency=currency,
            is_etf=is_etf,
            current_price=current_price,
            dividend_rate=_safe_float(info.get("dividendRate")),
            trailing_dividend_rate=_safe_float(info.get("trailingAnnualDividendRate")),
            info_dividend_yield=_safe_float(info.get("dividendYield")),
            info_payout_ratio=_safe_float(info.get("payoutRatio")),
            five_year_avg_yield=_safe_float(info.get("fiveYearAvgDividendYield")),
            etf_ttm_yield=_safe_float(info.get("yield")),
            ex_dividend_date=_to_date(info.get("exDividendDate")),
            last_dividend_value=_safe_float(info.get("lastDividendValue")),
            last_dividend_date=_to_date(info.get("lastDividendDate")),
            history=history,
        )

        self._cache.put(cache_key, data.model_dump(mode="json"))
        return data

    # ------------------------------------------------------------------
    # Peer / competitor lookup
    # ------------------------------------------------------------------

    async def get_sector_peers(self, ticker: str, max_peers: int = 8) -> list[Competitor]:
        """Discover sector peers via a curated sector -> peers map.

        Discovery is deterministic (no network) — it replaces the fragile
        yfinance funds_data.top_holdings lookup that returned empty from
        datacenter IPs (Fly/Render) and left the Competitive/Moat step blank.
        yfinance is used ONLY to enrich each peer's metrics, with retry +
        backoff and per-peer graceful skip.
        """
        ticker = _sanitize_ticker(ticker)

        profile = await self.get_company_profile(ticker)
        if not profile.sector:
            logger.warning("No sector data for %s; cannot discover peers.", ticker)
            return []

        peer_tickers = [
            t for t in _sector_peer_candidates(profile.sector, profile.industry)
            if t != ticker
        ]
        if not peer_tickers:
            logger.info("No curated peer set for sector '%s'", profile.sector)
            return []

        peers: list[Competitor] = []

        # Enrich peers in parallel — bounded concurrency, retry + graceful skip.
        sem = asyncio.Semaphore(4)

        async def _fetch_peer(pt: str) -> Competitor | None:
            async with sem:
                for attempt in range(3):
                    try:
                        pp = await self.get_company_profile(pt)
                        info = await self._yf_ticker(pt)
                        yf_info = await asyncio.to_thread(lambda: info.info)

                        # yfinance reports debtToEquity as a percent (e.g. 152.3);
                        # normalize to a ratio so it is comparable to the target's
                        # fundamental debt_to_equity (populated as a ratio by Fix B).
                        de = _safe_float(yf_info.get("debtToEquity"))
                        de_ratio = (de / 100.0) if de is not None else None

                        return Competitor(
                            ticker=pt,
                            name=pp.name,
                            market_cap=pp.market_cap,
                            revenue=_safe_decimal(yf_info.get("totalRevenue")),
                            gross_margin=_safe_float(yf_info.get("grossMargins")),
                            operating_margin=_safe_float(yf_info.get("operatingMargins")),
                            pe_ratio=_safe_float(yf_info.get("trailingPE")),
                            ev_ebitda=_safe_float(yf_info.get("enterpriseToEbitda")),
                            revenue_growth_yoy=_safe_float(yf_info.get("revenueGrowth")),
                            roe=_safe_float(yf_info.get("returnOnEquity")),
                            debt_to_equity=de_ratio,
                            dividend_yield=_safe_float(yf_info.get("trailingAnnualDividendYield")),
                        )
                    except Exception as e:
                        if attempt == 2:
                            logger.debug("Could not fetch peer %s after retries: %s", pt, e)
                            return None
                        await asyncio.sleep(0.5 * (attempt + 1))
                return None

        tasks = [_fetch_peer(pt) for pt in peer_tickers[:max_peers * 2]]
        results = await asyncio.gather(*tasks)

        for r in results:
            if r is not None and len(peers) < max_peers:
                peers.append(r)

        peers.sort(key=lambda p: float(p.market_cap or 0), reverse=True)
        return peers[:max_peers]

    # ------------------------------------------------------------------
    # Macro snapshot
    # ------------------------------------------------------------------

    async def _populate_fred(self, snapshot: MacroSnapshot) -> bool:
        """Populate the macro snapshot from FRED (official data).

        Returns True if at least one field was set. Graceful no-op when the
        key is missing. Series:
          - CPIAUCSL        -> cpi_yoy (YoY from 13 monthly points)
          - A191RL1Q225SBEA -> gdp_growth_latest (real GDP, annualized %)
          - BAMLH0A0HYM2    -> credit_spread_hy (HY OAS %)
          - T10Y2Y          -> yield_curve_spread / signal
        cycle_phase is derived from growth + curve.
        """
        api_key = settings.market.fred_api_key
        if not api_key:
            return False
        base = settings.market.fred_base_url
        got = False

        try:
            cpi = await asyncio.to_thread(_fred_observations, "CPIAUCSL", api_key, base, 14)
            if len(cpi) >= 13 and cpi[12][1]:
                snapshot.cpi_yoy = (cpi[0][1] / cpi[12][1]) - 1.0
                got = True
        except Exception as e:  # pragma: no cover - network
            logger.debug("FRED CPIAUCSL failed: %s", e)

        try:
            gdp = await asyncio.to_thread(_fred_observations, "A191RL1Q225SBEA", api_key, base, 2)
            if gdp:
                snapshot.gdp_growth_latest = gdp[0][1] / 100.0
                got = True
        except Exception as e:  # pragma: no cover - network
            logger.debug("FRED GDP failed: %s", e)

        try:
            hy = await asyncio.to_thread(_fred_observations, "BAMLH0A0HYM2", api_key, base, 5)
            if hy:
                snapshot.credit_spread_hy = hy[0][1] / 100.0
                got = True
        except Exception as e:  # pragma: no cover - network
            logger.debug("FRED HY OAS failed: %s", e)

        try:
            curve = await asyncio.to_thread(_fred_observations, "T10Y2Y", api_key, base, 5)
            if curve:
                spread = curve[0][1] / 100.0
                snapshot.yield_curve_spread = spread
                snapshot.yield_curve_signal = (
                    "inverted" if spread < 0 else ("flat" if spread < 0.002 else "normal")
                )
                got = True
        except Exception as e:  # pragma: no cover - network
            logger.debug("FRED T10Y2Y failed: %s", e)

        if snapshot.gdp_growth_latest is not None:
            g = snapshot.gdp_growth_latest
            inverted = (
                snapshot.yield_curve_spread is not None and snapshot.yield_curve_spread < 0
            )
            if g <= 0:
                snapshot.cycle_phase = "contraction"
            elif inverted:
                snapshot.cycle_phase = "peak"
            else:
                snapshot.cycle_phase = "expansion"
            got = True

        return got

    async def get_macro_snapshot(self) -> MacroSnapshot:
        """Fetch the current macro environment.

        Layered sources:
          - yfinance proxies: ^TNX (10Y yield), ^VIX (volatility)
          - FRED (official): CPI YoY, real GDP, HY credit spread, 10Y-2Y curve
            + derived cycle phase (see _populate_fred; no-op without a key).
        """
        cache_key = "macro_snapshot"
        cached = self._cache.get(cache_key)
        if cached:
            return MacroSnapshot.model_validate(cached)

        snapshot = MacroSnapshot(as_of_date=date.today())

        macro_tickers = {
            "^TNX": "us_10y_yield",
            "^VIX": "vix",
        }

        try:
            import yfinance as yf

            for symbol, field in macro_tickers.items():
                try:
                    tk = await asyncio.to_thread(lambda s=symbol: yf.Ticker(s))
                    hist = await asyncio.to_thread(lambda t=tk: t.history(period="5d"))
                    if hist is not None and not hist.empty:
                        val = _safe_float(hist["Close"].iloc[-1])
                        if field == "us_10y_yield" and val is not None:
                            snapshot.us_10y_yield = val / 100.0 if val > 1 else val
                        elif field == "vix":
                            snapshot.vix = val
                except Exception as e:
                    logger.debug("Macro ticker %s failed: %s", symbol, e)

        except ImportError:
            logger.warning("yfinance not available for macro data")

        # Official macro data from FRED. No-op when RA_MARKET_FRED_API_KEY is
        # unset; the ^TNX/^VIX proxies above still apply. Never raises.
        try:
            await self._populate_fred(snapshot)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("FRED population failed: %s", e)

        self._cache.put(cache_key, snapshot.model_dump(mode="json"))
        return snapshot

